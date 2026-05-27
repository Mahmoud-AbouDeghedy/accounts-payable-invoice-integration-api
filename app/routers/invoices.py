from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Invoice, Vendor
from app.schemas.invoice import (
    InvoiceCreate, InvoiceResponse, InvoiceListResponse,
    BulkInvoiceCreate, BulkInvoiceResult, InvoiceLineResponse,
)
from app.services.invoice_service import post_invoice, InvoiceValidationError
from app.core.json_logging import logger

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.post(
    "",
    summary="Post an invoice (idempotent)",
    description=(
        "Posts an invoice with full referential integrity and VAT validation. "
        "Idempotent: sending the same `external_invoice_id` twice returns the "
        "existing record with HTTP 200. First successful post returns HTTP 201."
    ),
    responses={
        201: {"description": "Invoice created"},
        200: {"description": "Invoice already existed (idempotent)"},
        422: {"description": "Validation error — structured list of all failures"},
    },
)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    try:
        response, is_new = post_invoice(db=db, payload=payload)
        db.commit()
        return JSONResponse(
            content=jsonable_encoder(response),
            status_code=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )
    except InvoiceValidationError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Invoice validation failed. No data was saved.",
                "errors": e.errors,
            },
        )
    except Exception:
        db.rollback()
        logger.exception("Unexpected error posting invoice", extra={"external_invoice_id": payload.external_invoice_id})
        raise


@router.post(
    "/bulk",
    response_model=BulkInvoiceResult,
    summary="Bulk invoice ingestion",
    description=(
        "Post up to 500 invoices in one request. Each invoice is processed independently — "
        "failures in one do not affect others. Returns a full report of succeeded/skipped/failed."
    ),
)
def bulk_create_invoices(payload: BulkInvoiceCreate, db: Session = Depends(get_db)):
    succeeded = []
    skipped = []
    failed = []

    for invoice_payload in payload.invoices:
        try:
            _, is_new = post_invoice(db=db, payload=invoice_payload)
            db.commit()
            if is_new:
                succeeded.append(invoice_payload.external_invoice_id)
            else:
                skipped.append(invoice_payload.external_invoice_id)
        except InvoiceValidationError as e:
            db.rollback()
            failed.append({
                "external_invoice_id": invoice_payload.external_invoice_id,
                "errors": e.errors,
            })
        except Exception as e:
            db.rollback()
            logger.exception(
                "Unexpected error in bulk invoice processing",
                extra={"external_invoice_id": invoice_payload.external_invoice_id},
            )
            failed.append({
                "external_invoice_id": invoice_payload.external_invoice_id,
                "errors": [{"message": str(e)}],
            })

    logger.info(
        "Bulk invoice ingestion complete",
        extra={"succeeded": len(succeeded), "skipped": len(skipped), "failed": len(failed)},
    )

    return BulkInvoiceResult(succeeded=succeeded, skipped=skipped, failed=failed)


@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="List invoices (paginated)",
)
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    vendor_external_id: str | None = Query(None, description="Filter by vendor external_id"),
    db: Session = Depends(get_db),
):
    query = db.query(Invoice).options(
        joinedload(Invoice.vendor),
        joinedload(Invoice.lines),
    )

    if vendor_external_id:
        vendor = db.query(Vendor).filter(Vendor.external_id == vendor_external_id).first()
        if not vendor:
            raise HTTPException(status_code=404, detail=f"Vendor '{vendor_external_id}' not found")
        query = query.filter(Invoice.vendor_id == vendor.id)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    response_items = []
    for inv in items:
        response_items.append(InvoiceResponse(
            id=inv.id,
            external_invoice_id=inv.external_invoice_id,
            vendor_external_id=inv.vendor.external_id,
            invoice_date=inv.invoice_date,
            status=inv.status,
            lines=[
                InvoiceLineResponse(
                    id=line.id,
                    description=line.description,
                    net_amount=line.net_amount,
                    vat_amount=line.vat_amount,
                    tax_code_external_id=line.tax_code.external_id,
                    nominal_external_id=line.account.external_id,
                    department_external_id=line.department.external_id,
                )
                for line in inv.lines
            ],
            created_at=inv.created_at,
            updated_at=inv.updated_at,
        ))

    return InvoiceListResponse(total=total, page=page, page_size=page_size, items=response_items)


@router.get(
    "/{external_invoice_id}",
    response_model=InvoiceResponse,
    summary="Get invoice by external_id",
)
def get_invoice(external_invoice_id: str, db: Session = Depends(get_db)):
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.vendor), joinedload(Invoice.lines))
        .filter(Invoice.external_invoice_id == external_invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice '{external_invoice_id}' not found")

    return InvoiceResponse(
        id=invoice.id,
        external_invoice_id=invoice.external_invoice_id,
        vendor_external_id=invoice.vendor.external_id,
        invoice_date=invoice.invoice_date,
        status=invoice.status,
        lines=[
            InvoiceLineResponse(
                id=line.id,
                description=line.description,
                net_amount=line.net_amount,
                vat_amount=line.vat_amount,
                tax_code_external_id=line.tax_code.external_id,
                nominal_external_id=line.account.external_id,
                department_external_id=line.department.external_id,
            )
            for line in invoice.lines
        ],
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )
