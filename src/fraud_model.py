"""Phase 3b - Hybrid fraud engine: rules + XGBoost + Isolation Forest + scam-type classifier.

final fraud_score = max(rule_score, model_prob), +0.1 if anomaly fires, capped at 1.0
Time-based split: train on the first 70% of the timeline, test on the last 30% (demo customer excluded from training).
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from .features import FEATURES

ANOM_FEATS = ["amount_zscore", "amount_ratio", "txns_last_10min", "txns_last_1hr", "channels_used_1hr",
              "payee_risk", "hour_of_day", "device_age_log", "outflow_log", "inbound_unique_senders_24h"]


def _metrics(y, score, thr=.5):
    pred = (np.asarray(score) >= thr).astype(int)
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    return dict(precision=round(float(p), 4), recall=round(float(r), 4), f1=round(float(f), 4),
                pr_auc=round(float(average_precision_score(y, score)), 4), confusion=confusion_matrix(y, pred).tolist())


def _anom_matrix(F):
    X = F[[c for c in ANOM_FEATS if c in F.columns]].copy()
    return X


def train_and_score(F: pd.DataFrame, demo_customer: str):
    F = F.copy()
    F["device_age_log"] = np.log1p(F.device_age_hours)
    F["outflow_log"] = np.log1p(F.total_outflow_1hr_all_channels)
    split = F.timestamp.quantile(.70)
    tr = (F.timestamp < split) & (F.customer_id != demo_customer)
    te = (F.timestamp >= split) & (F.customer_id != demo_customer)
    Xtr, ytr = F.loc[tr, FEATURES], F.loc[tr, "is_fraud"]

    # --- supervised model (class-weighted for imbalance)
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    xgb = XGBClassifier(n_estimators=250, max_depth=4, learning_rate=.08, subsample=.9, colsample_bytree=.9,
                        scale_pos_weight=spw, eval_metric="aucpr", random_state=42, n_jobs=-1)
    xgb.fit(Xtr, ytr)
    F["model_prob"] = xgb.predict_proba(F[FEATURES])[:, 1]

    # --- unsupervised anomaly detector (emerging patterns): fitted on training window only
    A = _anom_matrix(F)
    iso = IsolationForest(n_estimators=200, contamination="auto", random_state=42, n_jobs=-1).fit(A[tr])
    tr_scores = np.sort(-iso.score_samples(A[tr]))
    F["anomaly_raw"] = -iso.score_samples(A)
    F["anomaly_pct"] = np.searchsorted(tr_scores, F.anomaly_raw) / len(tr_scores)
    F["anomaly_flag"] = (F.anomaly_pct >= .995).astype(int)

    # --- scam-type multiclass (trained on labelled fraud rows only)
    fr = tr & (F.is_fraud == 1)
    le = LabelEncoder().fit(F.loc[fr, "scam_type"])
    clf = XGBClassifier(n_estimators=150, max_depth=4, learning_rate=.1, objective="multi:softprob",
                        random_state=42, n_jobs=-1).fit(F.loc[fr, FEATURES], le.transform(F.loc[fr, "scam_type"]))
    F["scam_ml"] = le.inverse_transform(clf.predict(F[FEATURES]))

    # --- combine
    fs = np.maximum(F.rule_score, F.model_prob) + .1 * F.anomaly_flag
    unknown = (F.anomaly_flag == 1) & (F.rule_fired == 0) & (F.model_prob < .5)
    fs = np.where(unknown, np.maximum(fs, .5), fs)           # unknown anomalies surface for step-up review
    F["fraud_score"] = np.clip(fs, 0, 1).round(4)
    stype = np.where(F.rule_fired == 1, F.rule_type, F.scam_ml)
    stype = np.where(unknown, "unknown_anomaly", stype)
    F["scam_type_pred"] = np.where(F.fraud_score >= .5, stype, "none")
    F["action"] = np.select([F.fraud_score > .85, F.fraud_score >= .5], ["HOLD", "STEP-UP"], "ALLOW")

    # --- evaluation on the held-out (later) period
    T = F[te]
    fraud_t = T[T.is_fraud == 1]
    per_type = {t: round(float((g.fraud_score >= .5).mean()), 3) for t, g in fraud_t.groupby("scam_type")}
    metrics = dict(
        split_time=str(split), n_train=int(tr.sum()), n_test=int(te.sum()), test_fraud=int(T.is_fraud.sum()),
        rules_only=_metrics(T.is_fraud, T.rule_score), xgboost_only=_metrics(T.is_fraud, T.model_prob),
        hybrid=_metrics(T.is_fraud, T.fraud_score), recall_by_scam_type=per_type,
        scam_type_accuracy=round(float((fraud_t.scam_ml == fraud_t.scam_type).mean()), 3),
        anomaly_flag_rate_test=round(float(T.anomaly_flag.mean()), 4),
        unknown_anomaly_alerts=int((T.scam_type_pred == "unknown_anomaly").sum()))
    return F, metrics, dict(xgb=xgb, iso=iso, clf=clf, le=le)
