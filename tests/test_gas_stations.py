import pytest

from fastapi.testclient import TestClient
from app.conversation import ConversationSession, ConversationState
from app.main import app
from app.services.google_places import (
    GooglePlacesServiceError,
    search_nearby_gas_stations,
    sort_stations,
)
from app.utils.cost import calculate_estimated_cost
from app.models import IncomingMessage
from app.parsers import parse_incoming_message
from app.services.whatsapp import (
    build_text_reply,
    build_gas_stations_reply,
    parse_search_preferences,
    send_list_message,
    send_reply_buttons,
    WhatsAppServiceError,
)
from app.i18n import t
from app.providers.here import HereFuelPricesProvider
from app.security import internal_api

TEST_INTERNAL_API_TOKEN = "test-internal-token"

client = TestClient(
    app,
    headers={
        "Authorization": f"Bearer {TEST_INTERNAL_API_TOKEN}",
    },
)


@pytest.fixture(autouse=True)
def configure_internal_api_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        TEST_INTERNAL_API_TOKEN,
    )




class FakeGoogleResponse:
    def __init__(self, places):
        self._places = places

    def raise_for_status(self):
        return None

    def json(self):
        return {"places": self._places}


class FakeHereResponse(FakeGoogleResponse):
    def json(self):
        return {"stations": self._places}


