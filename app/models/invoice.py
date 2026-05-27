from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.invoice_line import InvoiceLine


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # external_invoice_id is the ERP's reference — the idempotency key
    external_invoice_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Status tracks lifecycle: POSTED is the only valid terminal state for now
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="POSTED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="invoices")
    lines: Mapped[list["InvoiceLine"]] = relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Invoice external_id={self.external_invoice_id!r} date={self.invoice_date}>"
