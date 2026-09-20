from app.services.google_places import search_nearby_gas_stations


class FakeGoogleTextResponse:
    def __init__(self, places, next_page_token=None):
        self._places = places
        self._next_page_token = next_page_token

    def raise_for_status(self):
        return None

    def json(self):
        data = {"places": self._places}
        if self._next_page_token:
            data["nextPageToken"] = self._next_page_token
        return data


def google_place(place_id, name, address, latitude, longitude, price):
    units = int(price)
    nanos = round((price - units) * 1_000_000_000)
    return {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": address,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "fuelOptions": {
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
        },
    }


def test_google_text_search_follows_page_tokens_and_finds_later_candidates(
    monkeypatch,
):
    responses = [
        FakeGoogleTextResponse(
            [
                google_place(
                    "1",
                    "Speedway",
                    "1 Main St",
                    38.2501,
                    -85.7501,
                    3.25,
                )
            ],
            next_page_token="page-2",
        ),
        FakeGoogleTextResponse(
            [
                google_place(
                    "2",
                    "Sam's Club",
                    "4901 Outer Loop",
                    38.2510,
                    -85.7510,
                    2.79,
                )
            ],
            next_page_token="page-3",
        ),
        FakeGoogleTextResponse(
            [
                google_place(
                    "3",
                    "Kroger Fuel Center",
                    "3 Main St",
                    38.2520,
                    -85.7520,
                    3.10,
                )
            ]
        ),
    ]
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers.copy(),
                "payload": json.copy(),
            }
        )
        return responses[len(calls) - 1]

    monkeypatch.setattr("app.services.google_places.httpx.post", fake_post)
    # Explicit exhaustive mode preserves the original later-page regression.
    monkeypatch.setattr("app.services.google_places.GOOGLE_TEXT_MAX_PAGES", 3)

    result = search_nearby_gas_stations(
        latitude=38.25,
        longitude=-85.75,
        radius=16093.44,
        fuel_type="regular",
        sort="price",
        limit=5,
    )

    assert len(calls) == 3
    assert calls[0]["url"].endswith("places:searchText")
    assert calls[0]["payload"]["textQuery"] == "gas station"
    assert calls[0]["payload"]["includedType"] == "gas_station"
    assert calls[0]["payload"]["strictTypeFiltering"] is True
    assert calls[0]["payload"]["pageSize"] == 20
    assert "pageToken" not in calls[0]["payload"]
    assert calls[1]["payload"]["pageToken"] == "page-2"
    assert calls[2]["payload"]["pageToken"] == "page-3"
    assert "nextPageToken" in calls[0]["headers"]["X-Goog-FieldMask"]
    assert result["stations"][0]["name"] == "Sam's Club"
    assert result["stations"][0]["selected_fuel"]["price"] == 2.79


def test_google_text_search_keeps_results_inside_requested_radius(monkeypatch):
    responses = [
        FakeGoogleTextResponse(
            [
                google_place(
                    "near",
                    "Nearby Station",
                    "1 Near St",
                    38.2501,
                    -85.7501,
                    3.20,
                ),
                google_place(
                    "far",
                    "Far Station",
                    "999 Far St",
                    38.35,
                    -85.75,
                    2.50,
                ),
            ]
        )
    ]

    monkeypatch.setattr(
        "app.services.google_places.httpx.post",
        lambda *args, **kwargs: responses[0],
    )

    result = search_nearby_gas_stations(
        latitude=38.25,
        longitude=-85.75,
        radius=1609.344,
        fuel_type="regular",
        sort="price",
        limit=5,
    )

    assert result["count"] == 1
    assert result["stations"][0]["name"] == "Nearby Station"


def test_budget_mode_stops_after_two_pages_even_if_more_are_offered(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json.copy())
        return FakeGoogleTextResponse(
            [google_place(
                str(len(calls)), "Station " + str(len(calls)),
                str(len(calls)) + " Main St", 38.25, -85.75,
                3.00 + len(calls) / 10,
            )],
            next_page_token="more-" + str(len(calls)),
        )

    monkeypatch.setattr("app.services.google_places.httpx.post", fake_post)
    monkeypatch.setattr("app.services.google_places.GOOGLE_TEXT_MAX_PAGES", 2)

    result = search_nearby_gas_stations(
        latitude=38.25,
        longitude=-85.75,
        radius=5000,
        fuel_type="regular",
        sort="price",
        limit=5,
    )

    assert len(calls) == 2
    assert "pageToken" not in calls[0]
    assert calls[1]["pageToken"] == "more-1"
    assert result["count"] == 2


def test_strict_budget_can_use_one_page(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json)
        return FakeGoogleTextResponse(
            [google_place("one", "One", "1 Main St", 38.25, -85.75, 3.0)],
            next_page_token="unused",
        )

    monkeypatch.setattr("app.services.google_places.httpx.post", fake_post)
    monkeypatch.setattr("app.services.google_places.GOOGLE_TEXT_MAX_PAGES", 1)

    result = search_nearby_gas_stations(
        latitude=38.25, longitude=-85.75, fuel_type="regular",
    )
    assert result["count"] == 1
    assert len(calls) == 1
