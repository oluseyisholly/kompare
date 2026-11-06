from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base
from app.models.mixins import TimestampMixin


class MutualFund(TimestampMixin, Base):
    __tablename__ = "mutual_funds"

    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    fund_type = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    minimum_initial_investment = Column(Numeric(24, 8), nullable=True)
    minimum_topup = Column(Numeric(24, 8), nullable=True)
    minimum_holding_days = Column(Integer, nullable=True)
    risk_label = Column(String, nullable=True)
    management_fee_percent_pa = Column(Numeric(24, 8), nullable=True)
    distribution_frequency = Column(String, nullable=True)
    structure = Column(String, nullable=True)
    details_metadata = Column(JSON, nullable=True)


class MutualFundSnapshot(Base):
    __tablename__ = "mutual_fund_snapshots"
    __table_args__ = (
        UniqueConstraint("fund_id", "fetch_run_id", name="uq_mutual_fund_snapshot_run"),
    )

    id = Column(Integer, primary_key=True)
    fund_id = Column(Integer, ForeignKey("mutual_funds.id"), nullable=False, index=True)
    bid_price = Column(Numeric(24, 8), nullable=True)
    offer_price = Column(Numeric(24, 8), nullable=True)
    nav_per_unit = Column(Numeric(24, 8), nullable=True)
    yield_percent = Column(Numeric(24, 8), nullable=True)
    ytd_return_percent = Column(Numeric(24, 8), nullable=True)
    yield_label = Column(String, nullable=True)
    valuation_date = Column(Date, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=False, index=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=False)
