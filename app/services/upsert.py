"""
Generic upsert service for all master data entities.

Upsert logic:
  - If external_id exists → update name/fields, return (record, "updated")
  - If not              → insert new record, return (record, "created")

This is intentionally generic so vendors, tax_codes, accounts, departments
all share the same battle-tested code path.
"""
from typing import TypeVar, Type, Literal
from sqlalchemy.orm import Session
from app.database import Base
from app.core.json_logging import logger

T = TypeVar("T", bound=Base)
UpsertResult = Literal["created", "updated"]


def upsert_master(
    db: Session,
    model: Type[T],
    external_id: str,
    data: dict,
) -> tuple[T, UpsertResult]:
    """
    Upsert a master data record by external_id.

    Args:
        db:          Active SQLAlchemy session (caller manages commit/rollback)
        model:       The SQLAlchemy model class (Vendor, TaxCode, etc.)
        external_id: The ERP's stable identifier
        data:        Dict of fields to set/update (excluding external_id)

    Returns:
        (record, "created"|"updated")
    """
    record = db.query(model).filter(model.external_id == external_id).first()

    if record is None:
        record = model(external_id=external_id, **data)
        db.add(record)
        action: UpsertResult = "created"
        logger.info(
            "Master data created",
            extra={"entity": model.__tablename__, "external_id": external_id},
        )
    else:
        changed_fields = []
        for field, value in data.items():
            if getattr(record, field) != value:
                setattr(record, field, value)
                changed_fields.append(field)

        action = "updated"
        if changed_fields:
            logger.info(
                "Master data updated",
                extra={
                    "entity": model.__tablename__,
                    "external_id": external_id,
                    "changed_fields": changed_fields,
                },
            )
        else:
            logger.info(
                "Master data unchanged (no-op upsert)",
                extra={"entity": model.__tablename__, "external_id": external_id},
            )

    return record, action
