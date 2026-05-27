from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.invoice_line import InvoiceLine


class TaxCode(Base):
    __tablename__ = "tax_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    # Rate stored as decimal e.g. 0.18 = 18%, 0.00 = 0%
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    invoice_lines: Mapped[list["InvoiceLine"]] = relationship("InvoiceLine", back_populates="tax_code")

    def __repr__(self) -> str:
        return f"<TaxCode code={self.code!r} rate={self.rate}>"
