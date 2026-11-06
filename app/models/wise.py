"""Compatibility import for the former Wise-only observation model."""

from app.models.fx import FxQuoteObservation as WiseIllustrativeQuote

__all__ = ["WiseIllustrativeQuote"]
