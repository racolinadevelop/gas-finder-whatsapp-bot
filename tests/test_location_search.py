from app.conversation import ConversationSession, ConversationState
from app.services.location_search import LocationSearchService


def test_location_search_uses_saved_distance_and_preferences():
    search_call = {}
    reply_call = {}

    def fake_station_search(**kwargs):
        search_call.update(kwargs)
        return {"stations": [{"name": "Example"}]}

    def fake_reply_builder(result, **kwargs):
        reply_call["result"] = result
        reply_call.update(kwargs)
        return "Formatted stations"

    service = LocationSearchService(
        station_search=fake_station_search,
        reply_builder=fake_reply_builder,
    )
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )

    reply = service.search(
        session=session,
        latitude=38.2527,
        longitude=-85.7585,
    )

    assert reply == "Formatted stations"
    assert search_call == {
        "latitude": 38.2527,
        "longitude": -85.7585,
        "radius": 4828.032,
        "fuel_type": "premium",
        "sort": "price",
        "limit": 5,
        "gallons_needed": 10,
        "vehicle_mpg": 25,
    }
    assert reply_call == {
        "result": {"stations": [{"name": "Example"}]},
        "language": "es",
        "fuel_type": "premium",
        "sort": "price",
        "max_distance_miles": 3,
    }


def test_location_search_uses_default_radius_without_saved_distance():
    search_call = {}

    def fake_station_search(**kwargs):
        search_call.update(kwargs)
        return {"stations": []}

    service = LocationSearchService(
        station_search=fake_station_search,
        reply_builder=lambda result, **kwargs: "No stations",
    )

    reply = service.search(
        session=ConversationSession(sender="15551234567"),
        latitude=38.2527,
        longitude=-85.7585,
    )

    assert reply == "No stations"
    assert search_call["radius"] == 5000


def test_location_search_allows_result_parameters_to_be_configured():
    search_call = {}

    def fake_station_search(**kwargs):
        search_call.update(kwargs)
        return {"stations": []}

    service = LocationSearchService(
        station_search=fake_station_search,
        reply_builder=lambda result, **kwargs: "No stations",
        result_limit=10,
        gallons_needed=15,
        vehicle_mpg=30,
    )

    service.search(
        session=ConversationSession(sender="15551234567"),
        latitude=38.2527,
        longitude=-85.7585,
    )

    assert search_call["limit"] == 10
    assert search_call["gallons_needed"] == 15
    assert search_call["vehicle_mpg"] == 30
