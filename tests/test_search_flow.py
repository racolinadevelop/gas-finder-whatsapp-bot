from app.conversation import (
    ConversationSession,
    ConversationState,
    SearchFlowPrompt,
    decide_search_flow,
)
from app.intelligence import IntentType, MessageInterpretation


def interpretation(**changes):
    values = {
        "intent": IntentType.SEARCH_GAS,
        "language": "en",
    }
    values.update(changes)
    return MessageInterpretation(**values)


def test_invalid_distance_does_not_change_session():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_FUEL,
        language="es",
    )

    decision = decide_search_flow(
        session,
        interpretation(max_distance_miles=100),
    )

    assert decision.prompt == SearchFlowPrompt.INVALID_DISTANCE
    assert decision.language == "es"
    assert decision.session_changes == {}


def test_fuel_selection_advances_to_sort_for_expected_state():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_FUEL,
        language="es",
    )

    decision = decide_search_flow(
        session,
        interpretation(language="es", fuel_type="diesel"),
    )

    assert decision.prompt == SearchFlowPrompt.SORT
    assert decision.selected is True
    assert decision.session_changes == {
        "state": ConversationState.WAITING_SORT,
        "language": "es",
        "fuel_type": "diesel",
    }


def test_distance_only_preserves_waiting_sort_step():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_SORT,
        language="en",
        fuel_type="premium",
    )

    decision = decide_search_flow(
        session,
        interpretation(max_distance_miles=2),
    )

    assert decision.prompt == SearchFlowPrompt.SORT
    assert decision.session_changes == {"max_distance_miles": 2}


def test_sort_selection_without_distance_advances_to_distance_step():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_SORT,
        language="es",
        fuel_type="premium",
    )

    decision = decide_search_flow(
        session,
        interpretation(language="es", sort="price"),
    )

    assert decision.prompt == SearchFlowPrompt.DISTANCE
    assert decision.session_changes == {
        "state": ConversationState.WAITING_DISTANCE,
        "language": "es",
        "sort": "price",
    }


def test_sort_selection_with_saved_distance_advances_to_location():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_SORT,
        language="en",
        fuel_type="regular",
        max_distance_miles=3,
    )

    decision = decide_search_flow(
        session,
        interpretation(sort="best"),
    )

    assert decision.prompt == SearchFlowPrompt.LOCATION
    assert decision.saved is True
    assert decision.session_changes["state"] == (
        ConversationState.WAITING_LOCATION
    )


def test_search_without_preferences_starts_guided_fuel_step():
    decision = decide_search_flow(None, interpretation(language="es"))

    assert decision.prompt == SearchFlowPrompt.FUEL
    assert decision.session_changes == {
        "state": ConversationState.WAITING_FUEL,
        "language": "es",
    }


def test_complete_preferences_advance_directly_to_location():
    decision = decide_search_flow(
        None,
        interpretation(
            language="es",
            fuel_type="diesel",
            sort="price",
            max_distance_miles=5,
        ),
    )

    assert decision.prompt == SearchFlowPrompt.LOCATION
    assert decision.saved is True
    assert decision.session_changes == {
        "state": ConversationState.WAITING_LOCATION,
        "language": "es",
        "fuel_type": "diesel",
        "sort": "price",
        "max_distance_miles": 5,
    }
