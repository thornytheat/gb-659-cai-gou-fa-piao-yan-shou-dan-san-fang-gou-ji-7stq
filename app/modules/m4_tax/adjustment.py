from decimal import Decimal
from .calculate import money


def tax_adjustment_delta(old_tax: str, new_tax: str) -> dict:
    """Signed difference between corrected and closing tax, rounded half up to the cent.

    A downward correction yields a negative delta; it is carried forward as a
    difference-batch entry rather than editing the closed batch.
    """
    old_value, new_value = Decimal(str(old_tax)), Decimal(str(new_tax))
    if old_value < 0 or new_value < 0:
        raise ValueError("NEGATIVE_TAX")
    delta = money(new_value - old_value)
    return {"old_tax_cny": str(money(old_value)), "new_tax_cny": str(money(new_value)), "tax_delta_cny": str(delta)}


def batch_tax_delta(deltas: list[str]) -> str:
    """Conserve the signed deltas when several corrections hit one batch."""
    return str(money(sum((Decimal(value) for value in deltas), start=Decimal("0"))))
