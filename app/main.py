"""
AP Integration API — Entry Point

Architecture overview:
  - Master data (vendors, tax_codes, accounts, departments) synced via idempotent upserts
  - Invoices posted atomically with full referential integrity + VAT validation
  - SQLite (dev) / Postgres (prod) via DATABASE_URL env var
  - Structured JSON logging for full audit trail
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.json_logging import logger
from app.database import engine, Base, SessionLocal
from app.routers import vendors, tax_codes, accounts, departments, invoices


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all tables on startup."""
    logger.info("Starting AP Integration API — creating database tables")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready")
    yield
    logger.info("AP Integration API shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AP Integration Layer

A reliable REST API for synchronizing financial data between an ERP system
and an AP automation platform.

### Key Design Principles
- **Idempotent**: Safe to retry any request — duplicates are detected and returned, not re-inserted
- **Atomic**: Invoice posting is all-or-nothing — one bad line rejects the whole invoice
- **Referential integrity**: Cannot post an invoice with unknown vendor/tax code/account/department
- **VAT validated**: Every line's VAT amount is validated against the tax code rate

### Recommended Sync Order
1. `POST /departments` — sync all departments first
2. `POST /accounts` — sync nominal accounts
3. `POST /tax-codes` — sync tax codes with rates
4. `POST /vendors` — sync vendor master data
5. `POST /invoices` or `POST /invoices/bulk` — post historical entries
""",
    lifespan=lifespan,
    docs_url="/docs",
)

# CORS — restrict in production to your AP platform's domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handler ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", extra={"path": str(request.url)})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": "An unexpected internal error occurred.",
            "detail": str(exc),
        },
    )


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(vendors.router)
app.include_router(tax_codes.router)
app.include_router(accounts.router)
app.include_router(departments.router)
app.include_router(invoices.router)


@app.get("/", tags=["Health"], summary="Health check")
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/health", tags=["Health"], summary="Detailed health check")
def detailed_health(db=None):
    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return {"status": "ok", "database": db_status, "version": settings.APP_VERSION}
