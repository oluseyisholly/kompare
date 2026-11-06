"""Compatibility facade. Public FX reads/calculations use the shared FxService."""

from app.schemas.common import ApiResponse
from app.services.fx import FxService
from app.services.ingestion.wise import WiseIngestionService


class WiseService(FxService):
    def __init__(self, db, *, adapter=None):
        super().__init__(db)
        self.db = db
        self._adapter = adapter
        self._ingestion = None

    @property
    def ingestion(self):
        if self._ingestion is None:
            self._ingestion = WiseIngestionService(self.db, adapter=self._adapter)
        return self._ingestion

    def list_rates(self, **filters):
        return super().list_rates("wise", **filters)

    def list_currencies(self, **filters):
        return super().list_currencies("wise", **filters)

    async def request_quote(self, request):
        quote = await self.ingestion.request_quote(request)
        return ApiResponse(
            responseCode=200,
            message="Illustrative transfer observation; not executable",
            data=quote,
        )
