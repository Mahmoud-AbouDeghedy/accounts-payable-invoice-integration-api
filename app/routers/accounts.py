from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.schemas.account import AccountUpsert, AccountResponse, AccountListResponse
from app.services.upsert import upsert_master

router = APIRouter(prefix="/accounts", tags=["Master Data — Accounts"])


@router.post("", response_model=AccountResponse, summary="Create or update a nominal account")
def upsert_account(payload: AccountUpsert, db: Session = Depends(get_db)):
    try:
        record, action = upsert_master(
            db=db, model=Account, external_id=payload.external_id,
            data={"name": payload.name},
        )
        db.commit()
        db.refresh(record)
        status_code = status.HTTP_201_CREATED if action == "created" else status.HTTP_200_OK
        return JSONResponse(
            content=jsonable_encoder(AccountResponse.model_validate(record)),
            status_code=status_code,
        )
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=AccountListResponse, summary="List all accounts (paginated)")
def list_accounts(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    total = db.query(Account).count()
    items = db.query(Account).offset((page - 1) * page_size).limit(page_size).all()
    return AccountListResponse(
        total=total, page=page, page_size=page_size,
        items=[AccountResponse.model_validate(a) for a in items],
    )


@router.get("/{external_id}", response_model=AccountResponse)
def get_account(external_id: str, db: Session = Depends(get_db)):
    record = db.query(Account).filter(Account.external_id == external_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Account '{external_id}' not found")
    return AccountResponse.model_validate(record)
