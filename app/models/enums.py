from enum import Enum


class MarketCategory(str, Enum):
    CRYPTO = "crypto"
    GIFTCARD = "giftcard"
    FX = "fx"
    MUTUAL_FUND = "mutual_fund"


class ProviderName(str, Enum):
    FINCRA = "fincra"
    FLUTTERWAVE = "flutterwave"
    WISE = "wise"
    UNITED_CAPITAL = "united_capital"
    STANBIC = "stanbic"
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


class UserStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    UNVERIFIED = "unverified"
    SUSPENDED = "suspended"


class AdminType(str, Enum):
    SUPER_ADMIN = "super_admin"
    SUPPORT_ADMIN = "support_admin"
    CONTENT_MODERATOR = "content_moderator"
    INGESTION_MANAGER = "ingestion_manager"
    FINANCE_ADMIN = "finance_admin"


class IngestionJobType(str, Enum):
    CURRENCIES = "currencies"
    FUND_DETAILS = "fund_details"
    MARKET_DATA = "market_data"
    KYC = "kyc"
    FEES = "fees"


class GiftCardType(str, Enum):
    ECODE = "ecode"
    PHYSICAL = "physical"
    OTHER = "other"


class GiftCardRateUnit(str, Enum):
    PER_FACE_VALUE_UNIT = "per_face_value_unit"


class ProviderReviewTag(str, Enum):
    RATE_ACCURACY = "rate_accuracy"
    CUSTOMER_SERVICE = "customer_service"
    EASE_OF_USE = "ease_of_use"
    FAST_TRANSACTIONS = "fast_transactions"
    SLOW_TRANSACTIONS = "slow_transactions"
    VERIFICATION_EXPERIENCE = "verification_experience"
    SUPPORT_QUALITY = "support_quality"
    HIDDEN_FEES = "hidden_fees"
    SECURITY_TRUST = "security_trust"


class ProviderReviewType(str, Enum):
    REVIEW = "review"
    TIP = "tip"


class ProviderTipCategory(str, Enum):
    RATE_ALERT = "rate_alert"
    HIDDEN_FEE_WARNING = "hidden_fee_warning"
    SCAM_WARNING = "scam_warning"
    GENERAL_TIP = "general_tip"


class ProviderTipSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProviderReviewStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    HIDDEN = "hidden"


class VerificationPurpose(str, Enum):
    EMAIL_VERIFICATION = "email_verification"
    PHONE_VERIFICATION = "phone_verification"
    PASSWORD_RESET = "password_reset"


class VerificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"


class UserDeletionRequestStatus(str, Enum):
    REQUESTED = "requested"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
