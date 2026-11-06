"""Compatibility names. Normalized FX contracts live in app.schemas.fx."""

from app.schemas.fx import Amount, Currency, Nonnegative, Positive
from app.schemas.fx import FxCurrencyRead as WiseCurrencyRead
from app.schemas.fx import FxCurrencyRecord as WiseCurrencyRecord
from app.schemas.fx import FxFeeRead as WiseFeeRead
from app.schemas.fx import FxPaymentOptionRead as WisePaymentOptionRead
from app.schemas.fx import FxQuoteRead as WiseQuoteRead
from app.schemas.fx import FxQuoteRequest as WiseQuoteRequest
from app.schemas.fx import FxReferenceRate as WiseReferenceRate
from app.schemas.fx import FxReferenceRateRead as WiseReferenceRateRead

__all__ = [
    "Amount",
    "Currency",
    "Nonnegative",
    "Positive",
    "WiseQuoteRequest",
    "WiseReferenceRate",
    "WiseReferenceRateRead",
    "WiseFeeRead",
    "WisePaymentOptionRead",
    "WiseQuoteRead",
    "WiseCurrencyRecord",
    "WiseCurrencyRead",
]
