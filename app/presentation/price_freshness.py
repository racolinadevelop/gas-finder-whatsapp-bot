"""Present provider-reported fuel-price timestamps without additional API calls."""

from datetime import datetime, timedelta, timezone

from app.i18n import t

# A conservative display warning, not a guarantee of actual pump-price accuracy.
PRICE_STALE_AFTER = timedelta(hours=48)
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


def price_update_lines(
    updated_at: str | None,
    *,
    language: str,
    now: datetime | None = None,
) -> list[str]:
    """Return localized price-source information for one selected fuel.

    Unknown, malformed, timezone-less and implausibly future timestamps are
    not interpreted as fresh. A provider timestamp describes the last reported
    price update, not a verified price at the pump.
    """
    if not isinstance(updated_at, str) or not updated_at.strip():
        return [t(language, "price_update_unknown")]

    try:
        reported = datetime.fromisoformat(updated_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return [t(language, "price_update_unknown")]

    if reported.tzinfo is None or reported.utcoffset() is None:
        return [t(language, "price_update_unknown")]

    current = datetime.now(timezone.utc) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    reported = reported.astimezone(timezone.utc)
    current = current.astimezone(timezone.utc)
    if reported > current + MAX_FUTURE_CLOCK_SKEW:
        return [t(language, "price_update_unknown")]

    lines = [
        t(
            language,
            "price_last_reported",
            timestamp=reported.strftime("%Y-%m-%d %H:%M UTC"),
        ),
    ]
    if current - reported >= PRICE_STALE_AFTER:
        lines.append(t(language, "price_may_be_stale"))
    return lines
