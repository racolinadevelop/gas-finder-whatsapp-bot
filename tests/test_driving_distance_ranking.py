"""The displayed station ranking uses the actual road distances when enabled."""

from app.conversation import ConversationSession, ConversationState
from app.services.location_search import LocationSearchService
from app.services.road_routes import rank_displayed_stations_by_road
from app.services.whatsapp import build_gas_stations_reply
from app.utils.cost import calculate_estimated_cost


def station(name, *, geographic, road=None, price=3.0, open_now=True):
    entry = {
        "name": name,
        "distance_miles": geographic,
        "selected_fuel": {"available": True, "price": price},
        "open_now": open_now,
        "estimated_cost": calculate_estimated_cost(
            price_per_gallon=price,
            distance_miles=geographic,
            gallons_needed=10,
            vehicle_mpg=25,
        ),
    }
    if road is not None:
        entry["road_distance_miles"] = road
        entry["road_eta_minutes"] = 7
    return entry


def test_closest_order_changes_to_actual_road_distance_among_five_candidates():
    a = station("Near geographically", geographic=0.2, road=4.0)
    b = station("Near by road", geographic=0.8, road=1.1)
    original = {"stations": [a, b], "count": 2}
    ranked = rank_displayed_stations_by_road(
        original, sort="distance", gallons_needed=10, vehicle_mpg=25,
    )
    assert [item["name"] for item in ranked["stations"]] == [
        "Near by road", "Near geographically",
    ]
    assert [item["name"] for item in original["stations"]] == [
        "Near geographically", "Near by road",
    ]
    assert original["stations"][0]["distance_miles"] == 0.2


def test_best_option_recalculates_travel_cost_from_driving_miles():
    a = station("Cheap but long drive", geographic=0.2, road=9, price=2.8)
    b = station("Higher price but short drive", geographic=0.7, road=1, price=2.9)
    original = {"stations": [a, b], "count": 2}
    ranked = rank_displayed_stations_by_road(
        original, sort="best", gallons_needed=10, vehicle_mpg=25,
    )
    assert ranked["stations"][0]["name"] == "Higher price but short drive"
    assert ranked["stations"][0]["estimated_cost"] == calculate_estimated_cost(
        price_per_gallon=2.9, distance_miles=1, gallons_needed=10, vehicle_mpg=25
    )
    assert original["stations"][0]["estimated_cost"] == calculate_estimated_cost(
        price_per_gallon=2.8, distance_miles=0.2, gallons_needed=10, vehicle_mpg=25
    )


def test_unknown_route_never_wins_closest_on_geographic_distance():
    unknown = station("Route unavailable", geographic=0.05)
    known = station("Drive available", geographic=0.5, road=2)
    ranked = rank_displayed_stations_by_road(
        {"stations": [unknown, known]},
        sort="distance", gallons_needed=10, vehicle_mpg=25,
    )
    assert [item["name"] for item in ranked["stations"]] == [
        "Drive available", "Route unavailable",
    ]


def test_hours_priority_stays_first_and_price_order_is_unchanged():
    open_station = station("Open", geographic=0.8, road=4, price=3.5)
    unknown_hours = station(
        "Unknown hours", geographic=0.1, road=0.1, price=2.5, open_now=None
    )
    result = {"stations": [open_station, unknown_hours]}
    assert rank_displayed_stations_by_road(
        result, sort="distance", gallons_needed=10, vehicle_mpg=25
    )["stations"][0]["name"] == "Open"
    assert rank_displayed_stations_by_road(
        result, sort="price", gallons_needed=10, vehicle_mpg=25
    ) is result


def test_all_routes_missing_preserves_candidate_order_and_original_cost():
    a = station("One", geographic=0.1)
    b = station("Two", geographic=0.5)
    result = {"stations": [a, b]}
    assert rank_displayed_stations_by_road(
        result, sort="best", gallons_needed=10, vehicle_mpg=25,
    ) is result


def test_location_search_shows_real_road_distance_without_extra_results():
    first = station("Geographically closest", geographic=0.2, road=3.0)
    second = station("Actually closest", geographic=0.7, road=1.5)
    original = {"stations": [first, second], "count": 2}
    events = []

    def fake_search(**kwargs):
        events.append(("station_search", kwargs))
        return original

    def fake_routes(result, **kwargs):
        assert result is original
        events.append(("route_matrix", kwargs))
        return result

    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="regular",
        sort="distance",
        max_distance_miles=3,
    )
    service = LocationSearchService(
        station_search=fake_search,
        route_enricher=fake_routes,
        routes_enabled=True,
        result_limit=5,
    )
    message = service.search(session=session, latitude=38.25, longitude=-85.75)
    assert [event[0] for event in events] == ["station_search", "route_matrix"]
    assert "1️⃣ Actually closest" in message
    assert "Distancia: 1.50 mi" in message
    assert "Distancia: 3.00 mi" in message
    assert "Distancia aproximada" not in message
    assert "en línea recta" not in message
    assert "Cómo llegar" not in message


def test_location_search_never_labels_route_failure_as_a_driving_mile():
    original = {"stations": [station("No route", geographic=0.3)], "count": 1}
    service = LocationSearchService(
        station_search=lambda **kwargs: original,
        routes_enabled=True,
        route_enricher=lambda result, **kwargs: result,
    )
    message = service.search(
        session=ConversationSession(sender="15551234567", sort="distance"),
        latitude=38.25,
        longitude=-85.75,
    )
    assert "Driving distance unavailable" in message
    assert "Closest option" not in message
    assert "0.30 mi" not in message
