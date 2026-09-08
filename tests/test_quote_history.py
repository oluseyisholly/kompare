import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models
from app.core.database import Base
from app.models.asset import Asset
from app.models.enums import MarketCategory, ProviderName, QuoteType
from app.models.quote import Quote, QuoteObservation
from app.repositories.quote import QuoteRepository
from app.repositories.report import ReportRepository


class QuoteHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        asset = Asset(code="BTC", name="Bitcoin", category=MarketCategory.CRYPTO)
        self.db.add(asset)
        self.db.commit()
        self.asset_id = asset.id
        self.repo = QuoteRepository(self.db)
        self.now = datetime.now(UTC)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def quote(self, rate="100", provider=ProviderName.QUIDAX, metadata=None):
        return Quote(provider=provider, asset_id=self.asset_id, quote_type=QuoteType.SPOT,
                     base_currency="BTC", quote_currency="NGN", buy_rate=Decimal(rate),
                     captured_at=self.now, metadata_json=metadata)

    def test_unchanged_then_changed_and_provider_isolation(self):
        self.assertEqual(self.repo.create_many([self.quote()]), 1)
        first = self.db.query(Quote).one()
        captured = first.captured_at
        self.assertEqual(self.repo.create_many([self.quote("100.000000001", metadata={"volume": "999"})]), 0)
        self.assertEqual(first.captured_at, captured)
        self.assertEqual(self.db.query(QuoteObservation).count(), 2)
        self.assertEqual(self.repo.create_many([self.quote("101")]), 1)
        self.assertIsNotNone(first.superseded_at)
        self.assertEqual(self.repo.create_many([self.quote("101", ProviderName.BUSHA)]), 1)
        self.assertEqual(self.db.query(Quote).filter(Quote.superseded_at.is_(None)).count(), 2)

    def test_changed_limits_create_version(self):
        self.repo.create_many([self.quote(metadata={"min_buy_amount": "10"})])
        self.assertEqual(self.repo.create_many([self.quote(metadata={"min_buy_amount": "20"})]), 1)

    def test_failed_batch_rolls_back_freshness_and_version(self):
        self.repo.create_many([self.quote()])
        last_seen = self.db.query(Quote).one().last_seen_at
        with self.assertRaises(ValueError):
            self.repo.create_many([self.quote("101"), self.quote("NaN")])
        self.assertEqual(self.db.query(Quote).count(), 1)
        self.assertEqual(self.db.query(QuoteObservation).count(), 1)
        self.assertEqual(self.db.query(Quote).one().last_seen_at, last_seen)
        self.assertIsNone(self.db.query(Quote).one().superseded_at)

    def test_trend_preserves_unchanged_samples_without_filling_gaps(self):
        with patch("app.repositories.quote.datetime") as clock:
            clock.now.return_value = self.now
            self.repo.create_many([self.quote()])
            clock.now.return_value = self.now + timedelta(hours=3)
            self.repo.create_many([self.quote()])
        rows = ReportRepository(self.db).get_quote_trend(
            ProviderName.QUIDAX, base_currency="BTC", quote_currency="NGN",
            started_at=self.now + timedelta(hours=1), ended_at=self.now + timedelta(hours=4))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0].buy_rate, Decimal("100"))

    def test_unique_current_pair(self):
        self.repo.create_many([self.quote()])
        self.db.add(self.quote())
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
