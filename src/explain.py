"""Phase 5 - Explainability. TreeSHAP contributions (XGBoost's native `pred_contribs`, i.e. exact
TreeSHAP values in log-odds units) -> top positive drivers -> plain-English reason strings.
A template returns None when the feature value is not actually risky, so we never print a
reason that contradicts the data."""
import numpy as np
import xgboost as xgb


def contribs(model, X):
    """SHAP values per row (n_rows x n_features); log-odds contribution to the risk score."""
    return model.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[:, :-1]


def _ago(h):
    return f"{h * 60:.0f} min ago" if h < 2 else f"{h:.0f} h ago"


FRAUD_T = {
    "amount_ratio": lambda r: f"Amount is {r['amount_ratio']:.1f}x this customer's normal" if r["amount_ratio"] >= 3 else None,
    "new_payee": lambda r: "Payment to a never-seen payee" if r["new_payee"] else None,
    "payee_risk": lambda r: f"Payee has a high risk score ({r['payee_risk']:.2f})" if r["payee_risk"] > .3 else None,
    "payee_age_days": lambda r: f"Payee account is only {r['payee_age_days']:.0f} days old" if r["payee_age_days"] < 60 else None,
    "device_changed": lambda r: "First use of this device on the customer's account" if r["device_changed"] else None,
    "device_age_hours": lambda r: f"Device first seen {_ago(r['device_age_hours'])}" if r["device_age_hours"] < 24 else None,
    "remote_app_flag": lambda r: "Remote-access app detected on the device" if r["remote_app_flag"] else None,
    "emulator_flag": lambda r: "Device looks like an emulator" if r["emulator_flag"] else None,
    "is_night": lambda r: "Late-night activity" if r["is_night"] else None,
    "txns_last_10min": lambda r: f"{r['txns_last_10min']:.0f} transactions within 10 minutes" if r["txns_last_10min"] >= 2 else None,
    "txns_last_1hr": lambda r: f"{r['txns_last_1hr']:.0f} transactions within an hour" if r["txns_last_1hr"] >= 3 else None,
    "total_outflow_1hr_all_channels": lambda r: f"Rs {r['total_outflow_1hr_all_channels']:,.0f} moved out in the last hour across all channels" if r["total_outflow_1hr_all_channels"] >= 10000 else None,
    "channels_used_1hr": lambda r: f"{r['channels_used_1hr']:.0f} different channels used within one hour" if r["channels_used_1hr"] >= 3 else None,
    "wallet_topup_then_transfer": lambda r: "Transfer right after a wallet top-up" if r["wallet_topup_then_transfer"] else None,
    "amount_to_income_ratio": lambda r: f"Amount equals {r['amount_to_income_ratio'] * 100:.0f}% of monthly income" if r["amount_to_income_ratio"] >= .3 else None,
    "device_shared_across_customers": lambda r: f"Same device used by {r['device_shared_across_customers']:.0f} different customers" if r["device_shared_across_customers"] >= 2 else None,
    "inbound_unique_senders_24h": lambda r: f"Money received from {r['inbound_unique_senders_24h']:.0f} different senders in 24h" if r["inbound_unique_senders_24h"] >= 4 else None,
    "inbound_total_24h": lambda r: f"Rs {r['inbound_total_24h']:,.0f} received in 24h" if r["inbound_total_24h"] >= 10000 else None,
    "payee_txn_count_14d": lambda r: f"{r['payee_txn_count_14d'] + 1:.0f}th transfer to the same payee in 14 days" if r["payee_txn_count_14d"] >= 2 else None,
    "escalation_ratio": lambda r: f"Amount is {r['escalation_ratio']:.1f}x the previous transfer to this payee" if r["escalation_ratio"] >= 1.2 else None,
    "is_collect": lambda r: "UPI collect (pull) request" if r["is_collect"] else None,
    "note_refund": lambda r: "'Refund' wording in the payment note" if r["note_refund"] else None,
    "note_urgent": lambda r: "Urgency / KYC wording in the payment note" if r["note_urgent"] else None,
}

LOAN_T = {
    "income_change_30d": lambda r: f"Income down {abs(r['income_change_30d']) * 100:.0f}% in the last 30 days" if r["income_change_30d"] <= -.05 else None,
    "income_change_60d": lambda r: f"Income down {abs(r['income_change_60d']) * 100:.0f}% in 60 days" if r["income_change_60d"] <= -.05 else None,
    "spend_change": lambda r: f"Spending up {r['spend_change'] * 100:.0f}% while income fell" if r["spend_change"] > .05 and r["income_change_60d"] < 0 else None,
    "spend_to_income": lambda r: f"Spending is {r['spend_to_income'] * 100:.0f}% of income" if r["spend_to_income"] > .7 else None,
    "cash_advance_trend": lambda r: f"Cash-advance use up {r['cash_advance_trend'] * 100:.1f} pts of income" if r["cash_advance_trend"] >= .02 else None,
    "debt_to_income": lambda r: f"Total debt is {r['debt_to_income']:.1f}x annual income" if r["debt_to_income"] > .8 else None,
    "emi_to_income": lambda r: f"EMI takes {r['emi_to_income'] * 100:.0f}% of income" if r["emi_to_income"] > .3 else None,
    "late_count_90d": lambda r: f"{r['late_count_90d']:.0f} late/missed EMIs in the last 90 days" if r["late_count_90d"] >= 1 else None,
    "missed_count": lambda r: f"{r['missed_count']:.0f} missed EMI(s)" if r["missed_count"] >= 1 else None,
    "last_emi_dpd": lambda r: f"Latest EMI paid {r['last_emi_dpd']:.0f} days late" if r["last_emi_dpd"] >= 1 else None,
    "max_dpd": lambda r: f"Worst delay: {r['max_dpd']:.0f} days past due" if r["max_dpd"] >= 5 else None,
}


def top_reasons(row, contrib_vec, feats, templates, k=4, min_c=.05):
    """Return [(text, contribution)] for the strongest risk-increasing, still-risky features."""
    out = []
    total = float(contrib_vec[contrib_vec > 0].sum()) or 1.0      # each driver reported as share of the total risk push
    for i in np.argsort(-contrib_vec):
        if contrib_vec[i] < min_c:
            break
        fn = templates.get(feats[i])
        txt = fn(row) if fn else None
        if txt:
            out.append((txt, float(contrib_vec[i]) / total))
        if len(out) >= k:
            break
    return out


def fmt(reasons):
    return [f"{t} (+{c * 100:.0f}%)" for t, c in reasons]


def fraud_summary(scam, score, reasons, amount):
    label = scam.replace("_", " ")
    head = f"Flagged as possible {label} (risk {score:.2f}) on a Rs {amount:,.0f} transaction"
    return head + (": " + "; ".join(r.split(" (+")[0].lower() for r in reasons[:2]) + "." if reasons else ".")


def loan_summary(p, band, reasons):
    head = f"{band} repayment risk ({p:.2f})"
    return head + (": " + "; ".join(r.split(" (+")[0].lower() for r in reasons[:2]) + "." if reasons else ".")
