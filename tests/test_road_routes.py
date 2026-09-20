"""Optional road-distance enrichment has bounded external API usage."""

import httpx

from app.conversation import ConversationSession
from app.services.location_search import LocationSearchService
from app.services.road_routes import add_road_routes
from app.services.whatsapp import build_gas_stations_reply


def places(count=5):
    return {
        "stations": [
            {
                "name": "Station " + str(i),
                "address": str(i) + " Main St",
                "latitude": 38.25 + i / 1000,
                "longitude": -85.75 - i / 1000,
                "distance_miles": 0.25 + i / 10,
                "open_now": True,
                "selected_fuel": {"price": 3.20, "available": True},
            }
            for i in range(count)
        ],
        "count": count,
    }


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.request = httpx.Request("POST", "https://routes.googleapis.com/")
        self.response = httpx.Response(status_code, request=self.request)

    def raise_for_status(self):
        self.response.raise_for_status()

    def json(self):
        return self.data


def test_route_matrix_uses_one_request_with_capped_destinations(monkeypatch):
    calls = []

    def post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "payload": json})
        return FakeResponse([
            {"originIndex": 0, "destinationIndex": 1, "condition": "ROUTE_EXISTS",
             "status": {}, "distanceMeters": 3218.688, "duration": "480s"},
            {"originIndex": 0, "destinationIndex": 0, "condition": "ROUTE_EXISTS",
             "status": {}, "distanceMeters": 1609.344, "duration": "145s"},
        ])

    monkeypatch.setattr("app.services.road_routes.httpx.post", post)
    original = places()
    enriched = add_road_routes(
        original,
        latitude=38.25,
        longitude=-85.75,
        api_key="test-key",
        max_destinations=2,
    )

    assert len(calls) == 1
    assert calls[0]["url"].endswith("computeRouteMatrix")
    assert len(calls[0]["payload"]["origins"]) == 1
    assert len(calls[0]["payload"]["destinations"]) == 2
    assert calls[0]["payload"]["routingPreference"] == "TRAFFIC_UNAWARE"
    assert calls[0]["headers"]["X-Goog-FieldMask"].endswith("distanceMeters,duration")
    assert [station.get("road_distance_miles") for station in enriched["stations"]] == [
        1.0, 2.0, None, None, None,
    ]
    assert [station.get("road_eta_minutes") for station in enriched["stations"][:2]] == [
        3, 8,
    ]
    assert original["stations"][0].get("road_distance_miles") is None
    assert enriched["stations"][0]["distance_miles"] == original["stations"][0]["distance_miles"]


def test_failed_matrix_does_not_replace_geographic_distance(monkeypatch):
    monkeypatch.setattr(
        "app.services.road_routes.httpx.post",
        lambda *args, **kwargs: FakeResponse({}, status_code=403),
    )
    original = places(2)
    assert add_road_routes(
        original, latitude=38.25, longitude=-85.75, api_key="test-key",
    ) is original


def test_missing_route_or_invalid_duration_is_not_mislabeled(monkeypatch):
    monkeypatch.setattr(
        "app.services.road_routes.httpx.post",
        lambda *args, **kwargs: FakeResponse([
            {"originIndex": 0, "destinationIndex": 0,
             "condition": "ROUTE_NOT_FOUND"},
            {"originIndex": 0, "destinationIndex": 1,
             "condition": "ROUTE_EXISTS", "status": {},
             "distanceMeters": 1000, "duration": "invalid"},
        ]),
    )
    enriched = add_road_routes(
        places(2), latitude=38.25, longitude=-85.75, api_key="test-key",
    )
    assert all("road_eta_minutes" not in station for station in enriched["stations"])


def test_zero_stations_or_missing_key_avoids_routes_request(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Routes API must not be called")

    monkeypatch.setattr("app.services.road_routes.httpx.post", unexpected)
    assert add_road_routes(
        {"stations": []}, latitude=38.25, longitude=-85.75,
        api_key="test-key",
    ) == {"stations": []}
    result = places(2)
    assert add_road_routes(
        result, latitude=38.25, longitude=-85.75, api_key=None,
    ) is result


def test_location_search_only_invokes_routes_after_explicit_opt_in():
    original = places(2)
    events = []

    def fake_enricher(result, **kwargs):
        events.append(kwargs)
        assert result is original
        return {**result, "route_added": True}

    base_kwargs = {
        "station_search": lambda **kwargs: original,
        "reply_builder": lambda result, **kwargs: result,
        "route_enricher": fake_enricher,
    }
    disabled = LocationSearchService(**base_kwargs, routes_enabled=False)
    assert disabled.search(
        session=ConversationSession(sender="15551234567"),
        latitude=38.25, longitude=-85.75,
    ) is original
    assert events == []

    enabled = LocationSearchService(**base_kwargs, routes_enabled=True)
    result = enabled.search(
        session=ConversationSession(sender="15551234567"),
        latitude=38.25, longitude=-85.75,
    )
    assert result["route_added"] is True
    assert events == [{"latitude": 38.25, "longitude": -85.75}]


def test_whatsapp_reply_uses_real_driving_distance_as_its_only_distance():
    station = places(1)["stations"][0]
    station["road_distance_miles"] = 1.57
    station["road_eta_minutes"] = 5
    reply = build_gas_stations_reply(
        {"stations": [station], "routes_requested": True},
        language="es",
        sort="distance",
    )
    assert "Distancia: 1.57 mi" in reply
    assert "Tiempo estimado: 5 min" in reply
    assert "0.25 mi" not in reply
    assert "en línea recta" not in reply
    assert "Por carretera:" not in reply
    assert "Cómo llegar:" not in reply
    assert "google.com/maps/dir/" not in reply


def test_route_failure_does_not_misrepresent_geographic_miles_as_driving():
    station = places(1)["stations"][0]
    for language, expected in [
        ("en", "Driving distance unavailable"),
        ("es", "Distancia por carretera no disponible"),
    ]:
        reply = build_gas_stations_reply(
            {"stations": [station], "routes_requested": True},
            language=language,
            sort="distance",
        )
        assert expected in reply
        assert "0.25 mi" not in reply
        assert "google.com/maps/dir/" not in reply


def test_routes_disabled_keeps_geographic_distance_clearly_approximate():
    station = places(1)["stations"][0]
    for language, expected in [
        ("en", "Approx. distance: 0.25 mi"),
        ("es", "Distancia aproximada: 0.25 mi"),
    ]:
        reply = build_gas_stations_reply(
            {"stations": [station]},
            language=language,
            sort="distance",
        )
        assert expected in reply
        assert "straight line" not in reply
        assert "en línea recta" not in reply
        assert "google.com/maps/dir/" not in reply
