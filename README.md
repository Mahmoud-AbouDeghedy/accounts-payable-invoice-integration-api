# AP Invoice Integration API

A FastAPI integration layer for synchronizing ERP master data and invoice records into an accounts payable automation workflow.

The project focuses on API reliability, idempotent sync behavior, referential integrity, VAT validation, and structured audit-friendly logging. It is a compact backend project that mirrors the kind of service used between finance systems, ERP platforms, and AP automation tools.

## Features

- Idempotent upsert endpoints for vendors, tax codes, nominal accounts, and departments.
- Atomic invoice posting with all-or-nothing persistence.
- VAT validation for invoice lines based on configured tax-code rates.
- Bulk invoice ingestion with per-invoice success, skip, and failure reporting.
- Paginated invoice listing and invoice lookup by external invoice ID.
- Structured JSON logging for operational traceability.
- Health endpoints for readiness and database connectivity checks.
- CSV seeding utility for local testing and sample data ingestion.

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite / PostgreSQL-ready database URL
- Uvicorn
- Pandas
- Pytest
- REST APIs
- Structured JSON logging

## Project Structure

```text
app/
  core/          Configuration and JSON logging
  models/        SQLAlchemy ORM models
  routers/       FastAPI route modules
  schemas/       Pydantic request/response schemas
  services/      Upsert, VAT validation, and invoice posting logic
  database.py    Engine, session, and base model setup
  main.py        FastAPI application entry point
scripts/
  seed_from_csv.py
requirements.txt
```

## API Overview

### Master Data

- `POST /vendors`
- `POST /tax-codes`
- `POST /accounts`
- `POST /departments`

Each master-data endpoint is designed for safe retries through idempotent upsert behavior.

### Invoices

- `POST /invoices`
- `POST /invoices/bulk`
- `GET /invoices`
- `GET /invoices/{external_invoice_id}`

Invoice posting validates vendor, account, tax-code, and department references before committing the transaction.

### Health

- `GET /`
- `GET /health`

## Getting Started

### 1. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

On macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file:

```env
DATABASE_URL=sqlite:///./ap_entries.db
LOG_LEVEL=INFO
APP_NAME=AP Invoice Integration API
APP_VERSION=1.0.0
```

### 4. Run the API

```bash
uvicorn app.main:app --reload
```

Open the Swagger docs:

```text
http://localhost:8000/docs
```

### 5. Seed data from CSV

```bash
python scripts/seed_from_csv.py --csv path/to/line_items.csv
```

## Design Notes

- `external_id` fields are used as integration keys for ERP-originated records.
- Invoice posting is wrapped in validation logic so failed records do not create partial invoice state.
- Bulk ingestion processes each invoice independently and returns a structured report.
- Logging is emitted as JSON to make the service easier to plug into observability tooling.

## Why This Project Matters

This project is useful as portfolio evidence for backend roles involving finance integrations, REST API design, data validation, SQL-backed services, idempotency, and production-minded error handling.
