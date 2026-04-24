"""Tango / MakeGov API integration for VM2-OPP opportunity intelligence."""
from .client import TangoClient, TangoAPIError, TangoAuthError, TangoRateLimitError
from .normalizer import normalize_opportunity, normalize_forecast, normalize_contract

__all__ = [
    "TangoClient",
    "TangoAPIError",
    "TangoAuthError",
    "TangoRateLimitError",
    "normalize_opportunity",
    "normalize_forecast",
    "normalize_contract",
]
