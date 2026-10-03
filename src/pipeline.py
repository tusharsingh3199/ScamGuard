"""Phase 7 - End-to-end pipeline.  Run:  python -m src.pipeline
raw feeds -> adapters -> features -> rules + models -> explanations -> cases -> SQLite/CSV/JSON"""
import json
import os
import sqlite3
import time

import numpy as np
import pandas as pd

from . import explain as ex
from . import interventions as iv
from .adapters import unify
from .features import FEATURES, build_features
from .fraud_model import train_and_score
from .loan_model import LOAN_FEATURES, build_loan_table, train_repayment
from .mule_graph import detect_mules
from .rules import apply_rules

DATA = os.path.join(iv.ROOT, "data")


def main():
    t0 = time.time()
    rd = lambda n: pd.read_csv(os.path.join(DATA, f"{n}.csv"))
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    demo, today = meta["demo_customer"], meta["today"]
    customers, payees, devices = rd("customers"), rd("payees"), rd("devices")

    print("[1/7] unifying channels ...")
    u = unify(rd("raw_upi"), rd("raw_card"), rd("raw_wallet"), rd("raw_netbanking"), rd("identity_map"), payees)
    print(f"      {len(u):,} events from 4 channels, {u.customer_id.nunique()} customers, 0 unresolved IDs = {u.customer_id.isna().sum() == 0}")

    print("[2/7] cross-channel features ...")
    feats = build_features(u, customers, devices, payees)
    F = u.drop(columns=["channel_specific_json", "is_collect"]).merge(feats.drop(columns="amount"), on="txn_id")
    F = F.merge(rd("fraud_labels"), on="txn_id")
    F = pd.concat([F, apply_rules(F)], axis=1)

    print("[3/7] fraud engine (rules + XGBoost + IsolationForest + scam classifier) ...")
    F, fm, models = train_and_score(F, demo)
    for k in ("rules_only", "xgboost_only", "hybrid"):
        m = fm[k]
        print(f"      {k:13s} precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f} PR-AUC={m['pr_auc']:.3f}")
    graph = detect_mules(u)
    print(f"      mule graph: {len(graph['mules'])} mule accounts flagged, {graph['rings']} ring(s)")

    print("[4/7] loan engine ...")
    B = build_loan_table(customers, rd("loans"), rd("repayments"), rd("income_expense"), today)
    B, lm, lmodel = train_repayment(B, rd("loan_labels"), demo)
    B["today"] = today
    print(f"      repayment model AUC={lm['auc']:.3f} recall={lm['recall']:.3f} PR-AUC={lm['pr_auc']:.3f}  bands={lm['band_counts']}")

    print("[5/7] explanations (TreeSHAP) ...")
    sel = F[F.fraud_score >= .3].index
    cf = ex.contribs(models["xgb"], F.loc[sel, FEATURES])
    reasons, summaries = {}, {}
    for j, i in enumerate(sel):
        row = F.loc[i]
        mr = ex.fmt(ex.top_reasons(row, cf[j], FEATURES, ex.FRAUD_T))
        rs = ([f"{row.rule_reason} (rule, {row.rule_score:.2f})"] if row.rule_fired else []) + mr
        reasons[i] = json.dumps(rs)
        summaries[i] = ex.fraud_summary(row.scam_type_pred if row.scam_type_pred != "none" else "suspicious activity",
                                        row.fraud_score, mr, row.amount)
    F["reasons"] = pd.Series(reasons)
    F["summary"] = pd.Series(summaries)
    F[["reasons", "summary"]] = F[["reasons", "summary"]].fillna("")
    cb = ex.contribs(lmodel, B[LOAN_FEATURES])
    B["reasons"], B["summary"] = "", ""
    for j in range(len(B)):
        r = ex.fmt(ex.top_reasons(B.iloc[j], cb[j], LOAN_FEATURES, ex.LOAN_T))
        B.loc[B.index[j], "reasons"] = json.dumps(r)
        B.loc[B.index[j], "summary"] = ex.loan_summary(B.repayment_risk.iloc[j], B.risk_band.iloc[j], r)

    print("[6/7] latency benchmark ...")
    samp = F.sample(300, random_state=1)
    t = time.perf_counter()
    for i in range(len(samp)):
        row = samp.iloc[[i]]
        apply_rules(row)
        models["xgb"].predict_proba(row[FEATURES])
    fm["avg_latency_ms"] = round((time.perf_counter() - t) / len(samp) * 1000, 2)

    print("[7/7] cases + saving ...")
    keep = ["txn_id", "customer_id", "timestamp", "channel", "direction", "amount", "payee_id", "payee_type", "device_id",
            "note", "is_fraud", "scam_type", "rule_score", "rule_type", "model_prob", "anomaly_pct", "anomaly_flag",
            "fraud_score", "scam_type_pred", "action", "reasons", "summary", "amount_ratio", "new_payee"]
    S = F[keep].rename(columns={"scam_type": "scam_type_true"}).sort_values("timestamp").reset_index(drop=True)
    n_cases = iv.create_cases(S, B, customers)
    con = sqlite3.connect(iv.DB)
    S.to_sql("scored_transactions", con, if_exists="replace", index=False)
    B.to_sql("borrower_scores", con, if_exists="replace", index=False)
    con.close()
    S.to_csv(os.path.join(DATA, "scored_transactions.csv"), index=False)
    B.to_csv(os.path.join(DATA, "borrower_scores.csv"), index=False)
    json.dump(graph, open(os.path.join(DATA, "mule_graph.json"), "w"))
    data_sum = dict(transactions=len(S), customers=len(customers), fraud_rate=round(float(S.is_fraud.mean()), 4),
                    alerts=int((S.fraud_score >= .5).sum()), holds=int((S.action == "HOLD").sum()), cases=n_cases)
    json.dump(dict(fraud=fm, loan=lm, data=data_sum), open(os.path.join(DATA, "metrics.json"), "w"), indent=1)
    print(f"done in {time.time() - t0:.0f}s | {data_sum} | model-scoring latency {fm['avg_latency_ms']} ms/event")


if __name__ == "__main__":
    main()
