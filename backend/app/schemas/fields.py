"""Shared Pydantic field types for quantities and money.

Named ``fields`` rather than ``types`` on purpose: a module called ``types.py``
shadows the standard library's ``types`` for any tool run with this directory on
sys.path, which breaks imports in confusing ways.

Why these exist rather than plain ``Decimal``:

Pydantic v2 serializes a bare ``Decimal`` to a JSON *string* - ``"4.5000"``, not
``4.5``. Every existing frontend consumer types these fields as ``number`` and
calls things like ``value.toFixed(2)`` on them, which throws on a string. Left
alone, the quantity migration would have silently changed the API contract for
every price and quantity in the app.

So: ``Decimal`` everywhere inside Python (exact arithmetic, no float error), and
a plain JSON number on the wire (unchanged contract, no frontend churn). The
authoritative value always lives in the database's NUMERIC column; the JSON
number is a transport/display representation, and doubles carry 4-dp quantities
and 2-dp money far below the 2^53 threshold where that would lose anything.

``when_used="json"`` keeps ``model_dump()`` (Python mode) returning real
Decimals, so internal callers and tests still get exact values.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

_as_json_number = PlainSerializer(float, return_type=float, when_used="json")

# A stock quantity - 4 decimal places (see app.models.inventory.QuantityType).
Quantity = Annotated[Decimal, _as_json_number]

# A currency amount - 2 decimal places (see app.core.money.money).
Money = Annotated[Decimal, _as_json_number]
