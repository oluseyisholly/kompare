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

ENABLE_INGESTION_SCHEDULER = _get_bool("ENABLE_INGESTION_SCHEDULER", False)
INGESTION_SCHEDULER_POLL_SECONDS = int(os.getenv("INGESTION_SCHEDULER_POLL_SECONDS", "60"))
