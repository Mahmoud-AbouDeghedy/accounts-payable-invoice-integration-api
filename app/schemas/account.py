from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class AccountUpsert(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=500)

    @field_validator("external_id", "name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class AccountResponse(BaseModel):
    id: int
    external_id: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AccountResponse]
