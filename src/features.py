"""Phase 2b - Cross-channel streaming features.

Events are processed in global time order; every feature for an event uses ONLY that customer's
past events (plus the current event itself) -> no label or future leakage.
"""
from collections import defaultdict, deque
from math import sqrt

import numpy as np
import pandas as pd

H = 3600.0
FEATURES = [
    "amount", "amount_zscore", "amount_ratio", "amount_to_income_ratio", "new_payee", "payee_risk", "payee_age_days",
    "device_changed", "device_age_hours", "remote_app_flag", "emulator_flag", "device_shared_across_customers",
    "hour_of_day", "is_night", "txns_last_10min", "txns_last_1hr", "total_outflow_1hr_all_channels",
    "channels_used_1hr", "wallet_topup_then_transfer", "inbound_unique_senders_24h", "inbound_total_24h",
    "payee_txn_count_14d", "escalation_ratio", "is_collect", "note_refund", "note_urgent", "is_credit",
    "ch_UPI", "ch_CARD", "ch_WALLET", "ch_NETBANK"]


def build_features(u, customers, devices, payees):
    inc = customers.set_index("customer_id").monthly_income.to_dict()
    pr = payees.set_index("payee_id")
    risk, page = pr.risk_score.to_dict(), pr.age_days.to_dict()
    dv = devices.set_index("device_id")
    dfirst = pd.to_datetime(dv.first_seen, format="ISO8601").to_dict()
    remote, emu = dv.is_remote_access_app.to_dict(), dv.is_emulator.to_dict()
    t_min = u.timestamp.min()
    seen_dev = defaultdict(set)                       # devices registered before the observation window
    for r in devices.itertuples():
        if pd.Timestamp(r.first_seen) < t_min and r.device_id.startswith("D") and not r.device_id.startswith(("DX", "D_")):
            seen_dev[r.customer_id].add(r.device_id)
    dev_users = defaultdict(set)
    state, out = {}, []

    for r in u.itertuples(index=False):
        c = r.customer_id
        s = state.get(c)
        if s is None:
            s = state[c] = dict(n=0, mean=0.0, m2=0.0, seen=set(), ev=deque(), pp=defaultdict(list))
        ts, amt, debit = r.timestamp, r.amount, r.direction == "debit"
        t = ts.timestamp()
        # --- amount vs the customer's own history (past debits only)
        if s["n"] >= 5:
            mean = s["mean"]
            sd = max(sqrt(s["m2"] / (s["n"] - 1)), .25 * mean)
            z = float(np.clip((amt - mean) / sd, -5, 50))
        else:
            mean, z = max(inc[c] * .0625, 1.0), 0.0
        ratio = amt / max(mean, 1.0)
        new_payee = int(r.payee_id not in s["seen"] and r.payee_type != "salary")
        # --- device
        if r.channel == "CARD":
            dchg, dage, shared, rem, em = 0, 2160.0, 1, 0, 0
        else:
            dchg = int(r.device_id not in seen_dev[c])
            dage = float(np.clip((ts - dfirst.get(r.device_id, ts)).total_seconds() / H, 0, 2160))
            shared = len(dev_users[r.device_id] | {c})
            rem, em = remote.get(r.device_id, 0), emu.get(r.device_id, 0)
        # --- sliding windows (24h kept)
        ev = s["ev"]
        while ev and t - ev[0][0] > 24 * H:
            ev.popleft()
        n10 = 1 + sum(1 for e in ev if t - e[0] <= 600)
        n60 = 1 + sum(1 for e in ev if t - e[0] <= H)
        out1 = (amt if debit else 0.0) + sum(e[1] for e in ev if t - e[0] <= H and e[3] == "debit")
        chs = {r.channel} | {e[2] for e in ev if t - e[0] <= H}
        topup = int(debit and r.channel in ("UPI", "NETBANK") and
                    any(e[5] == "wallet_topup" and t - e[0] <= 1800 for e in ev))
        senders = {e[4] for e in ev if e[3] == "credit" and e[5] != "salary"}
        in_tot = sum(e[1] for e in ev if e[3] == "credit" and e[5] != "salary")
        if (not debit) and r.payee_type != "salary":
            senders.add(r.payee_id)
            in_tot += amt
        prior = [x for x in s["pp"][r.payee_id] if t - x[0] <= 14 * 86400] if debit else []
        esc = amt / max(prior[-1][1], 1.0) if prior else 1.0
        note = (r.note or "").lower()
        out.append((r.txn_id, amt, z, ratio, amt / inc[c], new_payee, risk.get(r.payee_id, .1), page.get(r.payee_id, 1000),
                    dchg, dage, rem, em, shared, ts.hour, int(ts.hour >= 22 or ts.hour < 5), n10, n60, out1, len(chs),
                    topup, len(senders), in_tot, len(prior), esc, int(r.is_collect), int("refund" in note),
                    int(any(w in note for w in ("urgent", "kyc", "verify"))), int(not debit),
                    int(r.channel == "UPI"), int(r.channel == "CARD"), int(r.channel == "WALLET"), int(r.channel == "NETBANK")))
        # --- update state AFTER feature computation
        if debit:
            s["n"] += 1
            dlt = amt - s["mean"]
            s["mean"] += dlt / s["n"]
            s["m2"] += dlt * (amt - s["mean"])
            s["pp"][r.payee_id].append((t, amt))
        s["seen"].add(r.payee_id)
        ev.append((t, amt, r.channel, r.direction, r.payee_id, r.payee_type))
        if r.channel != "CARD":
            seen_dev[c].add(r.device_id)
            dev_users[r.device_id].add(c)
    F = pd.DataFrame(out, columns=["txn_id"] + FEATURES)
    return F
