from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import ProviderName, QuoteType
from app.models.mixins import TimestampMixin


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(Enum(ProviderName, name="provider_name"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    provider_asset_id = Column(Integer, ForeignKey("provider_assets.id"), nullable=True, index=True)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=True, index=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True, index=True)
    quote_type = Column(Enum(QuoteType, name="quote_type"), nullable=False, index=True)
    base_currency = Column(String, nullable=False, index=True)
    quote_currency = Column(String, nullable=False, index=True)
    buy_rate = Column(Numeric(24, 8), nullable=True)
    sell_rate = Column(Numeric(24, 8), nullable=True)
    mid_rate = Column(Numeric(24, 8), nullable=True)
    market_price = Column(Numeric(24, 8), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, nullable=True)

    asset = relationship("Asset", back_populates="quotes")
    provider_asset = relationship("ProviderAsset", back_populates="quotes")
    fetch_run = relationship("FetchRun", back_populates="quotes")
    raw_record = relationship("RawRecord", back_populates="quotes")


Index(
    "uq_quotes_current_pair", Quote.provider, Quote.asset_id,
    Quote.base_currency, Quote.quote_currency, Quote.quote_type,
    unique=True, postgresql_where=Quote.superseded_at.is_(None),
    sqlite_where=Quote.superseded_at.is_(None),
)


class QuoteObservation(Base):
    """Successful sampling times, including unchanged prices; failures add no points."""

    __tablename__ = "quote_observations"
    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
