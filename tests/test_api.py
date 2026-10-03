import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.temp_dir.name, "test.db")
        self.original_db = api.iv.DB
        api.iv.DB = self.database
        self._create_database()
        self.artifact_patch = patch.object(api, "_json_file", side_effect=self._artifact)
        self.artifact_patch.start()
        self.client = TestClient(api.app)

    def tearDown(self):
        self.artifact_patch.stop()
        api.iv.DB = self.original_db
        self.temp_dir.cleanup()

    def _create_database(self):
        with sqlite3.connect(self.database) as connection:
            connection.executescript(
                """
                CREATE TABLE customers(customer_id TEXT, name TEXT, age INTEGER, city TEXT,
                    occupation TEXT, monthly_income REAL, account_age_days INTEGER, phone TEXT);
                CREATE TABLE scored_transactions(txn_id TEXT, customer_id TEXT, timestamp TEXT,
                    channel TEXT, direction TEXT, amount REAL, payee_id TEXT, payee_type TEXT,
                    note TEXT, fraud_score REAL, scam_type_pred TEXT, action TEXT, reasons TEXT, summary TEXT);
                CREATE TABLE payees(payee_id TEXT, category TEXT, age_days INTEGER, is_mule INTEGER);
                CREATE TABLE borrower_scores(loan_id TEXT, customer_id TEXT, outstanding REAL, emi REAL,
                    repayment_risk REAL, risk_band TEXT, currently_overdue INTEGER, warnings TEXT,
                    days_to_next_emi INTEGER, next_due_date TEXT, delayed_flag INTEGER, last_emi_dpd INTEGER,
                    last_emi_status TEXT, late_count_90d INTEGER, income_change_60d REAL, emi_to_income REAL,
                    reasons TEXT, summary TEXT);
                CREATE TABLE repayments(loan_id TEXT, due_date TEXT, paid_date TEXT, status TEXT, days_past_due INTEGER);
                CREATE TABLE cases(case_id INTEGER PRIMARY KEY, customer_id TEXT, customer_name TEXT,
                    type TEXT, category TEXT, risk_score REAL, amount REAL, reasons TEXT, summary TEXT,
                    recommended_action TEXT, status TEXT, assignee TEXT, notes TEXT, created_at TEXT, ref TEXT);
                INSERT INTO customers VALUES('C1', 'Asha Rao', 31, 'Pune', 'Analyst', 50000, 900, '000');
                INSERT INTO payees VALUES('P1', 'Retail', 30, 0);
                INSERT INTO scored_transactions VALUES
                    ('T1', 'C1', '2026-01-01T10:00:00', 'UPI', 'debit', 1200, 'P1', 'merchant', '', 0.8, 'phishing', 'HOLD', '["new payee"]', 'Flagged'),
                    ('T2', 'C1', '2026-01-02T10:00:00', 'CARD', 'debit', 400, 'P1', 'merchant', '', 0.1, 'none', 'ALLOW', '[]', 'Normal');
                INSERT INTO borrower_scores VALUES
                    ('L1', 'C1', 20000, 2000, 0.7, 'High', 1, 'income fell', 4,
                     '2026-01-06', 1, 8, 'late', 2, -0.2, 0.4, '["late EMI"]', 'Repayment concern');
                INSERT INTO repayments VALUES('L1', '2026-01-01', '2026-01-09', 'late', 8);
                INSERT INTO cases VALUES(1, 'C1', 'Asha Rao', 'fraud', 'phishing', 0.8, 1200,
                    '["new payee"]', 'Flagged', 'Investigate', 'Open', '', '', '2026-01-01', 'T1');
                """
            )

    @staticmethod
    def _artifact(name):
        return {"metrics.json": {"fraud": {}, "loan": {}, "data": {}},
                "meta.json": {"demo_customer": "C1"},
                "mule_graph.json": {"nodes": [], "edges": [], "mules": [], "rings": 0}}[name]

    def test_dashboard_transaction_filters_and_trends(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)
        result = self.client.get("/api/transactions?flagged=true&limit=5").json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["txn_id"], "T1")
        trends = self.client.get("/api/trends").json()
        self.assertEqual(trends["by_channel"][0]["channel"], "UPI")
        self.assertEqual(trends["graph"]["rings"], 0)

    def test_customer_and_loan_views(self):
        customers = self.client.get("/api/customers").json()
        self.assertEqual(customers[0]["peak_fraud_risk"], 0.8)
        detail = self.client.get("/api/customers/C1").json()
        self.assertEqual(detail["borrower"]["loan_id"], "L1")
        self.assertEqual(len(detail["repayments"]), 1)
        loans = self.client.get("/api/loans").json()
        self.assertEqual(loans["summary"]["high_risk"], 1)
        self.assertEqual(loans["warning_counts"][0]["warning"], "income fell")

    def test_case_filters_and_updates_persist(self):
        result = self.client.get("/api/cases?type=fraud&status=Open").json()
        self.assertEqual(result["total"], 1)
        updated = self.client.patch("/api/cases/1", json={
            "status": "In Progress", "assignee": "Analyst 1", "note": "Reviewed transaction",
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "In Progress")
        self.assertEqual(updated.json()["assignee"], "Analyst 1")
        persisted = self.client.get("/api/cases?status=In%20Progress").json()["items"][0]
        self.assertIn("Reviewed transaction", persisted["notes"])

    def test_invalid_and_missing_case_updates(self):
        self.assertEqual(self.client.patch("/api/cases/1", json={"status": "Closed"}).status_code, 422)
        self.assertEqual(self.client.patch("/api/cases/999", json={"status": "Resolved"}).status_code, 404)
        self.assertEqual(self.client.get("/api/customers/missing").status_code, 404)


if __name__ == "__main__":
    unittest.main()