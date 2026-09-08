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
CARDTONIC_KYC_URL = os.getenv("CARDTONIC_KYC_URL", "https://help.cardtonic.com/en/articles/6811777-what-is-kyc-and-how-does-it-apply-to-cardtonic")

TBAY_BASE_URL = os.getenv("TBAY_BASE_URL", "https://api.tbay.store")
TBAY_SITE_URL = os.getenv("TBAY_SITE_URL", "https://h5.tbay.store")
TBAY_CLIENT_VERSION = os.getenv("TBAY_CLIENT_VERSION", "1.10.16")
TBAY_SIGNING_SALT = os.getenv("TBAY_SIGNING_SALT", "IgaO0cpIJp")

SECRET_KEY = os.getenv("SECRET_KEY", "kompare-dev-secret")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

ENABLE_INGESTION_SCHEDULER = _get_bool("ENABLE_INGESTION_SCHEDULER", False)
INGESTION_SCHEDULER_POLL_SECONDS = int(os.getenv("INGESTION_SCHEDULER_POLL_SECONDS", "60"))
