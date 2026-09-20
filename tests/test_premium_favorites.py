"""Premium favorites are read-only to Free users and require no extra provider calls."""

from datetime import datetime, timedelta, timezone

import pytest

from app.favorites import (
    FavoriteStoreError,
    InMemoryFavoriteStore,
    SearchReply,
    parse_favorite_action,
    shown_stations,
)
from app.favorites.models import FavoriteStation
from app.services.location_search import LocationSearchService
from app.conversation import ConversationSession


SENDER = "15551234567"
OTHER = "15559999999"


def station(i, **extra):
    return {"id": f"google-id-{i}", "name": f"Station {i}",
            "address": f"{i} Main St", "latitude": 38.2,
            "longitude": -85.7, "selected_fuel": {"price": 3.0},
            **extra}


def test_shown_stations_mirror_five_visible_results_without_coordinates_or_prices():
    stations = [station(0, open_now=False)] + [station(i) for i in range(1, 9)]
    shown = shown_stations(stations)
    assert len(shown) == 5
    assert [s.name for s in shown] == [f"Station {i}" for i in range(1, 6)]
    assert "latitude" not in repr(shown)
    assert "price" not in repr(shown)
    assert shown[0].key == "place:google-id-1"


@pytest.mark.parametrize("text,expected", [
    ("mis favoritas", ("list", None)),
    ("MY FAVORITES", ("list", None)),
    ("Guardar 2", ("save", 2)),
    ("save favorite 5", ("save", 5)),
    ("eliminar favorita 2", ("remove", 2)),
    ("remove favorite 1", ("remove", 1)),
    ("premium", None),
    ("guardar 6", None),
    ("save fuel", None),
])
def test_favorite_commands_are_explicit(text, expected):
    assert parse_favorite_action(text=text) == expected


def test_global_button_id_validation():
    assert parse_favorite_action(selection_id="fav_save_2") == ("save", 2)
    assert parse_favorite_action(selection_id="fav_save_6") is None
    assert parse_favorite_action(selection_id="fav_list") == ("list", None)


def test_favorite_store_is_user_isolated_idempotent_and_removable():
    store = InMemoryFavoriteStore()
    shown = shown_stations([station(1), station(2)])
    store.record_results(SENDER, shown)
    assert store.list_favorites(SENDER) == ()
    assert store.add_from_recent(SENDER, 2) == shown[1]
    assert store.add_from_recent(SENDER, 2) == shown[1]
    assert store.list_favorites(SENDER) == (shown[1],)
    assert store.list_favorites(OTHER) == ()
    with pytest.raises(FavoriteStoreError, match="no_recent_result"):
        store.add_from_recent(OTHER, 2)
    with pytest.raises(FavoriteStoreError, match="missing_favorite"):
        store.remove_favorite(OTHER, 1)
    assert store.remove_favorite(SENDER, 1) == shown[1]
    assert store.list_favorites(SENDER) == ()


def test_favorites_stale_results_and_ten_station_cap():
    store = InMemoryFavoriteStore()
    for i in range(10):
        store.record_results(SENDER, shown_stations([station(i)]))
        store.add_from_recent(SENDER, 1)
    store.record_results(SENDER, shown_stations([station(99)]))
    with pytest.raises(FavoriteStoreError, match="limit"):
        store.add_from_recent(SENDER, 1)
    store.remove_favorite(SENDER, 1)
    assert store.add_from_recent(SENDER, 1).name == "Station 99"
    store._recent[next(iter(store._recent))] = (
        shown_stations([station(100)]),
        datetime.now(timezone.utc) - timedelta(hours=25),
    )
    with pytest.raises(FavoriteStoreError, match="no_recent_result"):
        store.add_from_recent(SENDER, 1)


def test_search_captures_same_five_stations_with_single_provider_call():
    calls = []
    def provider(**kwargs):
        calls.append(kwargs)
        return {"stations": [station(1), station(2)]}
    service = LocationSearchService(
        station_search=provider, routes_enabled=False,
        reply_builder=lambda result, **kwargs: "Reply from one request",
    )
    session = ConversationSession(sender=SENDER)
    normal = service.search(session=session, latitude=38.25, longitude=-85.75)
    assert normal == "Reply from one request"
    calls.clear()
    reply = service.search(
        session=session, latitude=38.25, longitude=-85.75, capture_results=True,
    )
    assert isinstance(reply, SearchReply)
    assert reply.text == normal
    assert [s.name for s in reply.stations] == ["Station 1", "Station 2"]
    assert len(calls) == 1
