from app.conversation import (
    ConversationState,
    ConversationTransitions,
    InMemoryConversationStore,
    NavigationAction,
)


def build_transitions():
    store = InMemoryConversationStore()
    return store, ConversationTransitions(store)


def test_begin_preserves_existing_preferences():
    store, transitions = build_transitions()
    store.update(
        "sender",
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )

    session = transitions.begin("sender")

    assert session.state == ConversationState.WAITING_LANGUAGE
    assert session.language == "es"
    assert session.fuel_type == "premium"
    assert session.sort == "price"
    assert session.max_distance_miles == 3


def test_ensure_started_creates_only_missing_session():
    store, transitions = build_transitions()

    created = transitions.ensure_started("new-sender")
    existing = transitions.ensure_started("new-sender")

    assert created.state == ConversationState.WAITING_LANGUAGE
    assert existing is created
    assert store.get("new-sender") is created


def test_menu_navigation_resets_all_preferences():
    store, transitions = build_transitions()
    store.update(
        "sender",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="diesel",
        sort="price",
        max_distance_miles=5,
    )

    session = transitions.navigate("sender", NavigationAction.MENU)

    assert session.state == ConversationState.WAITING_LANGUAGE
    assert session.language == "en"
    assert session.fuel_type == "regular"
    assert session.sort == "best"
    assert session.max_distance_miles is None


def test_back_navigation_preserves_preferences():
    store, transitions = build_transitions()
    store.update(
        "sender",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )

    session = transitions.navigate("sender", NavigationAction.BACK)

    assert session.state == ConversationState.WAITING_DISTANCE
    assert session.language == "es"
    assert session.fuel_type == "premium"
    assert session.sort == "price"
    assert session.max_distance_miles == 3


def test_language_selection_starts_clean_guided_search():
    store, transitions = build_transitions()
    store.update("sender", max_distance_miles=10, sort="price")

    session = transitions.select_language("sender", "es")

    assert session.state == ConversationState.WAITING_FUEL
    assert session.language == "es"
    assert session.fuel_type == "regular"
    assert session.sort == "best"
    assert session.max_distance_miles is None


def test_fuel_selection_advances_to_sort():
    _, transitions = build_transitions()

    session = transitions.select_fuel("sender", "diesel")

    assert session.state == ConversationState.WAITING_SORT
    assert session.fuel_type == "diesel"


def test_sort_selection_requests_distance_when_none_is_saved():
    _, transitions = build_transitions()

    session = transitions.select_sort("sender", "price")

    assert session.state == ConversationState.WAITING_DISTANCE
    assert session.sort == "price"


def test_sort_selection_requests_location_when_distance_is_saved():
    store, transitions = build_transitions()
    store.update("sender", max_distance_miles=3)

    session = transitions.select_sort("sender", "best")

    assert session.state == ConversationState.WAITING_LOCATION
    assert session.max_distance_miles == 3


def test_selecting_distance_advances_to_location():
    _, transitions = build_transitions()

    session = transitions.select_distance("sender", 4.5)

    assert session.state == ConversationState.WAITING_LOCATION
    assert session.max_distance_miles == 4.5


def test_custom_distance_selection_changes_only_state():
    store, transitions = build_transitions()
    store.update("sender", language="es", fuel_type="premium")

    session = transitions.request_custom_distance("sender")

    assert session.state == ConversationState.WAITING_CUSTOM_DISTANCE
    assert session.language == "es"
    assert session.fuel_type == "premium"


def test_apply_updates_interpreted_search_changes():
    _, transitions = build_transitions()

    session = transitions.apply(
        "sender",
        {
            "state": ConversationState.WAITING_LOCATION,
            "language": "es",
            "fuel_type": "diesel",
            "sort": "price",
        },
    )

    assert session.state == ConversationState.WAITING_LOCATION
    assert session.language == "es"
    assert session.fuel_type == "diesel"
    assert session.sort == "price"


def test_finish_removes_and_returns_session():
    store, transitions = build_transitions()
    expected = store.update(
        "sender",
        state=ConversationState.WAITING_LOCATION,
    )

    removed = transitions.finish("sender")

    assert removed == expected
    assert store.get("sender") is None


def test_results_back_returns_to_location_with_saved_preferences():
    store, transitions = build_transitions()
    store.update(
        "sender",
        state=ConversationState.WAITING_RESULTS,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
        profile_name="Ramon",
    )
    session = transitions.navigate("sender", NavigationAction.BACK)

    assert session.state == ConversationState.WAITING_LOCATION
    assert session.language == "es"
    assert session.fuel_type == "premium"
    assert session.sort == "price"
    assert session.max_distance_miles == 3
    assert session.profile_name == "Ramon"


def test_menu_resets_preferences_but_keeps_display_name():
    store, transitions = build_transitions()
    store.update(
        "sender",
        state=ConversationState.WAITING_RESULTS,
        profile_name="Ramon",
        language="es",
        fuel_type="diesel",
    )
    session = transitions.navigate("sender", NavigationAction.MENU)

    assert session.state == ConversationState.WAITING_LANGUAGE
    assert session.profile_name == "Ramon"
    assert session.language == "en"
    assert session.fuel_type == "regular"
