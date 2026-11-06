import os

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


QUIDAX_BASE_URL = os.getenv("QUIDAX_BASE_URL", "https://openapi.quidax.io")
QUIDAX_API_KEY = os.getenv("QUIDAX_API_KEY")
QUIDAX_KYC_URL = os.getenv(
    "QUIDAX_KYC_URL",
    "https://support.quidax.io/hc/en-us/articles/13812153745564-KYC-Documents-and-Limits",
)

BUSHA_BASE_URL = os.getenv("BUSHA_BASE_URL", "https://api.sandbox.busha.so")
BUSHA_API_KEY = os.getenv("BUSHA_API_KEY")
BUSHA_KYC_IDENTITY_URL = os.getenv(
    "BUSHA_KYC_IDENTITY_URL",
    "https://support.busha.io/en/articles/2631291-how-do-i-verify-my-identity",
)
BUSHA_KYC_LIMITS_URL = os.getenv(
    "BUSHA_KYC_LIMITS_URL",
    "https://support.busha.io/en/articles/2137037-verification-levels-and-limits",
)

CARDTONIC_BASE_URL = os.getenv("CARDTONIC_BASE_URL", "https://api.cardtonic.com")
CARDTONIC_SITE_URL = os.getenv("CARDTONIC_SITE_URL", "https://cardtonic.com")
CARDTONIC_API_ENV = os.getenv("CARDTONIC_API_ENV", "production")
CARDTONIC_KYC_URL = os.getenv(
    "CARDTONIC_KYC_URL",
    "https://help.cardtonic.com/en/articles/6811777-what-is-kyc-and-how-does-it-apply-to-cardtonic",
)

TBAY_BASE_URL = os.getenv("TBAY_BASE_URL", "https://api.tbay.store")
TBAY_SITE_URL = os.getenv("TBAY_SITE_URL", "https://h5.tbay.store")
TBAY_CLIENT_VERSION = os.getenv("TBAY_CLIENT_VERSION", "1.10.16")
TBAY_SIGNING_SALT = os.getenv("TBAY_SIGNING_SALT", "IgaO0cpIJp")

SECRET_KEY = os.getenv("SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES = int(
    os.getenv("EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES", "10")
)
EMAIL_VERIFICATION_OTP_LENGTH = int(os.getenv("EMAIL_VERIFICATION_OTP_LENGTH", "6"))
PASSWORD_RESET_OTP_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_OTP_EXPIRE_MINUTES", "10"))
PASSWORD_RESET_OTP_LENGTH = int(os.getenv("PASSWORD_RESET_OTP_LENGTH", "6"))

ENABLE_INGESTION_SCHEDULER = _get_bool("ENABLE_INGESTION_SCHEDULER", False)
INGESTION_SCHEDULER_POLL_SECONDS = int(os.getenv("INGESTION_SCHEDULER_POLL_SECONDS", "60"))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_TLS = _get_bool("SMTP_USE_TLS", True)
SMTP_USE_SSL = _get_bool("SMTP_USE_SSL", False)
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Kompare")

# Kompare freshness policy; not a provider publishing commitment.
UNITED_CAPITAL_STALE_AFTER_DAYS = int(os.getenv("UNITED_CAPITAL_STALE_AFTER_DAYS", "7"))

# Public mutual-fund pages require no provider credentials.
STANBIC_BASE_URL = os.getenv("STANBIC_BASE_URL", "https://blunest.stanbicibtcassetmanagement.com")
UNITED_CAPITAL_BASE_URL = os.getenv("UNITED_CAPITAL_BASE_URL", "https://unitedcapitalplcgroup.com")

# Wise is optional. Personal tokens authenticate rates; illustrative quotes are
# anonymous unless a separate partner client-credentials token is configured.
WISE_API_TOKEN = os.getenv("WISE_API_TOKEN", "")
WISE_BASE_URL = os.getenv("WISE_BASE_URL", "https://api.wise.com")
WISE_API_VERSION = os.getenv("WISE_API_VERSION", "2026Q4")
WISE_QUOTE_CLIENT_TOKEN = os.getenv("WISE_QUOTE_CLIENT_TOKEN", "")

# Calculators read stored provider rates locally; never refresh on reads.
FX_RATE_STALE_AFTER_SECONDS = int(os.getenv("FX_RATE_STALE_AFTER_SECONDS", "3600"))

# Flutterwave v3: test/live keys use the same v3 host. Configuration is validated
# only when ingestion runs, so missing/invalid credentials do not block startup.
FLUTTERWAVE_SECRET_KEY = os.getenv("FLUTTERWAVE_SECRET_KEY", "")
FLUTTERWAVE_BASE_URL = os.getenv("FLUTTERWAVE_BASE_URL", "https://api.flutterwave.com")
# Optional override. Missing/blank/[] uses the adapter's built-in collection pairs.
FLUTTERWAVE_FX_SCENARIOS = os.getenv("FLUTTERWAVE_FX_SCENARIOS", "[]")

# Fincra secrets are environment-specific; never use a live key in sandbox.
FINCRA_SECRET_KEY = os.getenv("FINCRA_SECRET_KEY", "")
FINCRA_BASE_URL = os.getenv("FINCRA_BASE_URL", "https://sandboxapi.fincra.com")

# Shared API authentication abuse controls (enforced in database across workers).
AUTH_LOGIN_ACCOUNT_LIMIT = int(os.getenv("AUTH_LOGIN_ACCOUNT_LIMIT", "10"))
AUTH_LOGIN_IP_LIMIT = int(os.getenv("AUTH_LOGIN_IP_LIMIT", "60"))
AUTH_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "900"))
AUTH_OTP_MAX_ATTEMPTS = int(os.getenv("AUTH_OTP_MAX_ATTEMPTS", "5"))
AUTH_OTP_IP_LIMIT = int(os.getenv("AUTH_OTP_IP_LIMIT", "60"))
AUTH_OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("AUTH_OTP_RESEND_COOLDOWN_SECONDS", "60"))
AUTH_EMAIL_IP_LIMIT = int(os.getenv("AUTH_EMAIL_IP_LIMIT", "20"))
AUTH_EMAIL_ACCOUNT_LIMIT = int(os.getenv("AUTH_EMAIL_ACCOUNT_LIMIT", "3"))
INGESTION_WORKER_POLL_SECONDS = int(os.getenv("INGESTION_WORKER_POLL_SECONDS", "5"))
INGESTION_JOB_LEASE_SECONDS = int(os.getenv("INGESTION_JOB_LEASE_SECONDS", "300"))
INGESTION_JOB_MAX_ATTEMPTS = int(os.getenv("INGESTION_JOB_MAX_ATTEMPTS", "3"))
