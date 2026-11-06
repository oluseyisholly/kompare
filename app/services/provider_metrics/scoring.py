from enum import Enum

from app.models.enums import MarketCategory


class CoverageSignal(str, Enum):
    ASSETS = "assets"
    QUOTES = "quotes"
    GIFT_CARD_VARIANTS = "gift_card_variants"
    GIFT_CARD_RATES = "gift_card_rates"
    KYC = "kyc"
    FEES = "fees"
    RECENT_SUCCESSFUL_RUN = "recent_successful_run"


COVERAGE_POINTS: dict[MarketCategory, dict[CoverageSignal, int]] = {
    MarketCategory.CRYPTO: {
        CoverageSignal.ASSETS: 25,
        CoverageSignal.QUOTES: 35,
        CoverageSignal.KYC: 20,
        CoverageSignal.FEES: 10,
        CoverageSignal.RECENT_SUCCESSFUL_RUN: 10,
    },
    MarketCategory.GIFTCARD: {
        CoverageSignal.GIFT_CARD_VARIANTS: 35,
        CoverageSignal.GIFT_CARD_RATES: 35,
        CoverageSignal.KYC: 15,
        CoverageSignal.RECENT_SUCCESSFUL_RUN: 15,
    },
    MarketCategory.FX: {
        CoverageSignal.QUOTES: 70,
        CoverageSignal.KYC: 15,
        CoverageSignal.RECENT_SUCCESSFUL_RUN: 15,
    },
    MarketCategory.MUTUAL_FUND: {
        CoverageSignal.QUOTES: 70,
        CoverageSignal.KYC: 15,
        CoverageSignal.RECENT_SUCCESSFUL_RUN: 15,
    },
}


def calculate_coverage_score(
    category: MarketCategory, available_signals: set[CoverageSignal]
) -> int:
    points = COVERAGE_POINTS.get(category, {})
    return min(100, sum(value for signal, value in points.items() if signal in available_signals))
