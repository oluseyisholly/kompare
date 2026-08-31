from app.adapters.crypto.quidax import QuidaxAdapter
from app.schemas.common import ApiResponse, PaginatedData, build_pagination
from app.schemas.quidax import QuidaxMarketRead


class QuidaxService:
    def __init__(self, adapter: QuidaxAdapter) -> None:
        self.adapter = adapter

    async def get_markets(self, *, page: int, per_page: int) -> ApiResponse[PaginatedData[QuidaxMarketRead]]:
        payload = await self.adapter.fetch_markets()
        markets = payload.get("data", [])
        total = len(markets)
        start = (page - 1) * per_page
        end = start + per_page
        items = [
            QuidaxMarketRead(
                id=market["id"],
                name=market["name"],
                base_unit=str(market["base_unit"]).upper(),
                quote_unit=str(market["quote_unit"]).upper(),
                trading_rules=market.get("trading_rules", {}),
                filters=market.get("filters", {}),
            )
            for market in markets[start:end]
        ]
        return ApiResponse(
            responseCode=200,
            message="Quidax markets retrieved successfully",
            data=PaginatedData(
                items=items,
                pagination=build_pagination(page=page, per_page=per_page, total=total),
            ),
        )
