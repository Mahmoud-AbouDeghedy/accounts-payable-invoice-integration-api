from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class VendorUpsert(BaseModel):
    """
    Request body for POST /vendors.
    external_id is the ERP's identifier — drives idempotency.
    """
    external_id: str = Field(..., min_length=1, max_length=255, description="ERP vendor identifier")
    name: str = Field(..., min_length=1, max_length=500, description="Vendor display name")

    @field_validator("external_id", "name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class VendorResponse(BaseModel):
    id: int
    external_id: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VendorListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[VendorResponse]
