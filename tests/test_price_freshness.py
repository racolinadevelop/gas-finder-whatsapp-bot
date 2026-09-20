"""Price freshness is derived from existing provider data, not new requests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.presentation.price_freshness import price_update_lines
from app.providers.here import HereFuelPricesProvider
from app.services.google_places import search_nearby_gas_stations
from app.services.whatsapp import build_gas_stations_reply


NOW = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("language", ["en", "es"])
def test_recent_provider_report_shows_utc_time_without_stale_warning(language):
    lines = price_update_lines(
        "2026-09-20T13:00:00-04:00", language=language, now=NOW
    )
    assert len(lines) == 1
    assert "2026-09-20 17:00 UTC" in lines[0]
    assert ("Provider price update" if language == "en" else
            "Actualización del precio según proveedor") in lines[0]


@pytest.mark.parametrize("language,warning", [
    ("en", "48+ hours old"),
    ("es", "48+ horas"),
])
def test_price_48_hours_old_has_visible_warning(language, warning):
    timestamp = (NOW - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    lines = price_update_lines(timestamp, language=language, now=NOW)
    assert len(lines) == 2
    assert "2026-09-18 18:00 UTC" in lines[0]
    assert warning in lines[1]


def test_warning_is_based_on_elapsed_time_not_calendar_date():
    nearly_old = (NOW - timedelta(hours=47, minutes=59)).isoformat()
    assert len(price_update_lines(nearly_old, language="en", now=NOW)) == 1


@pytest.mark.parametrize("value", [
    None, "", "   ", "not-a-timestamp", "2026-09-20",
    "2026-09-20T12:00:00", "2026-09-21T12:00:00Z", 1758000000,
])
def test_missing_invalid_naive_or_future_timestamp_is_not_marked_fresh(value):
    for language, unknown in [
        ("en", "Price update time unavailable"),
        ("es", "Fecha del precio no disponible"),
    ]:
        lines = price_update_lines(value, language=language, now=NOW)
        assert len(lines) == 1
        assert unknown in lines[0]


def test_small_clock_skew_is_not_misclassified_as_old():
    timestamp = (NOW + timedelta(minutes=2)).isoformat()
    assert len(price_update_lines(timestamp, language="en", now=NOW)) == 1


def test_naive_test_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        price_update_lines(
            "2026-09-20T12:00:00Z",
            language="en",
            now=datetime(2026, 9, 20),
        )


@pytest.mark.parametrize("language,expected", [
    ("en", "Provider price update"),
    ("es", "Actualización del precio según proveedor"),
])
def test_whatsapp_reply_hides_selected_fuel_update_and_stale_warning(
    language, expected,
):
    station = {
        "name": "Example station",
        "distance_miles": 0.7,
        "open_now": True,
        "selected_fuel": {
            "available": True,
            "price": 2.99,
            "updated_at": "2020-01-02T03:04:00Z",
        },
    }
    message = build_gas_stations_reply(
        {"stations": [station]}, language=language, sort="distance"
    )
    assert expected not in message
    assert "2020-01-02 03:04 UTC" not in message
    assert ("48+ hours old" if language == "en" else "48+ horas") not in message
    assert "$2.990/gal" in message


def test_unknown_price_date_does_not_add_note_and_missing_price_is_shown():
    base = {
        "name": "Example",
        "distance_miles": 0.5,
        "open_now": None,
    }
    with_price = build_gas_stations_reply(
        {"stations": [{**base, "selected_fuel": {
            "available": True, "price": 3.01, "updated_at": None,
        }}]},
        sort="distance",
    )
    assert "Price update time unavailable" not in with_price
    assert "$3.010/gal" in with_price
    assert "48+ hours old" not in with_price

    without_price = build_gas_stations_reply(
        {"stations": [{**base, "selected_fuel": {
            "available": False, "price": None, "updated_at": None,
        }}]},
        sort="distance",
    )
    assert "Price unavailable" in without_price
    assert "Price update time unavailable" not in without_price


def test_google_price_timestamp_reuses_existing_places_response(monkeypatch):
    calls = []

    class FakePlacesResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [{
                    "id": "place-1",
                    "displayName": {"text": "Sample Fuel"},
                    "formattedAddress": "1 Main St",
                    "location": {"latitude": 38.25, "longitude": -85.75},
                    "currentOpeningHours": {"openNow": True},
                    "fuelOptions": {"fuelPrices": [{
                        "type": "REGULAR_UNLEADED",
                        "price": {
                            "units": 3, "nanos": 150000000,
                            "currencyCode": "USD",
                        },
                        "updateTime": "2020-01-02T03:04:00Z",
                    }]},
                }],
            }

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        return FakePlacesResponse()

    monkeypatch.setattr("app.services.google_places.httpx.post", fake_post)
    result = search_nearby_gas_stations(
        latitude=38.25, longitude=-85.75, fuel_type="regular",
        sort="price", limit=5,
    )
    text = build_gas_stations_reply(result, sort="price")

    assert len(calls) == 1
    assert calls[0].endswith("places:searchText")
    assert result["stations"][0]["selected_fuel"]["updated_at"] == (
        "2020-01-02T03:04:00Z"
    )
    assert "2020-01-02 03:04 UTC" not in text
    assert "48+ hours old" not in text


def test_here_price_timestamp_reuses_existing_provider_response(monkeypatch):
    calls = []

    class FakeHereResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"stations": [{
                "id": "here-1",
                "name": "Sample Fuel",
                "address": {"label": "1 Main St"},
                "position": {"lat": 38.25, "lng": -85.75},
                "distance": 100,
                "prices": [{
                    "fuelType": "2", "price": 3.05, "available": True,
                    "modified": "2020-01-02T03:04:00Z",
                }],
            }]}

    def fake_get(url, params, timeout):
        calls.append(url)
        return FakeHereResponse()

    monkeypatch.setattr("app.providers.here.httpx.get", fake_get)
    result = HereFuelPricesProvider(api_key="test-key").search_nearby(
        latitude=38.25, longitude=-85.75, fuel_type="regular",
        sort="price", limit=5,
    )
    text = build_gas_stations_reply(result, language="es", sort="price")

    assert len(calls) == 1
    assert result["stations"][0]["selected_fuel"]["updated_at"] == (
        "2020-01-02T03:04:00Z"
    )
    assert "2020-01-02 03:04 UTC" not in text
    assert "48+ horas" not in text
