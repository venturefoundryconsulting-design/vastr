"""Decimal helpers for money and stock arithmetic.

Everything monetary in this app is stored as ``Numeric`` and therefore comes back
from SQLAlchemy as ``Decimal``. Mixing that with ``float`` is not merely imprecise -
``float(x) * Decimal(y)`` raises ``TypeError`` outright - so once stock quantities
became Decimal (see app.models.inventory.QuantityType) every ``float(price) * qty``
site had to be reworked. These helpers are that rework's shared vocabulary.

Use ``money()`` for currency (2 dp) and ``quantity()`` for stock (4 dp). Both round
half-up, which is what an invoice reader expects; Python's default for Decimal is
half-even (banker's rounding), which would make 0.125 -> 0.12 and surprise people.
"""

from decimal import ROUND_HALF_UP, Decimal

MONEY_EXP = Decimal("0.01")
QUANTITY_EXP = Decimal("0.0001")

ZERO = Decimal("0")


def to_decimal(value: Decimal | int | float | str | None) -> Decimal:
    """Coerce anything numeric to Decimal without going through binary float.

    Floats are routed via ``str`` so 0.1 becomes Decimal("0.1") rather than
    Decimal("0.1000000000000000055511151231257827021181583404541015625").
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def money(value: Decimal | int | float | str | None) -> Decimal:
    """Round to 2 decimal places, half-up. Use for any currency amount."""
    return to_decimal(value).quantize(MONEY_EXP, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | int | float | str | None) -> Decimal:
    """Round to 4 decimal places, half-up. Use for any stock quantity."""
    return to_decimal(value).quantize(QUANTITY_EXP, rounding=ROUND_HALF_UP)


def format_quantity(value: Decimal | int | float | None) -> str:
    """Render a stock quantity for humans: 4 -> "4", 4.5 -> "4.5", 0.125 -> "0.125".

    Stored quantities carry four decimal places, so a plain ``str()`` prints
    "4.5000" on receipts and PDFs. This trims the trailing zeros without turning
    whole numbers into "4." - and keeps integers looking exactly as they did before
    the Numeric migration, which matters for every existing receipt layout.
    """
    d = to_decimal(value)
    normalized = d.normalize()
    # normalize() renders large whole numbers in scientific notation (1000 -> 1E+3),
    # and str() keeps that form - so format(..., "f") is what actually forces plain
    # positional notation in both branches.
    if normalized == normalized.to_integral_value():
        return format(normalized.to_integral_value(), "f")
    return format(normalized, "f")
