"""Read/write API for the React dashboard over the generated demo artifacts."""
import json
import os
import sqlite3
from contextlib import closing
from typing import Literal, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import interventions as iv

DATA = os.path.join(iv.ROOT, "data")
app = FastAPI(title="ScamGuard API", version="1.0.0")


class CaseUpdate(BaseModel):
    status: Optional[Literal["Open", "In Progress", "Resolved"]] = None
    assignee: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=2000)


def _connect():
    if not os.path.isfile(iv.DB):
        raise HTTPException(status_code=503, detail="Generated database is missing. Run the data pipeline first.")
    connection = sqlite3.connect(iv.DB)
    connection.row_factory = sqlite3.Row
    return connection


def _rows(sql, params=()):
    with closing(_connect()) as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _json_file(name):
    path = os.path.join(DATA, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=503, detail=f"Generated artifact is missing: {name}")
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _records(frame):
    """Convert Pandas values, including timestamps and NaN, into JSON-native values."""
    return json.loads(frame.to_json(orient="records", date_format="iso"))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard():
    return {"metrics": _json_file("metrics.json"), "meta": _json_file("meta.json")}


@app.get("/api/transactions")
def transactions(
    limit: int = Query(default=300, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    customer_id: Optional[str] = None,
    channel: Optional[str] = None,
    action: Optional[str] = None,
    flagged: Optional[bool] = None,
    search: Optional[str] = Query(default=None, max_length=120),
):
    clauses, params = [], []
    if customer_id:
        clauses.append("customer_id = ?")
        params.append(customer_id)
    if channel:
        clauses.append("channel = ?")
        params.append(channel)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if flagged is not None:
        clauses.append("fraud_score >= ?" if flagged else "fraud_score < ?")
        params.append(0.5)
    if search:
        clauses.append("(txn_id LIKE ? OR payee_id LIKE ? OR customer_id LIKE ? OR note LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    count = _rows(f"SELECT COUNT(*) AS total FROM scored_transactions{where}", params)[0]["total"]
    rows = _rows(
        f"SELECT * FROM scored_transactions{where} ORDER BY timestamp, txn_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return {"items": rows, "total": count, "limit": limit, "offset": offset}


@app.get("/api/trends")
def trends(scope: Literal["flagged", "all"] = "flagged"):
    where = " WHERE fraud_score >= 0.5" if scope == "flagged" else ""
    by_day = _rows(
        "SELECT substr(timestamp, 1, 10) AS day, scam_type_pred AS scam_type, COUNT(*) AS alerts "
        f"FROM scored_transactions{where} GROUP BY day, scam_type ORDER BY day"
    )
    by_channel = _rows(
        "SELECT channel, scam_type_pred AS scam_type, COUNT(*) AS alerts "
        f"FROM scored_transactions{where} GROUP BY channel, scam_type ORDER BY channel"
    )
    risky_payees = _rows(
        "SELECT s.payee_id, p.category, p.age_days, p.is_mule AS mule_flag, COUNT(*) AS alerts, "
        "SUM(s.amount) AS amount, MAX(s.fraud_score) AS max_score "
        "FROM scored_transactions s LEFT JOIN payees p ON s.payee_id = p.payee_id "
        "WHERE s.fraud_score >= 0.5 GROUP BY s.payee_id "
        "ORDER BY alerts DESC, amount DESC LIMIT 12"
    )
    flow = _rows(
        "SELECT channel, COALESCE(payee_type, 'other') AS payee_type, "
        "CASE action WHEN 'HOLD' THEN 'Held' WHEN 'STEP-UP' THEN 'Step-up auth' ELSE 'Allowed' END AS outcome, "
        "COUNT(*) AS count FROM scored_transactions" + where + " GROUP BY channel, payee_type, outcome"
    )
    return {
        "by_day": by_day,
        "by_channel": by_channel,
        "risky_payees": risky_payees,
        "flow": flow,
        "graph": _json_file("mule_graph.json"),
    }


@app.get("/api/customers")
def customers():
    return _rows(
        "SELECT c.*, COALESCE(t.peak_fraud_risk, 0) AS peak_fraud_risk, "
        "b.repayment_risk, b.risk_band, b.loan_id "
        "FROM customers c LEFT JOIN (SELECT customer_id, MAX(fraud_score) AS peak_fraud_risk "
        "FROM scored_transactions GROUP BY customer_id) t ON c.customer_id = t.customer_id "
        "LEFT JOIN borrower_scores b ON c.customer_id = b.customer_id ORDER BY peak_fraud_risk DESC, c.name"
    )


@app.get("/api/customers/{customer_id}")
def customer_detail(customer_id: str, transaction_limit: int = Query(default=1500, ge=1, le=3000)):
    customer = _rows("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    borrower = _rows("SELECT * FROM borrower_scores WHERE customer_id = ?", (customer_id,))
    transactions_for_customer = _rows(
        "SELECT * FROM scored_transactions WHERE customer_id = ? ORDER BY timestamp LIMIT ?",
        (customer_id, transaction_limit),
    )
    repayments = []
    if borrower:
        repayments = _rows("SELECT * FROM repayments WHERE loan_id = ? ORDER BY due_date", (borrower[0]["loan_id"],))
    return {
        "customer": customer[0],
        "borrower": borrower[0] if borrower else None,
        "transactions": transactions_for_customer,
        "repayments": repayments,
    }


@app.get("/api/loans")
def loans():
    borrowers = _rows(
        "SELECT b.*, c.name, c.city, c.occupation FROM borrower_scores b "
        "LEFT JOIN customers c ON b.customer_id = c.customer_id ORDER BY b.repayment_risk DESC"
    )
    repayment_rows = _rows("SELECT * FROM repayments ORDER BY due_date")
    warnings = {}
    for borrower in borrowers:
        for warning in (borrower.get("warnings") or "").split(", "):
            if warning:
                warnings[warning] = warnings.get(warning, 0) + 1
    return {
        "borrowers": borrowers,
        "repayments": repayment_rows,
        "warning_counts": [{"warning": key, "borrowers": value} for key, value in sorted(warnings.items(), key=lambda item: -item[1])],
        "summary": {
            "borrowers": len(borrowers),
            "high_risk": sum(row["risk_band"] == "High" for row in borrowers),
            "medium_risk": sum(row["risk_band"] == "Medium" for row in borrowers),
            "outstanding": sum(row["outstanding"] or 0 for row in borrowers),
            "overdue": sum(bool(row["currently_overdue"]) for row in borrowers),
        },
    }


@app.get("/api/cases")
def cases(
    limit: int = Query(default=300, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    type: Optional[Literal["fraud", "loan"]] = None,
    status: Optional[Literal["Open", "In Progress", "Resolved"]] = None,
    assignee: Optional[str] = None,
    search: Optional[str] = Query(default=None, max_length=120),
):
    clauses, params = [], []
    if type:
        clauses.append("type = ?")
        params.append(type)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if assignee == "unassigned":
        clauses.append("COALESCE(assignee, '') = ''")
    elif assignee:
        clauses.append("assignee = ?")
        params.append(assignee)
    if search:
        clauses.append("(customer_name LIKE ? OR customer_id LIKE ? OR category LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    total = _rows(f"SELECT COUNT(*) AS total FROM cases{where}", params)[0]["total"]
    items = _rows(f"SELECT * FROM cases{where} ORDER BY risk_score DESC, case_id LIMIT ? OFFSET ?", [*params, limit, offset])
    summary = _rows("SELECT status, COUNT(*) AS count FROM cases GROUP BY status")
    return {"items": items, "total": total, "limit": limit, "offset": offset, "status_counts": summary}


@app.patch("/api/cases/{case_id}")
def update_case(case_id: int, update: CaseUpdate):
    if update.status is None and update.assignee is None and update.note is None:
        raise HTTPException(status_code=422, detail="Provide at least one case field to update")
    exists = _rows("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
    if not exists:
        raise HTTPException(status_code=404, detail="Case not found")
    iv.update_case(case_id, status=update.status, assignee=update.assignee, note=update.note)
    return _rows("SELECT * FROM cases WHERE case_id = ?", (case_id,))[0]
