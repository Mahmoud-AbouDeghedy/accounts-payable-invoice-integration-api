from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Vendor
from app.schemas.vendor import VendorUpsert, VendorResponse, VendorListResponse
from app.services.upsert import upsert_master

router = APIRouter(prefix="/vendors", tags=["Master Data — Vendors"])


@router.post(
    "",
    response_model=VendorResponse,
    summary="Create or update a vendor",
    description=(
        "Idempotent upsert by `external_id`. "
        "If the vendor already exists, it is updated. Returns 201 on create, 200 on update."
    ),
)
def upsert_vendor(payload: VendorUpsert, db: Session = Depends(get_db)):
    try:
        record, action = upsert_master(
            db=db,
            model=Vendor,
            external_id=payload.external_id,
            data={"name": payload.name},
        )
        db.commit()
        db.refresh(record)

        status_code = status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK
        return JSONResponse(
            content=jsonable_encoder(VendorResponse.model_validate(record)),
            status_code=status_code,
        )
    except Exception:
        db.rollback()
        raise


@router.get(
    "",
    response_model=VendorListResponse,
    summary="List all vendors (paginated)",
)
def list_vendors(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 50

    total = db.query(Vendor).count()
    items = db.query(Vendor).offset((page - 1) * page_size).limit(page_size).all()

    return VendorListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[VendorResponse.model_validate(v) for v in items],
    )


@router.get(
    "/{external_id}",
    response_model=VendorResponse,
    summary="Get a vendor by external_id",
)
def get_vendor(external_id: str, db: Session = Depends(get_db)):
    record = db.query(Vendor).filter(Vendor.external_id == external_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Vendor '{external_id}' not found")
    return VendorResponse.model_validate(record)
