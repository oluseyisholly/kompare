"""Present published cells without silently assigning an unresolved metric a meaning."""

import re
from decimal import Decimal, InvalidOperation

from app.schemas.mutual_fund import PublishedFundMetricRead

MISSING_MARKERS = {"", "-", "–", "—", "n/a", "na", "nil"}
MAPPED_FIELDS = {
    "bidprice": "bid_price",
    "offerprice": "offer_price",
    "yeartodatereturns": "ytd_return_percent",
}


def build_published_metrics(snapshot, context, *, currency):
    headers = context.get("headers", [])
    rows = context.get("latest_rows") or []
    if not rows or not isinstance(rows[0], dict):
        return []
    cells = rows[0].get("cells", [])
    if len(headers) != len(cells):
        return []
    metrics = []
    for label, raw_value in zip(headers, cells):
        key = re.sub(r"[^a-z0-9]", "", label.lower())
        mapped = MAPPED_FIELDS.get(key)
        unresolved = key == "effectiveyielddayondayreturn"
        if mapped is None and not unresolved:
            continue
        missing = raw_value.strip().lower() in MISSING_MARKERS
        value = getattr(snapshot, mapped) if mapped else None
        status = "not_published" if missing else "available"
        if unresolved and not missing:
            # The adapter already validated this cell independently. Keep malformed
            # evidence visible without promoting it into a financial value.
            parsed = (rows[0].get("unresolved_metric") or {}).get("parsed_percent")
            try:
                value = Decimal(parsed) if parsed is not None else None
            except (InvalidOperation, TypeError):
                value = None
        if value is None and not missing:
            status = "invalid"
        data = dict(
            label=label,
            raw_value=raw_value,
            value=value,
            unit=currency if mapped in {"bid_price", "offer_price"} else "percent",
            mapped_field=mapped,
            status=status,
            interpretation="unresolved_yield_or_daily_return" if unresolved else "normalized",
        )
        try:
            metrics.append(PublishedFundMetricRead(**data))
        except ValueError:
            # Non-finite/out-of-range unresolved values stay as original text.
            data.update(value=None, status="invalid")
            metrics.append(PublishedFundMetricRead(**data))
    return metrics
