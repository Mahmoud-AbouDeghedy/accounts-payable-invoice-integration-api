from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TaxCode
from app.schemas.tax_code import TaxCodeUpsert, TaxCodeResponse, TaxCodeListResponse
from app.services.upsert import upsert_master

router = APIRouter(prefix="/tax-codes", tags=["Master Data — Tax Codes"])


@router.post(
    "",
    response_model=TaxCodeResponse,
    summary="Create or update a tax code",
)
def upsert_tax_code(payload: TaxCodeUpsert, db: Session = Depends(get_db)):
    try:
        record, action = upsert_master(
            db=db,
            model=TaxCode,
            external_id=payload.external_id,
            data={
                "code": payload.code,
                "rate": payload.rate,
                "description": payload.description,
            },
        )
        db.commit()
        db.refresh(record)
        status_code = status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK
        return JSONResponse(
            content=jsonable_encoder(TaxCodeResponse.model_validate(record)),
            status_code=status_code,
        )
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=TaxCodeListResponse, summary="List all tax codes (paginated)")
def list_tax_codes(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    total = db.query(TaxCode).count()
    items = db.query(TaxCode).offset((page - 1) * page_size).limit(page_size).all()
    return TaxCodeListResponse(
        total=total, page=page, page_size=page_size,
        items=[TaxCodeResponse.model_validate(t) for t in items],
    )


@router.get("/{external_id}", response_model=TaxCodeResponse)
def get_tax_code(external_id: str, db: Session = Depends(get_db)):
    record = db.query(TaxCode).filter(TaxCode.external_id == external_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Tax code '{external_id}' not found")
    return TaxCodeResponse.model_validate(record)
