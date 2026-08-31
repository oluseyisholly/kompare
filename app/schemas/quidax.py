from typing import Any

from pydantic import BaseModel


class QuidaxMarketRead(BaseModel):
    id: str
    name: str
    base_unit: str
    quote_unit: str
    trading_rules: dict[str, Any]
    filters: dict[str, Any]

