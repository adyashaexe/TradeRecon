# TradeRecon — Trade Reconciliation Engine

A full-stack trade reconciliation system that matches internal trade blotters against broker confirms, classifies breaks, and produces structured exception reports — simulating core workflows in banking operations (Payments, Settlement, Collateral Management).

## What It Does

Upload two CSV files — an **internal trade blotter** and a **broker confirmation file** — and TradeRecon will:

- Match trades by `trade_id` across both sources
- Classify every discrepancy as a typed break:
  - `PRICE_MISMATCH` — price difference exceeds 1% tolerance
  - `QTY_MISMATCH` — quantity differs between sources
  - `SIDE_MISMATCH` — buy/sell direction conflict
  - `SETTLE_DATE_MISMATCH` — settlement date differs
  - `MISSING_IN_BROKER` — trade exists internally but broker has no confirm
  - `MISSING_IN_INTERNAL` — broker has a confirm with no matching internal record
- Calculate match rate and break statistics
- Display a filterable, searchable break report dashboard

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Pandas |
| Frontend | React 18, IBM Plex Mono |
| Data | CSV upload, in-memory processing |
| Deploy | Docker Compose |

## Project Structure

```
TradeRecon/
├── backend/
│   ├── app.py              # Flask API + reconciliation engine
│   └── requirements.txt
├── frontend/
│   └── src/
│       └── App.jsx         # React dashboard
├── data/
│   ├── sample_internal.csv
│   └── sample_broker.csv
└── docker-compose.yml
```

## Running Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
python app.py
# API running at http://localhost:5000
```

### Frontend
```bash
cd frontend
npm install
npm start
# App running at http://localhost:3000
```

### Docker (full stack)
```bash
docker-compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/reconcile` | Upload internal + broker CSVs, returns full recon report |
| GET | `/api/sample` | Returns sample CSV data for testing |
| GET | `/api/health` | Health check |

## CSV Format

**Required columns:** `trade_id`, `symbol`, `side`, `quantity`, `price`

**Optional columns:** `settlement_date`

```csv
trade_id,symbol,side,quantity,price,settlement_date
T001,AAPL,BUY,100,182.50,2026-05-06
T002,MSFT,SELL,200,415.30,2026-05-06
```

## Key Engineering Decisions

- **Pandas-based matching engine** — O(n) dictionary lookup on `trade_id`, avoiding O(n²) row scanning
- **Typed break classification** — each break type has a distinct code for downstream triage and SLA tracking
- **Price tolerance** — configurable % threshold (default 1%) to handle rounding differences between systems
- **Decoupled architecture** — matching engine, API layer, and frontend are independently testable
- **SMOTE-style class handling** — break types are tracked and counted separately to avoid masking rare break categories in summary statistics

## Relevance to Banking Operations

This project simulates the reconciliation workflows performed daily by Operations teams at financial institutions:

| This Project | Real-World Equivalent |
|---|---|
| Internal blotter vs broker confirms | Front-office system vs prime broker confirms |
| `MISSING_IN_BROKER` breaks | Unconfirmed trades requiring chasing |
| `PRICE_MISMATCH` breaks | Economic disputes needing resolution |
| Settlement date mismatches | T+2 settlement failure risk |
| Exception report | Daily break report sent to ops managers |
| Alerting layer | Escalation to senior ops / risk teams |
