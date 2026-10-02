from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# Money is a string with 2 decimals, fractional quantities a string with 3 (API_CONTRACT.md 1.2).
Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]
Qty = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.3f}", return_type=str, when_used="json")]
