import unittest
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import app.models
from app.core.database import Base
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import FetchRunStatus, MarketCategory
from app.models.fetch_run import FetchRun
from app.models.giftcard_rate import GiftCardRate
from app.models.giftcard_variant import GiftCardVariant
from app.models.provider import Provider
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.provider import ProviderRepository
from app.repositories.report import ReportRepository
from app.repositories.tbay_catalog import TbayCatalogRepository
from app.services.ingestion.tbay import TbayIngestionService
from app.services.report import ReportService


class TbayIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Provider(slug="tbay", name="Tbay", category=MarketCategory.GIFTCARD, has_adapter=True))
        self.db.commit()
        self.offer = {"code": "offer1", "giftcardType": "razer", "tradeCurrency": "USD",
                      "tradeCoin": "Points", "discount": "0.877041", "minTrade": 10,
                      "maxTrade": 100, "tagList": ["Accepts Multiples of 5"], "status": "1"}
        self.adapter = AsyncMock()
        self.adapter.fetch_categories.return_value = [{"code": "razer", "name": "Razer Gift Card"}]
        self.adapter.fetch_currencies.return_value = [{"currency": "USD"}]
        self.adapter.fetch_offers.return_value = [self.offer]
        self.adapter.fetch_points_rate.return_value = {"mid": "1255.19"}
        self.adapter.source_url = lambda code: "https://api.tbay.store/api?code=" + code
        self.service = TbayIngestionService(adapter=self.adapter,
            catalog_repository=TbayCatalogRepository(self.db, GiftCardRateRepository(self.db)),
            fetch_run_repository=FetchRunRepository(self.db))
        self.reports = ReportService(ReportRepository(self.db), ProviderRepository(self.db))

    async def asyncTearDown(self):
        self.db.close()
        self.engine.dispose()

    def preview(self, rate_id, amount):
        return self.reports.get_giftcard_sell_preview("tbay", rate_id=rate_id,
            asset_code=None, source_currency=None, face_value=Decimal(amount))

    async def test_repeated_run_changed_rate_and_calculation(self):
        self.assertEqual((await self.service.ingest())["rates_created"], 1)
        rate = self.db.query(GiftCardRate).one()
        seen = rate.last_seen_at
        self.assertEqual(self.preview(rate.id, "50").data.payout_amount, Decimal("55042.65"))
        self.assertTrue(self.preview(rate.id, "50").data.is_estimate)
        self.assertEqual((await self.service.ingest())["rates_created"], 0)
        self.assertGreaterEqual(rate.last_seen_at, seen)
        self.offer["discount"] = "0.9"
        self.assertEqual((await self.service.ingest())["rates_created"], 1)
        self.assertIsNotNone(rate.superseded_at)
        with self.assertRaises(NotFoundError):
            self.preview(rate.id, "50")
        self.assertEqual(self.db.query(GiftCardVariant).count(), 1)

    async def test_failed_fetch_preserves_freshness(self):
        await self.service.ingest()
        seen = self.db.query(GiftCardRate).one().last_seen_at
        self.adapter.fetch_offers.side_effect = RuntimeError("upstream failure")
        with self.assertRaises(RuntimeError):
            await self.service.ingest()
        self.assertEqual(self.db.query(GiftCardRate).one().last_seen_at, seen)
        self.assertEqual(self.db.query(FetchRun).order_by(FetchRun.id.desc()).first().status, FetchRunStatus.FAILED)

    async def test_denominations_increments_and_limits(self):
        self.offer["fixTrade"] = "10||50||100"
        await self.service.ingest()
        rate = self.db.query(GiftCardRate).one()
        for amount in ["5", "51", "25", "10.5", "101"]:
            with self.subTest(amount=amount), self.assertRaises(BadRequestError):
                self.preview(rate.id, amount)

    async def test_changed_terms_create_version(self):
        await self.service.ingest()
        self.offer["explain"] = "New conditions"
        self.assertEqual((await self.service.ingest())["rates_created"], 1)

    async def test_removed_offer_is_unavailable(self):
        await self.service.ingest()
        old_id = self.db.query(GiftCardRate).one().id
        self.offer["code"] = "replacement"
        await self.service.ingest()
        with self.assertRaises(NotFoundError):
            self.preview(old_id, "50")

    async def test_partial_run_keeps_failed_scope_and_saves_good_scope(self):
        await self.service.ingest()
        original = self.db.query(GiftCardRate).one()
        seen = original.last_seen_at
        self.adapter.fetch_currencies.return_value = [{"currency": "USD"}, {"currency": "CAD"}]
        async def fetch(category, currency, **kwargs):
            if currency == "USD":
                raise RuntimeError("unstable pagination")
            return [{**self.offer, "code": "cad-offer", "tradeCurrency": "CAD"}]
        self.adapter.fetch_offers.side_effect = fetch
        result = await self.service.ingest()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["scopes_completed"], 1)
        self.assertEqual(result["failed_scopes"][0]["currency"], "USD")
        self.assertEqual(self.db.query(GiftCardRate).count(), 2)
        self.assertEqual(original.last_seen_at, seen)
        self.assertTrue(original.giftcard_variant.is_active)
        run = self.db.query(FetchRun).order_by(FetchRun.id.desc()).first()
        self.assertEqual(run.status, FetchRunStatus.FAILED)
        self.assertEqual(run.metadata_json["status"], "partial")

    async def test_empty_successful_scope_retires_only_its_own_offers(self):
        await self.service.ingest()
        self.adapter.fetch_currencies.return_value = [{"currency": "CAD"}]
        self.adapter.fetch_offers.return_value = []
        await self.service.ingest()
        self.assertTrue(self.db.query(GiftCardVariant).one().is_active)
        self.adapter.fetch_currencies.return_value = [{"currency": "USD"}]
        await self.service.ingest()
        self.assertFalse(self.db.query(GiftCardVariant).one().is_active)


if __name__ == "__main__":
    unittest.main()
