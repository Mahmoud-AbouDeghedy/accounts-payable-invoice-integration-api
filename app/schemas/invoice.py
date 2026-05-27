from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator


class InvoiceLineCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=1000)
    net_amount: Decimal = Field(..., description="Net amount before VAT")
    vat_amount: Decimal = Field(Decimal("0"), description="VAT amount (must match tax_code rate)")
    tax_code_external_id: str = Field(..., min_length=1, max_length=50)
    nominal_external_id: str = Field(..., min_length=1, max_length=255)
    department_external_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("net_amount", "vat_amount")
    @classmethod
    def amounts_to_4dp(cls, v: Decimal) -> Decimal:
        return round(v, 4)


class InvoiceCreate(BaseModel):
    """
    Full invoice payload.
    external_invoice_id is the idempotency key — sending the same id twice
    returns the existing invoice without re-posting.
    """
    external_invoice_id: str = Field(..., min_length=1, max_length=255)
    vendor_external_id: str = Field(..., min_length=1, max_length=255)
    invoice_date: date
    lines: list[InvoiceLineCreate] = Field(..., min_length=1)

    @field_validator("external_invoice_id", "vendor_external_id")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def at_least_one_line(self) -> "InvoiceCreate":
        if not self.lines:
            raise ValueError("Invoice must have at least one line item")
        return self


# ── Response Schemas ──────────────────────────────────────────────────────────

class InvoiceLineResponse(BaseModel):
    id: int
    description: str
    net_amount: Decimal
    vat_amount: Decimal
    tax_code_external_id: str
    nominal_external_id: str
    department_external_id: str

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: int
    external_invoice_id: str
    vendor_external_id: str
    invoice_date: date
    status: str
    lines: list[InvoiceLineResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[InvoiceResponse]


# ── Bulk Ingestion ─────────────────────────────────────────────────────────────

class BulkInvoiceCreate(BaseModel):
    invoices: list[InvoiceCreate] = Field(..., min_length=1, max_length=500)


class BulkInvoiceResult(BaseModel):
    succeeded: list[str]   # external_invoice_ids that were accepted
    skipped: list[str]     # already existed (idempotent)
    failed: list[dict]     # {"external_invoice_id": ..., "errors": [...]}
