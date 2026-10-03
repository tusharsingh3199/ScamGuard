"""Phase 3a - Rule layer for KNOWN scams. One rule per scam; each gives (fired, scam_type, score, reason).
Vectorised so it can score 50k events instantly; the highest-scoring rule wins.
"""
import numpy as np
import pandas as pd

RULES = {   # name: (score, human-readable reason)
    "impersonation": (.93, "Impersonation pattern: new/remote-access device + large transfer to a never-seen payee"),
    "cross_channel": (.90, "Cross-channel chain: wallet top-up followed by transfers to new payees across channels within the hour"),
    "mule_account": (.90, "Mule pattern: many small credits from different senders, then rapid outflow"),
    "fake_refund": (.88, "Fake-refund pattern: UPI collect request from a new payee mentioning a 'refund'"),
    "payment_request": (.86, "Payment-request scam: collect request from a new payee with urgency/KYC wording"),
    "phishing": (.85, "Phishing pattern: new device followed by rapid repeated transfers"),
    "investment_scam": (.80, "Investment-scam pattern: repeated, escalating transfers to the same new merchant"),
}
MULE_INBOUND_SCORE = .75


def apply_rules(f: pd.DataFrame) -> pd.DataFrame:
    d = f.direction.eq("debit")
    c = ~d
    new = f.new_payee == 1
    m = {
        "impersonation": d & new & (f.amount_ratio >= 6) & ((f.remote_app_flag == 1) | ((f.device_age_hours < 2) & (f.is_night == 1))),
        "cross_channel": d & new & (f.amount_ratio >= 3) & ((f.channels_used_1hr >= 3) | (f.wallet_topup_then_transfer == 1)),
        "mule_account": d & (f.inbound_unique_senders_24h >= 6) & (f.amount >= .4 * f.inbound_total_24h),
        "fake_refund": d & new & (f.is_collect == 1) & (f.note_refund == 1),
        "payment_request": d & new & (f.is_collect == 1) & (f.note_urgent == 1),
        "phishing": d & ((f.device_changed == 1) | (f.device_age_hours < 1)) & (f.txns_last_10min >= 2) & (f.amount_ratio >= 1),
        "investment_scam": d & (f.payee_txn_count_14d >= 2) & (f.escalation_ratio >= 1.15) & (f.payee_age_days < 90),
    }
    names = list(RULES)
    S = np.column_stack([m[n].to_numpy() * RULES[n][0] for n in names])
    mule_in = (c & (f.inbound_unique_senders_24h >= 6)).to_numpy()
    S = np.column_stack([S, mule_in * MULE_INBOUND_SCORE])           # extra column for inbound mule credits
    best = S.argmax(1)
    score = S.max(1)
    fired = score > 0
    all_names = names + ["mule_account"]
    rtype = np.where(fired, np.array(all_names)[best], "none")
    reason = np.where(fired, np.array([RULES[n][1] for n in names] + [RULES["mule_account"][1]])[best], "")
    return pd.DataFrame(dict(rule_fired=fired.astype(int), rule_type=rtype, rule_score=score, rule_reason=reason),
                        index=f.index)
