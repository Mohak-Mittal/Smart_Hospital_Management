"""Money column type.

Money is stored as an INTEGER number of paise (1/100 rupee) and returned as
`decimal.Decimal`.  This is exact (no float rounding) and works on SQLite,
which has no real DECIMAL type.  We also reuse it for percentages (80.00).
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import BigInteger
from sqlalchemy.types import TypeDecorator

TWO = Decimal("0.01")


def to_money(value) -> Decimal:
    """Convert anything number-like to a Decimal rounded to 2 places (half-up)."""
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWO, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((to_money(value) * 100).to_integral_value())

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(TWO)
