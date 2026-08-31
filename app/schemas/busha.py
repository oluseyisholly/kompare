from __future__ import annotations

from pydantic import BaseModel


class BushaPairRead(BaseModel):
    id: str
    base: str
    counter: str
    pair_type: str | None = None
    buy_price: str | None = None
    sell_price: str | None = None
    is_buy_supported: bool
    is_sell_supported: bool
    min_buy_amount: dict | None = None
    min_sell_amount: dict | None = None
    max_buy_amount: dict | None = None
    max_sell_amount: dict | None = None
    percentage_change: str | None = None
