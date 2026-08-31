from __future__ import annotations

from app.core.focus_assets import is_allowed_quote_currency, is_focus_asset
from app.models.provider_asset import ProviderAsset


class FocusAssetSelector:
    def should_use_provider_asset(self, provider_asset: ProviderAsset | None) -> bool:
        if provider_asset is None or provider_asset.asset is None:
            return False

        if not is_focus_asset(provider_asset.asset.code):
            return False

        metadata_json = provider_asset.metadata_json or {}
        quote_unit = metadata_json.get("quote_unit")
        if quote_unit and not is_allowed_quote_currency(str(quote_unit)):
            return False

        return True

    def should_use_pair(self, *, base_code: str | None, quote_code: str | None) -> bool:
        return is_focus_asset(base_code) and is_allowed_quote_currency(quote_code)
