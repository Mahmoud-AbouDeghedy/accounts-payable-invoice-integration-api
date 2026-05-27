from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Department
from app.schemas.department import DepartmentUpsert, DepartmentResponse, DepartmentListResponse
from app.services.upsert import upsert_master

router = APIRouter(prefix="/departments", tags=["Master Data — Departments"])


@router.post("", response_model=DepartmentResponse, summary="Create or update a department")
def upsert_department(payload: DepartmentUpsert, db: Session = Depends(get_db)):
    try:
        record, action = upsert_master(
            db=db, model=Department, external_id=payload.external_id,
            data={"name": payload.name},
        )
        db.commit()
        db.refresh(record)
        status_code = status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK
        return JSONResponse(
            content=jsonable_encoder(DepartmentResponse.model_validate(record)),
            status_code=status_code,
        )
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=DepartmentListResponse, summary="List all departments (paginated)")
def list_departments(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    total = db.query(Department).count()
    items = db.query(Department).offset((page - 1) * page_size).limit(page_size).all()
    return DepartmentListResponse(
        total=total, page=page, page_size=page_size,
        items=[DepartmentResponse.model_validate(d) for d in items],
    )


@router.get("/{external_id}", response_model=DepartmentResponse)
def get_department(external_id: str, db: Session = Depends(get_db)):
    record = db.query(Department).filter(Department.external_id == external_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Department '{external_id}' not found")
    return DepartmentResponse.model_validate(record)
