from __future__ import annotations


FOCUS_ASSET_CODES: set[str] = {
    "BTC",
    "USDT",
    "ETH",
    "XAUT",
    "USDC",
    "TRX",
    "DASH",
    "LTC",
    "XRP",
    "SOL",
    "QDX",
    "BNB",
    "DOGE",
}

ALLOWED_QUOTE_CURRENCIES: set[str] = {
    "NGN",
    "USDT",
}


def is_focus_asset(code: str | None) -> bool:
    if not code:
        return False
    return code.upper() in FOCUS_ASSET_CODES


def is_allowed_quote_currency(code: str | None) -> bool:
    if not code:
        return False
    return code.upper() in ALLOWED_QUOTE_CURRENCIES
