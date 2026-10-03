"""Phase 6 - Intervention / case management on SQLite.
Policy:  fraud >0.85 -> HOLD + investigate + alert | fraud 0.5-0.85 -> step-up auth + soft alert
         repayment Medium -> automated reminder   | repayment High -> counsellor call + restructuring offer
"""
import json
import os
import sqlite3

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "scamguard.db")

SCHEMA = """CREATE TABLE IF NOT EXISTS cases(
 case_id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, customer_name TEXT, type TEXT, category TEXT,
 risk_score REAL, amount REAL, reasons TEXT, summary TEXT, recommended_action TEXT,
 status TEXT DEFAULT 'Open', assignee TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT, ref TEXT)"""


def conn():
    return sqlite3.connect(DB)


def init_db():
    with conn() as c:
        c.execute("DROP TABLE IF EXISTS cases")
        c.execute(SCHEMA)


def restructure_offer(outstanding, rate, tenure_left, emi, extra_months=12):
    """Extend the tenure by `extra_months` and recompute the EMI (standard amortisation)."""
    r = rate / 1200
    n = int(tenure_left) + extra_months
    new = outstanding * r / (1 - (1 + r) ** -n)
    return dict(old_tenure=int(tenure_left), new_tenure=n, old_emi=float(emi), new_emi=round(float(new), 0))


def create_cases(scored, borrowers, customers):
    """Fraud cases are grouped per customer/day/scam-type so analysts see incidents, not single txns."""
    init_db()
    names = customers.set_index("customer_id").name.to_dict()
    rows = []
    al = scored[scored.fraud_score >= .5].copy()
    al["day"] = al.timestamp.dt.date
    for (c, day, st), g in al.groupby(["customer_id", "day", "scam_type_pred"]):
        top = g.sort_values("fraud_score", ascending=False).iloc[0]
        sc = float(top.fraud_score)
        if st == "mule_account":
            act = "FREEZE outward transfers + investigate mule ring + alert customer"
        elif sc > .85:
            act = "HOLD transaction + open investigation + SMS/app alert to customer"
        else:
            act = "Step-up authentication (OTP + liveness) + soft alert to customer"
        rows.append((c, names.get(c, ""), "fraud", st, sc, float(g[g.direction == "debit"].amount.sum()), top.reasons,
                     top.summary, act, "Open", "", "", str(g.timestamp.min()), ",".join(g.txn_id.head(8))))
    for b in borrowers[borrowers.risk_band != "Low"].itertuples():
        reasons, summ = b.reasons, b.summary
        if b.risk_band == "High":
            o = restructure_offer(b.outstanding, b.interest_rate, b.tenure_left, b.emi)
            act = (f"Counsellor call + restructuring offer: extend tenure {o['old_tenure']}->{o['new_tenure']} months, "
                   f"EMI Rs {o['old_emi']:,.0f} -> Rs {o['new_emi']:,.0f}")
        else:
            act = "Automated EMI reminder + follow-up call in 3 days"
        rows.append((b.customer_id, names.get(b.customer_id, ""), "loan", b.risk_band, float(b.repayment_risk),
                     float(b.outstanding), reasons, summ, act, "Open", "", "", str(pd.Timestamp(b.today)), b.loan_id))
    with conn() as c:
        c.executemany("""INSERT INTO cases(customer_id,customer_name,type,category,risk_score,amount,reasons,summary,
                      recommended_action,status,assignee,notes,created_at,ref) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    return len(rows)


def list_cases():
    with conn() as c:
        return pd.read_sql("SELECT * FROM cases ORDER BY risk_score DESC, case_id", c)


def update_case(case_id, status=None, assignee=None, note=None):
    with conn() as c:
        if status:
            c.execute("UPDATE cases SET status=? WHERE case_id=?", (status, case_id))
        if assignee is not None:
            c.execute("UPDATE cases SET assignee=? WHERE case_id=?", (assignee, case_id))
        if note:
            old = c.execute("SELECT notes FROM cases WHERE case_id=?", (case_id,)).fetchone()[0] or ""
            stamp = pd.Timestamp.now().strftime("%d %b %H:%M")
            c.execute("UPDATE cases SET notes=? WHERE case_id=?", ((old + "\n" if old else "") + f"[{stamp}] {note}", case_id))