def google_place(
    place_id,
    name,
    address,
    latitude,
    longitude,
    price=None,
):
    place = {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": address,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }
    if price is not None:
        units = int(price)
        nanos = round((price - units) * 1_000_000_000)
        place["fuelOptions"] = {
            "fuelPrices": [
                {
                    "type": "REGULAR_UNLEADED",
                    "price": {
                        "units": units,
                        "nanos": nanos,
                        "currencyCode": "USD",
                    },
                    "updateTime": "2026-09-17T12:00:00Z",
                }
            ]
        }
    return place


def test_search_evaluates_more_candidates_before_selecting_results(monkeypatch):
    captured_payload = {}
    places = [
        google_place("1", "Nearest", "1 Main St", 38.2501, -85.7501, 4.10),
        google_place("2", "No price", "2 Main St", 38.2502, -85.7502),
        google_place("3", "Duplicate A", "3 Main St", 38.2503, -85.7503),
        google_place("4", "Duplicate B", "3 Main St", 38.2503, -85.7503, 4.20),
        google_place("5", "Another no price", "5 Main St", 38.2505, -85.7505),
        google_place("6", "Sam's Club", "4901 Outer Loop", 38.2510, -85.7510, 2.79),
    ]

    def fake_post(url, headers, json, timeout):
        captured_payload.update(json)
        return FakeGoogleResponse(places)

    monkeypatch.setattr("app.services.google_places.httpx.post", fake_post)

    result = search_nearby_gas_stations(
        latitude=38.25,
        longitude=-85.75,
        radius=16093.44,
        fuel_type="regular",
        sort="price",
        limit=5,
    )

    assert captured_payload["maxResultCount"] == 20
    assert result["stations"][0]["name"] == "Sam's Club"
    assert all(
        station["selected_fuel"]["available"] for station in result["stations"]
    )
    assert [station["address"] for station in result["stations"]].count(
        "3 Main St"
    ) == 1


def test_search_applies_display_limit_after_price_filtering(monkeypatch):
    places = [
        google_place(
            str(index),
            f"Station {index}",
            f"{index} Main St",
            38.25 + (index / 10_000),
            -85.75,
            3 + (index / 100),
        )
        for index in range(1, 8)
    ]

    monkeypatch.setattr(
        "app.services.google_places.httpx.post",
        lambda *args, **kwargs: FakeGoogleResponse(places),
    )

    result = search_nearby_gas_stations(
        latitude=38.25,
        longitude=-85.75,
        sort="price",
        limit=5,
    )

    assert result["count"] == 5
    assert len(result["stations"]) == 5


def test_here_provider_requests_prices_and_normalizes_results(monkeypatch):
    captured_params = {}
    stations = [
        {
            "id": "here-1",
            "name": "Sam's Club",
            "distance": 3218,
            "address": {"label": "4901 Outer Loop, Louisville, KY"},
            "position": {"lat": 38.14, "lng": -85.66},
            "prices": [
                {
                    "fuelType": "2",
                    "price": 2.79,
                    "currency": "USD",
                    "available": True,
                    "modified": "2026-09-17T12:00:00Z",
                }
            ],
        },
        {
            "id": "here-2",
            "name": "Unknown price",
            "distance": 100,
            "address": {"label": "1 Main St"},
            "position": {"lat": 38.25, "lng": -85.75},
            "prices": [],
        },
    ]

    def fake_get(url, params, timeout):
        captured_params.update(params)
        return FakeHereResponse(stations)

    monkeypatch.setattr("app.providers.here.httpx.get", fake_get)

    result = HereFuelPricesProvider(api_key="test-key").search_nearby(
        latitude=38.25,
        longitude=-85.75,
        radius=16093.44,
        fuel_type="regular",
        sort="price",
        limit=5,
    )

    assert captured_params["fuelTypes"] == "2"
    assert captured_params["returnAllStations"] == "false"
    assert captured_params["limit"] == 50
    assert result["count"] == 1
    assert result["stations"][0]["name"] == "Sam's Club"
    assert result["stations"][0]["selected_fuel"]["price"] == 2.79


def test_invalid_latitude():
    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 200,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 422


def test_google_timeout(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places took too long to respond.",
            status_code=504,
        )

    monkeypatch.setattr(
        "app.routers.gas_stations.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 504

    assert response.json() == {"detail": "Google Places took too long to respond."}


def test_no_gas_stations(monkeypatch):
    def fake_search(*args, **kwargs):
        return {
            "stations": [],
            "count": 0,
            "message": "No gas stations found in the selected area.",
        }

    monkeypatch.setattr(
        "app.routers.gas_stations.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["stations"] == []


def test_google_authentication_error(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places authentication or permission error.",
            status_code=502,
        )

    monkeypatch.setattr(
        "app.routers.gas_stations.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Google Places authentication or permission error."
    }


def test_google_rate_limit(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places request limit has been reached.",
            status_code=503,
        )

    monkeypatch.setattr(
        "app.routers.gas_stations.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Google Places request limit has been reached."
    }


def test_google_server_error(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places is temporarily unavailable.",
            status_code=503,
        )

    monkeypatch.setattr(
        "app.routers.gas_stations.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Google Places is temporarily unavailable."}


def test_google_connection_error(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Unable to connect to Google Places.",
            status_code=502,
        )

    monkeypatch.setattr(
        "app.routers.gas_stations.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to connect to Google Places."}


def test_sort_stations_by_price():
    stations = [
        {
            "name": "Shell",
            "distance_miles": 0.5,
            "selected_fuel": {
                "available": True,
                "price": 3.19,
            },
        },
        {
            "name": "Speedway",
            "distance_miles": 1.5,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
        {
            "name": "BP",
            "distance_miles": 0.2,
            "selected_fuel": {
                "available": False,
                "price": None,
            },
        },
    ]

    result = sort_stations(stations, "price")

    assert result[0]["name"] == "Speedway"
    assert result[1]["name"] == "Shell"
    assert result[2]["name"] == "BP"


def test_sort_stations_by_distance():
    stations = [
        {
            "name": "Shell",
            "distance_miles": 1.2,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
        {
            "name": "Speedway",
            "distance_miles": 0.4,
            "selected_fuel": {
                "available": True,
                "price": 3.09,
            },
        },
        {
            "name": "BP",
            "distance_miles": 2.1,
            "selected_fuel": {
                "available": False,
                "price": None,
            },
        },
    ]

    result = sort_stations(stations, "distance")

    assert result[0]["name"] == "Speedway"
    assert result[1]["name"] == "Shell"
    assert result[2]["name"] == "BP"


def test_sort_same_price_uses_distance():
    stations = [
        {
            "name": "Shell",
            "distance_miles": 1.8,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
        {
            "name": "Speedway",
            "distance_miles": 0.6,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
    ]

    result = sort_stations(stations, "price")

    assert result[0]["name"] == "Speedway"
    assert result[1]["name"] == "Shell"


def test_invalid_limit():
    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
            "fuel_type": "regular",
            "sort": "distance",
            "limit": 21,
        },
    )

    assert response.status_code == 422


def test_best_option_can_choose_closer_station():
    stations = [
        {
            "name": "Cheap but far",
            "distance_miles": 8.0,
            "selected_fuel": {
                "available": True,
                "price": 2.90,
            },
        },
        {
            "name": "Closer station",
            "distance_miles": 1.0,
            "selected_fuel": {
                "available": True,
                "price": 2.95,
            },
        },
    ]

    for station in stations:
        station["estimated_cost"] = calculate_estimated_cost(
            price_per_gallon=station["selected_fuel"]["price"],
            distance_miles=station["distance_miles"],
            gallons_needed=10,
            vehicle_mpg=25,
        )

    result = sort_stations(stations, "best")

    assert result[0]["name"] == "Closer station"


def test_build_text_reply_for_text_message():
    incoming_message = IncomingMessage(
        sender="15551234567",
        message_type="text",
        message_id="wamid.test",
        text="hello",
    )

    reply = build_text_reply(incoming_message)

    assert reply == (
        "Hi! 👋\n" "Send me your location and I'll find nearby gas stations for you."
    )


def test_build_text_reply_ignores_non_text_message():
    incoming_message = IncomingMessage(
        sender="15551234567",
        message_type="location",
        message_id="wamid.test",
        latitude=38.25,
        longitude=-85.75,
    )

    reply = build_text_reply(incoming_message)

    assert reply is None


def test_build_gas_stations_reply_with_results():
    result = {
        "stations": [
            {
                "name": "Speedway",
                "address": "100 Main St, Louisville, KY",
                "distance_miles": 0.72,
                "selected_fuel": {
                    "available": True,
                    "price": 2.899,
                },
            },
            {
                "name": "Shell",
                "distance_miles": 1.14,
                "selected_fuel": {
                    "available": True,
                    "price": 2.999,
                },
            },
        ]
    }

    reply = build_gas_stations_reply(result)

    assert "Speedway" in reply
    assert "Shell" in reply
    assert "$2.899/gal" in reply
    assert "$2.999/gal" in reply
    assert "0.72 mi" in reply
    assert "1.14 mi" in reply
    assert "Fuel type: Regular" in reply
    assert "Category: Best option" in reply
    assert "Best overall option" in reply
    assert "Regular: $2.899/gal" in reply
    assert "100 Main St, Louisville, KY" in reply


def test_build_gas_stations_reply_without_results():
    result = {"stations": []}

    reply = build_gas_stations_reply(result)

    assert "couldn't find nearby gas stations" in reply.lower()
    assert "Fuel type: Regular" in reply
    assert "Category: Best option" in reply


def test_no_results_reply_includes_maximum_distance():
    reply = build_gas_stations_reply(
        {"stations": []},
        max_distance_miles=3,
    )

    assert "Maximum distance: 3 mi" in reply


def test_best_reply_explains_lower_total_cost_in_spanish():
    stations = [
        {
            "name": "Cercana",
            "distance_miles": 1.0,
            "selected_fuel": {"available": True, "price": 2.95},
        },
        {
            "name": "Barata pero lejana",
            "distance_miles": 8.0,
            "selected_fuel": {"available": True, "price": 2.90},
        },
    ]
    for station in stations:
        station["estimated_cost"] = calculate_estimated_cost(
            price_per_gallon=station["selected_fuel"]["price"],
            distance_miles=station["distance_miles"],
            gallons_needed=10,
            vehicle_mpg=25,
        )

    reply = build_gas_stations_reply(
        {"stations": stations},
        language="es",
        sort="best",
    )

    assert "Barata pero lejana tiene un precio menor" in reply
    assert "costo estimado menor" in reply


def test_build_gas_stations_reply_with_unavailable_price():
    result = {
        "stations": [
            {
                "name": "BP",
                "distance_miles": 0.35,
                "selected_fuel": {
                    "available": False,
                    "price": None,
                },
            }
        ]
    }

    reply = build_gas_stations_reply(
        result,
        fuel_type="premium",
        sort="distance",
    )

    assert "Premium: Price unavailable" in reply
    assert "Closest option" in reply


def test_parse_search_preferences_diesel_cheapest():
    result = parse_search_preferences("diesel cheapest")

    assert result == {
        "fuel_type": "diesel",
        "sort": "price",
    }


def test_parse_search_preferences_premium_closest():
    result = parse_search_preferences("premium closest")

    assert result == {
        "fuel_type": "premium",
        "sort": "distance",
    }


def test_parse_search_preferences_regular_best():
    result = parse_search_preferences("regular best")

    assert result == {
        "fuel_type": "regular",
        "sort": "best",
    }


def test_parse_search_preferences_case_insensitive():
    result = parse_search_preferences("DIESEL CHEAPEST")

    assert result == {
        "fuel_type": "diesel",
        "sort": "price",
    }


def test_parse_search_preferences_empty_text():
    result = parse_search_preferences("")

    assert result == {}


def test_parse_search_preferences_includes_maximum_distance():
    result = parse_search_preferences("premium best within 4 miles")

    assert result == {
        "fuel_type": "premium",
        "sort": "best",
        "max_distance_miles": 4,
    }


def test_send_reply_buttons(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"messages": [{"id": "wamid.test"}]}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_ACCESS_TOKEN",
        "test-token",
    )
    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_PHONE_NUMBER_ID",
        "123456789",
    )
    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_API_VERSION",
        "v25.0",
    )
    monkeypatch.setattr(
        "app.services.whatsapp.httpx.post",
        fake_post,
    )

    result = send_reply_buttons(
        to="15551234567",
        body_text="What fuel are you looking for?",
        buttons=[
            {
                "id": "fuel_regular",
                "title": "Regular",
            },
            {
                "id": "fuel_premium",
                "title": "Premium",
            },
            {
                "id": "fuel_diesel",
                "title": "Diesel",
            },
        ],
    )

    assert result == {"messages": [{"id": "wamid.test"}]}

    assert captured["json"]["type"] == "interactive"

    buttons = captured["json"]["interactive"]["action"]["buttons"]

    assert buttons[0]["reply"]["id"] == "fuel_regular"
    assert buttons[1]["reply"]["id"] == "fuel_premium"
    assert buttons[2]["reply"]["id"] == "fuel_diesel"


def test_send_reply_buttons_rejects_more_than_three_buttons(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_ACCESS_TOKEN",
        "test-token",
    )
    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_PHONE_NUMBER_ID",
        "123456789",
    )

    buttons = [
        {"id": "one", "title": "One"},
        {"id": "two", "title": "Two"},
        {"id": "three", "title": "Three"},
        {"id": "four", "title": "Four"},
    ]

    try:
        send_reply_buttons(
            to="15551234567",
            body_text="Choose an option",
            buttons=buttons,
        )

        assert False, "Expected WhatsAppServiceError"

    except WhatsAppServiceError:
        assert True


def test_send_list_message_builds_interactive_list(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"messages": [{"id": "wamid.list"}]}

    def fake_post(url, headers, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_ACCESS_TOKEN",
        "test-token",
    )
    monkeypatch.setattr(
        "app.services.whatsapp.WHATSAPP_PHONE_NUMBER_ID",
        "123456789",
    )
    monkeypatch.setattr("app.services.whatsapp.httpx.post", fake_post)

    result = send_list_message(
        to="15551234567",
        body_text="Choose a distance",
        button_text="Distances",
        section_title="Search radius",
        rows=[
            {"id": "distance_1", "title": "1 mi"},
            {"id": "distance_custom", "title": "Custom"},
        ],
    )

    interactive = captured["json"]["interactive"]
    assert result == {"messages": [{"id": "wamid.list"}]}
    assert interactive["type"] == "list"
    assert interactive["action"]["button"] == "Distances"
    assert interactive["action"]["sections"][0]["rows"][1]["id"] == (
        "distance_custom"
    )


def test_parse_incoming_interactive_button_reply():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.test",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "fuel_diesel",
                                            "title": "Diesel",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = parse_incoming_message(payload)

    assert result == IncomingMessage(
        sender="15551234567",
        message_type="interactive",
        message_id="wamid.test",
        interactive_type="button_reply",
        selection_id="fuel_diesel",
        selection_title="Diesel",
    )


def test_parse_incoming_text_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.text",
                                    "timestamp": "1789689600",
                                    "type": "text",
                                    "text": {"body": "premium closest"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = parse_incoming_message(payload)

    assert result.sender == "15551234567"
    assert result.message_type == "text"
    assert result.message_id == "wamid.text"
    assert result.timestamp == "1789689600"
    assert result.text == "premium closest"


def test_parse_incoming_location_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.location",
                                    "type": "location",
                                    "location": {
                                        "latitude": 38.2527,
                                        "longitude": -85.7585,
                                        "name": "Downtown Louisville",
                                        "address": "Louisville, KY",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = parse_incoming_message(payload)

    assert result.message_type == "location"
    assert result.latitude == 38.2527
    assert result.longitude == -85.7585
    assert result.location_name == "Downtown Louisville"
    assert result.location_address == "Louisville, KY"


def test_parse_incoming_interactive_list_reply():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.list",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {
                                            "id": "fuel_regular",
                                            "title": "Regular",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = parse_incoming_message(payload)

    assert result.interactive_type == "list_reply"
    assert result.selection_id == "fuel_regular"
    assert result.selection_title == "Regular"


def test_parse_incoming_image_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.image",
                                    "type": "image",
                                    "image": {
                                        "id": "media.image",
                                        "mime_type": "image/jpeg",
                                        "sha256": "image-hash",
                                        "caption": "Gas price sign",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = parse_incoming_message(payload)

    assert result.message_type == "image"
    assert result.media_id == "media.image"
    assert result.mime_type == "image/jpeg"
    assert result.sha256 == "image-hash"
    assert result.caption == "Gas price sign"


def test_parse_incoming_audio_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.audio",
                                    "type": "audio",
                                    "audio": {
                                        "id": "media.audio",
                                        "mime_type": "audio/ogg; codecs=opus",
                                        "sha256": "audio-hash",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    result = parse_incoming_message(payload)

    assert result.message_type == "audio"
    assert result.media_id == "media.audio"
    assert result.mime_type == "audio/ogg; codecs=opus"
    assert result.sha256 == "audio-hash"


def test_parse_incoming_message_ignores_status_event():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.status",
                                    "status": "delivered",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    assert parse_incoming_message(payload) is None


def test_whatsapp_button_flow(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.handlers.whatsapp as whatsapp_handler

    client = TestClient(app)

    sent_button_messages = []
    sent_list_messages = []
    sent_text_messages = []

    def fake_send_reply_buttons(to, body_text, buttons):
        sent_button_messages.append(
            {
                "to": to,
                "body_text": body_text,
                "buttons": buttons,
            }
        )
        return {"messages": [{"id": "wamid.buttons"}]}

    def fake_send_text_message(to, message):
        sent_text_messages.append(
            {
                "to": to,
                "message": message,
            }
        )
        return {"messages": [{"id": "wamid.text"}]}

    def fake_send_list_message(**kwargs):
        sent_list_messages.append(kwargs)
        return {"messages": [{"id": "wamid.list"}]}

    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        fake_send_reply_buttons,
    )

    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        fake_send_text_message,
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_list_message",
        fake_send_list_message,
    )

    whatsapp_handler.conversation_store.clear()

    sender = "15551234567"

    english_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.english",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "lang_en",
                                            "title": "English",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=english_payload,
    )

    assert response.status_code == 200
    assert whatsapp_handler.conversation_store.get(sender).state == (
        ConversationState.WAITING_FUEL
    )

    diesel_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.diesel",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "fuel_diesel",
                                            "title": "Diesel",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=diesel_payload,
    )

    assert response.status_code == 200

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_SORT,
        language="en",
        fuel_type="diesel",
        sort="best",
    )

    assert [row["id"] for row in sent_list_messages[0]["rows"]] == [
        "fuel_regular", "fuel_premium", "fuel_diesel", "nav_back", "nav_menu",
    ]
    assert [row["id"] for row in sent_list_messages[1]["rows"]] == [
        "sort_distance", "sort_price", "sort_best", "nav_back", "nav_menu",
    ]

    cheapest_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.cheapest",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "sort_price",
                                            "title": "Cheapest",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=cheapest_payload,
    )

    assert response.status_code == 200

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_DISTANCE,
        language="en",
        fuel_type="diesel",
        sort="price",
    )

    assert [row["id"] for row in sent_list_messages[0]["rows"]] == [
        "distance_1",
        "distance_3",
        "distance_5",
        "distance_10",
        "distance_custom",
    ]

    distance_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.distance",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {
                                            "id": "distance_5",
                                            "title": "5 mi",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=distance_payload,
    )

    assert response.status_code == 200
    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_LOCATION,
        language="en",
        fuel_type="diesel",
        sort="price",
        max_distance_miles=5,
    )
    assert "Diesel" in sent_text_messages[0]["message"]
    assert "Cheapest" in sent_text_messages[0]["message"]
    assert "Maximum distance: 5 mi" in sent_text_messages[0]["message"]

    whatsapp_handler.conversation_store.clear()


