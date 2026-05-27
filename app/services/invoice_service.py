"""
Invoice Service — the heart of the integration layer.

Responsibilities:
  1. Idempotency check (return existing if already posted)
  2. Referential integrity validation (vendor, tax codes, accounts, departments)
  3. VAT validation on every line
  4. Atomic transaction — all lines succeed or none do
  5. Structured error accumulation — surface all errors at once, not one at a time
"""
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, Vendor, TaxCode, Account, Department
from app.schemas.invoice import InvoiceCreate, InvoiceLineCreate, InvoiceResponse, InvoiceLineResponse
from app.services.vat_validator import validate_vat, VATValidationError
from app.core.json_logging import logger


class InvoiceValidationError(Exception):
    """Raised when one or more lines fail validation. Contains all errors."""
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__(f"Invoice validation failed with {len(errors)} error(s)")


class InvoiceAlreadyExistsError(Exception):
    """Raised (non-fatally) when the invoice already exists — for idempotent returns."""
    def __init__(self, invoice: Invoice):
        self.invoice = invoice
        super().__init__(f"Invoice {invoice.external_invoice_id!r} already exists")


def _build_line_response(line: InvoiceLine) -> InvoiceLineResponse:
    return InvoiceLineResponse(
        id=line.id,
        description=line.description,
        net_amount=line.net_amount,
        vat_amount=line.vat_amount,
        tax_code_external_id=line.tax_code.external_id,
        nominal_external_id=line.account.external_id,
        department_external_id=line.department.external_id,
    )


def _build_invoice_response(invoice: Invoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=invoice.id,
        external_invoice_id=invoice.external_invoice_id,
        vendor_external_id=invoice.vendor.external_id,
        invoice_date=invoice.invoice_date,
        status=invoice.status,
        lines=[_build_line_response(line) for line in invoice.lines],
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


def post_invoice(db: Session, payload: InvoiceCreate) -> tuple[InvoiceResponse, bool]:
    """
    Post an invoice atomically.

    Returns:
        (InvoiceResponse, is_new) — is_new=False means idempotent duplicate

    Raises:
        InvoiceValidationError — structured list of all validation failures
    """
    # ── 1. Idempotency Check ──────────────────────────────────────────────────
    existing = (
        db.query(Invoice)
        .filter(Invoice.external_invoice_id == payload.external_invoice_id)
        .first()
    )
    if existing:
        logger.info(
            "Idempotent invoice request — returning existing record",
            extra={"external_invoice_id": payload.external_invoice_id},
        )
        # Eager-load relationships for response building
        _ = existing.vendor
        for line in existing.lines:
            _ = line.tax_code
            _ = line.account
            _ = line.department
        return _build_invoice_response(existing), False

    # ── 2. Vendor Lookup ──────────────────────────────────────────────────────
    errors: list[dict] = []

    vendor = db.query(Vendor).filter(Vendor.external_id == payload.vendor_external_id).first()
    if vendor is None:
        errors.append({
            "field": "vendor_external_id",
            "value": payload.vendor_external_id,
            "message": f"Vendor '{payload.vendor_external_id}' not found. Sync vendor master data first.",
        })

    # ── 3. Per-Line Validation (collect ALL errors before rejecting) ──────────
    resolved_lines: list[dict] = []

    for idx, line in enumerate(payload.lines):
        line_errors: list[dict] = []

        # Resolve tax code
        tax_code = db.query(TaxCode).filter(TaxCode.external_id == line.tax_code_external_id).first()
        if tax_code is None:
            line_errors.append({
                "field": f"lines[{idx}].tax_code_external_id",
                "value": line.tax_code_external_id,
                "message": f"Tax code '{line.tax_code_external_id}' not found.",
            })

        # Resolve nominal account
        account = db.query(Account).filter(Account.external_id == line.nominal_external_id).first()
        if account is None:
            line_errors.append({
                "field": f"lines[{idx}].nominal_external_id",
                "value": line.nominal_external_id,
                "message": f"Account '{line.nominal_external_id}' not found.",
            })

        # Resolve department
        department = db.query(Department).filter(Department.external_id == line.department_external_id).first()
        if department is None:
            line_errors.append({
                "field": f"lines[{idx}].department_external_id",
                "value": line.department_external_id,
                "message": f"Department '{line.department_external_id}' not found.",
            })

        # VAT validation — only if tax code resolved (need the rate)
        if tax_code is not None and not line_errors:
            try:
                validate_vat(
                    line_index=idx,
                    description=line.description,
                    net_amount=line.net_amount,
                    vat_amount=line.vat_amount,
                    tax_rate=tax_code.rate,
                )
            except VATValidationError as e:
                line_errors.append({
                    "field": f"lines[{idx}].vat_amount",
                    **e.details,
                })

        if line_errors:
            errors.extend(line_errors)
        else:
            resolved_lines.append({
                "line": line,
                "tax_code": tax_code,
                "account": account,
                "department": department,
            })

    # ── 4. Fail Fast if Any Errors ────────────────────────────────────────────
    if errors:
        logger.warning(
            "Invoice rejected — validation errors",
            extra={
                "external_invoice_id": payload.external_invoice_id,
                "error_count": len(errors),
                "errors": errors,
            },
        )
        raise InvoiceValidationError(errors=errors)

    # ── 5. Atomic Insert ──────────────────────────────────────────────────────
    # The caller (router) manages the transaction boundary (commit/rollback)
    # so this function only adds to the session — never commits itself.
    invoice = Invoice(
        external_invoice_id=payload.external_invoice_id,
        vendor_id=vendor.id,
        invoice_date=payload.invoice_date,
        status="POSTED",
    )
    db.add(invoice)
    db.flush()  # Get invoice.id without committing

    for resolved in resolved_lines:
        line_data: InvoiceLineCreate = resolved["line"]
        db.add(InvoiceLine(
            invoice_id=invoice.id,
            tax_code_id=resolved["tax_code"].id,
            account_id=resolved["account"].id,
            department_id=resolved["department"].id,
            description=line_data.description,
            net_amount=line_data.net_amount,
            vat_amount=line_data.vat_amount,
        ))

    logger.info(
        "Invoice posted successfully",
        extra={
            "external_invoice_id": payload.external_invoice_id,
            "vendor": payload.vendor_external_id,
            "line_count": len(resolved_lines),
        },
    )

    # Refresh to load relationships for response
    db.flush()
    db.refresh(invoice)
    _ = invoice.vendor
    for line in invoice.lines:
        _ = line.tax_code
        _ = line.account
        _ = line.department

    return _build_invoice_response(invoice), True
