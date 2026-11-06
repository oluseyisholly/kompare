"""Pinned ISO metadata, not exchange rates or provider-supported currencies."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def iso_metadata():
    return json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "iso4217_minor_units.json").read_text()
    )


def currency_precision(code, *, supports_decimals=None, provider_source=None):
    if supports_decimals is False:
        return 0, provider_source
    metadata = iso_metadata()
    places = metadata["minor_units"].get(code)
    # A contradictory provider flag is not evidence of a specific precision.
    if supports_decimals is True and places == 0:
        return None, None
    return (places, metadata["source_url"]) if places is not None else (None, None)
