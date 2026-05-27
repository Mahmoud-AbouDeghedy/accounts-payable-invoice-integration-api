from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class TaxCodeUpsert(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=50)
    code: str = Field(..., min_length=1, max_length=50)
    rate: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"), description="Rate as decimal: 0.18 = 18%")
    description: str | None = Field(None, max_length=500)

    @field_validator("rate")
    @classmethod
    def rate_max_4_decimals(cls, v: Decimal) -> Decimal:
        # Round to 4 decimal places to avoid floating point drift
        return round(v, 4)


class TaxCodeResponse(BaseModel):
    id: int
    external_id: str
    code: str
    rate: Decimal
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaxCodeListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TaxCodeResponse]
