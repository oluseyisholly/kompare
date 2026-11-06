from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from app.core.database import Base
from app.models.mixins import TimestampMixin


class FxCurrency(TimestampMixin, Base):
    """Provider-specific discovery; never a transfer-route matrix."""

    __tablename__ = "fx_currencies"
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    code = Column(String(3), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    name = Column(String, nullable=True)
    symbol = Column(String, nullable=True)
    supports_decimals = Column(Boolean, nullable=True)
    decimal_places = Column(Integer, nullable=True)
    precision_source = Column(String, nullable=True)
    country_keywords = Column(JSON, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    source_url = Column(String, nullable=False)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=False)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=False)


Index(
    "uq_fx_currencies_current",
    FxCurrency.provider_id,
    FxCurrency.code,
    unique=True,
    postgresql_where=FxCurrency.is_active.is_(True),
    sqlite_where=FxCurrency.is_active.is_(True),
)


class FxQuoteObservation(TimestampMixin, Base):
    """One on-demand scenario observation; options keep their separate prices."""

    __tablename__ = "fx_quote_observations"
    __table_args__ = (
        UniqueConstraint(
            "fetch_run_id",
            "source_currency",
            "target_currency",
            "requested_amount",
            "amount_basis",
            "classification",
            name="uq_fx_observation_scenario",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    source_currency = Column(String(3), nullable=False, index=True)
    target_currency = Column(String(3), nullable=False, index=True)
    requested_amount = Column(Numeric(24, 8), nullable=False)
    amount_basis = Column(String(6), nullable=False)
    classification = Column(
        String(48),
        nullable=False,
        default="illustrative_transfer_quote",
        server_default="illustrative_transfer_quote",
    )
    captured_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=False)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=False)
    # Decimal strings in JSON preserve full provider precision for all amounts,
    # fees and options. Every request appends a row; no scenario overwrites another.
    response_data = Column(JSON, nullable=False)
