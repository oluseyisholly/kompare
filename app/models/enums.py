from enum import Enum


class MarketCategory(str, Enum):
    CRYPTO = "crypto"
    GIFTCARD = "giftcard"
    FX = "fx"


class ProviderName(str, Enum):
    QUIDAX = "quidax"
    BUSHA = "busha"
    CARDTONIC = "cardtonic"
    TBAY = "tbay"


class FetchRunStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class RawSourceType(str, Enum):
    API = "api"
    HTML = "html"
    JSON = "json"
    DOCUMENT = "document"


class QuoteType(str, Enum):
    SPOT = "spot"
    BUY = "buy"
    SELL = "sell"
    MARKET = "market"


class FeeCategory(str, Enum):
    TRADE = "trade"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"
    SWAP = "swap"
    NETWORK = "network"


class FeeType(str, Enum):
    FLAT = "flat"
    PERCENTAGE = "percentage"
    SPREAD = "spread"
    TIERED = "tiered"


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class IngestionJobType(str, Enum):
    MARKET_DATA = "market_data"
    KYC = "kyc"
    FEES = "fees"


class GiftCardType(str, Enum):
    ECODE = "ecode"
    PHYSICAL = "physical"
    OTHER = "other"


class GiftCardRateUnit(str, Enum):
    PER_FACE_VALUE_UNIT = "per_face_value_unit"
