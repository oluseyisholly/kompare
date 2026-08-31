from __future__ import annotations

from app.schemas.busha import BushaPairRead
from app.schemas.common import ApiResponse, PaginatedData, build_pagination
from app.services.ingestion.focus import FocusAssetSelector
from app.adapters.crypto.busha import BushaAdapter


class BushaService:
    def __init__(
        self,
        adapter: BushaAdapter,
        focus_selector: FocusAssetSelector | None = None,
    ) -> None:
        self.adapter = adapter
        self.focus_selector = focus_selector or FocusAssetSelector()

    async def get_pairs(self, *, page: int, per_page: int) -> ApiResponse[PaginatedData[BushaPairRead]]:
        payload = await self.adapter.fetch_pairs()
        pairs = [
            pair
            for pair in payload.get("data", [])
            if self.focus_selector.should_use_pair(
                base_code=pair.get("base"),
                quote_code=pair.get("counter"),
            )
        ]
        total = len(pairs)
        start = (page - 1) * per_page
        end = start + per_page
        items = [
            BushaPairRead(
                id=pair["id"],
                base=str(pair.get("base", "")).upper(),
                counter=str(pair.get("counter", "")).upper(),
                pair_type=pair.get("type"),
                buy_price=(pair.get("buy_price") or {}).get("amount"),
                sell_price=(pair.get("sell_price") or {}).get("amount"),
                is_buy_supported=bool(pair.get("is_buy_supported")),
                is_sell_supported=bool(pair.get("is_sell_supported")),
                min_buy_amount=pair.get("min_buy_amount"),
                min_sell_amount=pair.get("min_sell_amount"),
                max_buy_amount=pair.get("max_buy_amount"),
                max_sell_amount=pair.get("max_sell_amount"),
                percentage_change=pair.get("percentage_change"),
            )
            for pair in pairs[start:end]
        ]
        return ApiResponse(
            responseCode=200,
            message="Busha pairs retrieved successfully",
            data=PaginatedData(
                items=items,
                pagination=build_pagination(page=page, per_page=per_page, total=total),
            ),
        )
