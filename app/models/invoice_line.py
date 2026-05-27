from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime, Integer, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    tax_code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tax_codes.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    # vat_amount stored as-provided; validated against tax_code.rate * net_amount
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")
    tax_code: Mapped["TaxCode"] = relationship("TaxCode", back_populates="invoice_lines")
    account: Mapped["Account"] = relationship("Account", back_populates="invoice_lines")
    department: Mapped["Department"] = relationship("Department", back_populates="invoice_lines")

    def __repr__(self) -> str:
        return f"<InvoiceLine invoice_id={self.invoice_id} net={self.net_amount} vat={self.vat_amount}>"