def test_translation_english():
    result = t("en", "choose_fuel")

    assert result == ("⛽ To get started, what type of fuel do you need?")


def test_translation_spanish():
    result = t("es", "choose_fuel")

    assert result == ("⛽ Para comenzar, ¿qué tipo de combustible necesitas?")


def test_translation_with_variables():
    result = t(
        "es",
        "preferences_saved",
        fuel="Diésel",
        sort="Más barato",
    )

    assert "Diésel" in result
    assert "Más barato" in result


def test_translation_falls_back_to_english():
    result = t("fr", "choose_fuel")

    assert result == ("⛽ To get started, what type of fuel do you need?")


def test_whatsapp_spanish_button_flow(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.handlers.whatsapp as whatsapp_handler

    client = TestClient(app)

    sent_button_messages = []
    sent_list_messages = []
    sent_text_messages = []

    def fake_send_reply_buttons(to, body_text, buttons):
        sent_button_messages.append(
            {
                "to": to,
                "body_text": body_text,
                "buttons": buttons,
            }
        )
        return {"messages": [{"id": "wamid.buttons"}]}

    def fake_send_text_message(to, message):
        sent_text_messages.append(
            {
                "to": to,
                "message": message,
            }
        )
        return {"messages": [{"id": "wamid.text"}]}

    def fake_send_list_message(**kwargs):
        sent_list_messages.append(kwargs)
        return {"messages": [{"id": "wamid.list"}]}

    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        fake_send_reply_buttons,
    )

    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        fake_send_text_message,
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_list_message",
        fake_send_list_message,
    )

    whatsapp_handler.conversation_store.clear()

    sender = "15551234567"

    # 1. Select Spanish
    spanish_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.spanish",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "lang_es",
                                            "title": "Español",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=spanish_payload,
    )

    assert response.status_code == 200

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_FUEL,
        language="es",
        fuel_type="regular",
        sort="best",
    )

    assert "¿qué tipo de combustible necesitas?" in (
        sent_list_messages[0]["body_text"]
    )

    assert sent_list_messages[0]["rows"][2]["title"] == "🚛 Diésel"

    # 2. Select Diesel
    diesel_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.diesel",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "fuel_diesel",
                                            "title": "Diésel",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=diesel_payload,
    )

    assert response.status_code == 200

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_SORT,
        language="es",
        fuel_type="diesel",
        sort="best",
    )

    assert [row["id"] for row in sent_list_messages[0]["rows"]][-2:] == [
        "nav_back", "nav_menu",
    ]
    assert sent_list_messages[1]["rows"][0]["title"] == "📍 Más cerca"
    assert sent_list_messages[1]["rows"][1]["title"] == "💵 Más barato"
    assert sent_list_messages[1]["rows"][2]["title"] == "⭐ Mejor opción"

    # 3. Select Cheapest
    cheapest_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.cheapest",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "sort_price",
                                            "title": "Más barato",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=cheapest_payload,
    )

    assert response.status_code == 200

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_DISTANCE,
        language="es",
        fuel_type="diesel",
        sort="price",
    )

    assert sent_list_messages[0]["button_text"] == "Elegir distancia"

    distance_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.distance",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {
                                            "id": "distance_3",
                                            "title": "3 mi",
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post(
        "/api/v1/whatsapp/webhook",
        json=distance_payload,
    )

    assert response.status_code == 200
    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="diesel",
        sort="price",
        max_distance_miles=3,
    )
    assert "Diésel" in sent_text_messages[0]["message"]
    assert "Más barato" in sent_text_messages[0]["message"]
    assert "Ahora comparte tu ubicación" in (sent_text_messages[0]["message"])
    assert "Distancia máxima: 3 mi" in sent_text_messages[0]["message"]

    whatsapp_handler.conversation_store.clear()


def test_build_gas_stations_reply_spanish():
    result = {
        "stations": [
            {
                "name": "Shell",
                "address": "200 Market St, Louisville, KY",
                "distance_miles": 0.56,
                "selected_fuel": {
                    "available": True,
                    "price": 4.10,
                },
            }
        ]
    }

    reply = build_gas_stations_reply(
        result,
        language="es",
        fuel_type="regular",
        sort="price",
    )

    assert "Gasolineras cercanas" in reply
    assert "Combustible: Regular" in reply
    assert "Categoría: Más barato" in reply
    assert "Resultados mostrados: 1" in reply
    assert "Shell" in reply
    assert "$4.100/gal" in reply
    assert "Opción más barata" in reply
    assert "Regular: $4.100/gal" in reply
    assert "Distancia: 0.56 mi" in reply
    assert "200 Market St, Louisville, KY" in reply
