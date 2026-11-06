from app.core.exceptions import NotFoundError
from app.repositories.mutual_fund import MutualFundRepository
from app.repositories.provider import ProviderRepository
from app.schemas.common import ApiResponse, build_paginated_response
from app.schemas.mutual_fund import MutualFundRead, MutualFundSnapshotRead
from app.utils.mutual_fund_metrics import build_published_metrics


class MutualFundService:
    def __init__(self, repository: MutualFundRepository):
        self.repository = repository

    def list_funds(self, *, page, per_page, provider_slug=None):
        provider_id = None
        if provider_slug is not None:
            provider = ProviderRepository(self.repository.db).get_by_slug(provider_slug)
            if provider is None:
                raise NotFoundError("Provider not found")
            provider_id = provider.id
        funds, total = self.repository.list_funds(
            page=page,
            per_page=per_page,
            provider_id=provider_id,
        )
        snapshots = self.repository.latest_snapshots_for_funds([fund.id for fund in funds])
        contexts = self.repository.source_contexts({s.raw_record_id for s in snapshots.values()})
        items = []
        for fund in funds:
            item = MutualFundRead.model_validate(fund)
            snapshot = snapshots.get(fund.id)
            if snapshot is not None:
                item.latest_snapshot = self._snapshot_to_schema(fund, snapshot, contexts)
            items.append(item)
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Mutual funds retrieved successfully",
        )

    def latest_snapshot(self, code):
        fund = self.repository.get_by_code(code)
        if fund is None:
            raise NotFoundError("Mutual fund not found")
        snapshot = self.repository.latest_snapshot(fund.id)
        if snapshot is None:
            raise NotFoundError("No snapshot available for this fund")
        return ApiResponse(
            responseCode=200,
            message="Latest mutual fund snapshot retrieved successfully",
            data=self._snapshot_to_schema(
                fund, snapshot, self.repository.source_contexts({snapshot.raw_record_id})
            ),
        )

    @staticmethod
    def _snapshot_to_schema(fund, snapshot, contexts):
        source = contexts.get(snapshot.raw_record_id, {})
        context = source.get("funds", {}).get(fund.code, {})
        result = MutualFundSnapshotRead.model_validate(snapshot)
        result.source_url = source.get("source_url")
        if context.get("valuation_date") == (
            snapshot.valuation_date.isoformat() if snapshot.valuation_date else None
        ):
            result.published_metrics = build_published_metrics(
                snapshot, context, currency=fund.currency
            )
        return result
