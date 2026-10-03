# ScamGuard: Financial Scam Detection and Loan Risk Management

ScamGuard combines a synthetic-data fraud monitoring pipeline, borrower repayment-risk scoring, and intervention case management in one dashboard.

- **Transaction monitoring:** Unified UPI, card, wallet, and netbanking feeds with rules, behavioral features, model scores, and scam classifications.
- **Loan monitoring:** Outstanding balances, upcoming EMIs, delayed repayments, and early-warning indicators for income, spending, and debt changes.
- **Explainability:** Transaction and repayment alerts include feature-based reasons and summaries.
- **Interventions:** SQLite-backed cases support assignment, notes, reminders, restructuring, escalation, resolution, and reopening.
- **Web dashboard:** React screens for transaction replay, scam trends, Customer 360, borrower health, and case management.

## Run Locally

Requirements: Python 3.10 or newer and Node.js 20 or newer.

Create and activate a Python environment, then install the backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The generated demo database and metrics are included. If you need to regenerate them, run these commands from the project root:

```powershell
python -m src.generate_data
python -m src.pipeline
```

Running the pipeline rebuilds the intervention case queue in `data/scamguard.db`.

Start the API in one terminal from the project root:

```powershell
python -m uvicorn app:app --reload
```

Install frontend packages once, then start Vite in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`. The frontend proxies `/api` requests to `http://127.0.0.1:8000`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

To create a production frontend bundle, run `npm run build` from `frontend/`; the output is written to `frontend/dist/`.

## Dashboard Workflows

1. **Transaction monitor:** Filter the chronological scored feed by channel or alert status, then replay a sample at a selected speed. This is a replay of pre-scored events, not a live payment stream.
2. **Scam trends:** Compare classifications over time and channel, review risky payees, inspect channel-to-payee-to-action flows, and explore the generated mule graph.
3. **Customer 360:** Inspect fraud and repayment risk, the strongest available explanations, borrower warnings, and a combined transaction/repayment timeline.
4. **Loans and interventions:** Review upcoming and delayed payments, warning aggregates, borrower risk bands, and case histories. Case actions persist in SQLite.

## Architecture

```text
Synthetic raw feeds and customer/loan data
  -> Python adapters and feature engineering
  -> fraud rules/models and repayment model
  -> scored SQLite tables and JSON metrics/graph artifacts
  -> FastAPI read/write API
  -> Vite + React dashboard
```

Generate and score data separately with `python -m src.generate_data` and `python -m src.pipeline`. The web API reads the generated artifacts and updates cases; it does not train models or create cases at startup. Fraud and repayment models remain in Python.

## Results and Limitations

The included data is fully synthetic, with scam patterns injected by design. Metrics in `data/metrics.json` are demonstration results, not real-world accuracy claims. The transaction monitor replays already-scored events; it is not Kafka/Flink or live transaction processing. Identity resolution uses a lookup table. The analyst copilot uses deterministic templates and makes no network calls. Isolation Forest rarely fires on the current generated patterns.

This project is a demo, not a production financial monitoring service. It has no authentication or authorization and must not be connected to real customer data without a security, privacy, model-risk, and operational review.
