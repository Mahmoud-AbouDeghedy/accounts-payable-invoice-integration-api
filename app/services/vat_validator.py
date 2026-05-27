"""
VAT Validation Service

VAT correctness rule:
    expected_vat = round(net_amount * tax_rate, 2)
    |provided_vat - expected_vat| <= tolerance

We allow a small tolerance (0.02) to accommodate rounding differences
between ERP systems (some round mid-calculation, some at the end).

This is a deliberate trade-off: strict 0 tolerance would reject valid
entries that differ by 1 cent due to rounding methods.
"""
from decimal import Decimal, ROUND_HALF_UP


# Tolerance in currency units — 2 cents covers rounding differences
VAT_TOLERANCE = Decimal("0.02")


class VATValidationError(Exception):
    def __init__(self, line_index: int, description: str, net: Decimal, provided_vat: Decimal,
                 expected_vat: Decimal, rate: Decimal):
        self.line_index = line_index
        self.details = {
            "line_index": line_index,
            "description": description,
            "net_amount": str(net),
            "provided_vat": str(provided_vat),
            "expected_vat": str(expected_vat),
            "tax_rate": str(rate),
            "message": (
                f"Line {line_index}: VAT mismatch. "
                f"Provided={provided_vat}, Expected={expected_vat} "
                f"(net={net} × rate={rate}). Tolerance=±{VAT_TOLERANCE}"
            ),
        }
        super().__init__(self.details["message"])


def validate_vat(
    line_index: int,
    description: str,
    net_amount: Decimal,
    vat_amount: Decimal,
    tax_rate: Decimal,
) -> None:
    """
    Raises VATValidationError if the provided VAT is outside tolerance.

    line_index is 0-based, used for clear error messages.
    """
    expected_vat = (net_amount * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    difference = abs(vat_amount - expected_vat)

    if difference > VAT_TOLERANCE:
        raise VATValidationError(
            line_index=line_index,
            description=description,
            net=net_amount,
            provided_vat=vat_amount,
            expected_vat=expected_vat,
            rate=tax_rate,
        )
