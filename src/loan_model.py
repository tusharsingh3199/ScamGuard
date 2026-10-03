"""Phase 4 - Loan engine: tracker, rolling distress features, early-warning badges and a
SEPARATE repayment-risk model (default_within_90d)."""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

LOAN_FEATURES = ["income_change_30d", "income_change_60d", "spend_change", "spend_to_income", "cash_advance_trend",
                 "debt_to_income", "emi_to_income", "late_count_90d", "missed_count", "last_emi_dpd", "max_dpd"]


def build_loan_table(customers, loans, repayments, ie, today):
    """One row per borrower: tracker fields + rolling 30/60-day features."""
    today = pd.Timestamp(today)
    ie = ie.sort_values(["customer_id", "month"])
    rep = repayments.sort_values(["loan_id", "due_date"], ascending=[True, False])   # most recent first
    rows = []
    for ln in loans.itertuples():
        g = ie[ie.customer_id == ln.customer_id]
        i0, i1, i2 = g.income.iloc[0], g.income.iloc[1], g.income.iloc[2]
        s0, s2 = g.spend.iloc[0], g.spend.iloc[2]
        ca0, ca2 = g.cash_advance.iloc[0], g.cash_advance.iloc[2]
        r = rep[rep.loan_id == ln.loan_id]
        bad = r[r.status != "on_time"]
        last3 = r.head(3)
        rows.append(dict(
            loan_id=ln.loan_id, customer_id=ln.customer_id, principal=ln.principal, outstanding=ln.outstanding,
            emi=ln.emi, tenure_left=ln.tenure, interest_rate=ln.interest_rate, next_due_date=ln.next_due_date,
            days_to_next_emi=(pd.Timestamp(ln.next_due_date) - today).days,
            income_now=i2, income_change_30d=i2 / i1 - 1, income_change_60d=i2 / i0 - 1,
            spend_change=s2 / max(s0, 1) - 1, spend_to_income=g.spend.iloc[2] / max(i2, 1),
            cash_advance_trend=ca2 / max(i2, 1) - ca0 / max(i0, 1),
            debt_to_income=g.total_debt.iloc[2] / max(i2 * 12, 1), emi_to_income=ln.emi / max(i2, 1),
            late_count_90d=int((last3.status != "on_time").sum()), missed_count=int((r.status == "missed").sum()),
            last_emi_dpd=int(r.days_past_due.iloc[0]), max_dpd=int(r.days_past_due.max()),
            last_emi_status=r.status.iloc[0], currently_overdue=int(r.status.iloc[0] == "missed"),
            delayed_flag=int(len(bad) > 0)))
    return pd.DataFrame(rows)


def early_warnings(r):
    """Rule-based early-warning badges (shown next to the ML score)."""
    b = []
    if r.income_change_60d <= -.20:
        b.append("Income drop >20%")
    if r.late_count_90d >= 2:
        b.append("2+ late payments")
    if r.emi_to_income > .35:
        b.append("EMI/income >35%")
    if r.cash_advance_trend >= .03:
        b.append("Rising cash advances")
    if r.currently_overdue:
        b.append("EMI missed / overdue")
    if r.debt_to_income > 1.5:
        b.append("High debt load")
    return b


def band(p):
    return "High" if p > .65 else "Medium" if p >= .35 else "Low"


def train_repayment(B, labels, demo_customer):
    B = B.merge(labels[["loan_id", "default_within_90d", "stress_group"]], on="loan_id")
    trainable = B[B.customer_id != demo_customer]
    tr, te = train_test_split(trainable, test_size=.3, stratify=trainable.default_within_90d, random_state=42)
    spw = float((tr.default_within_90d == 0).sum() / max((tr.default_within_90d == 1).sum(), 1))
    m = XGBClassifier(n_estimators=150, max_depth=3, learning_rate=.08, subsample=.9, colsample_bytree=.9,
                      scale_pos_weight=spw, random_state=42, n_jobs=-1, eval_metric="auc")
    m.fit(tr[LOAN_FEATURES], tr.default_within_90d)
    B["repayment_risk"] = m.predict_proba(B[LOAN_FEATURES])[:, 1].round(4)
    B["risk_band"] = B.repayment_risk.map(band)
    B["warnings"] = [", ".join(early_warnings(r)) for r in B.itertuples()]
    p = m.predict_proba(te[LOAN_FEATURES])[:, 1]
    pred = (p >= .5).astype(int)
    pr, rc, f1, _ = precision_recall_fscore_support(te.default_within_90d, pred, average="binary", zero_division=0)
    metrics = dict(n_train=len(tr), n_test=len(te), test_defaults=int(te.default_within_90d.sum()),
                   auc=round(float(roc_auc_score(te.default_within_90d, p)), 4),
                   pr_auc=round(float(average_precision_score(te.default_within_90d, p)), 4),
                   precision=round(float(pr), 4), recall=round(float(rc), 4), f1=round(float(f1), 4),
                   confusion=confusion_matrix(te.default_within_90d, pred).tolist(),
                   band_counts=B.risk_band.value_counts().to_dict())
    return B, metrics, m
