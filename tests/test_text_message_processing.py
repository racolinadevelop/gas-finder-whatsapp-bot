"""Text processing should not change the existing guided conversation flow."""

from app.conversation import ConversationSession, ConversationState, NavigationAction, SearchFlowPrompt
from app.handlers.text_messages import process_text_message
from app.intelligence import IntentType, MessageInterpretation
from app.models import IncomingMessage


SENDER = "15551234567"


def process(text, *, state=ConversationState.WAITING_FUEL, interpretation=None,
            dispatch_result=False, profile_name=None):
    events = []
    session = ConversationSession(sender=SENDER, state=state, language="es")

    def unexpected(*args, **kwargs):
        raise AssertionError("Should not interpret or change the flow here")

    def interpreter(value):
        events.append(("interpret", value))
        if interpretation is None:
            raise AssertionError("Text must not be interpreted for this case")
        return interpretation

    process_text_message(
        IncomingMessage(
            sender=SENDER, message_type="text", text=text,
            profile_name=profile_name,
        ),
        navigate=lambda sender, action: events.append(("navigate", sender, action)),
        begin=lambda sender, **kwargs: events.append(("begin", sender, kwargs)),
        send_language=lambda sender, **kwargs: events.append(("language", sender, kwargs)),
        get_session=lambda sender: session,
        dispatch_state_text=lambda message, current: (
            events.append(("state", current.state)) or dispatch_result
        ),
        send_expected=lambda sender, current: events.append(("expected", current.state)),
        interpret=interpreter,
        ensure_started=lambda sender: events.append(("ensure", sender)) or session,
        apply_decision=lambda sender, decision: events.append(("decision", decision)),
    )
    return events


def test_navigation_is_prioritized_before_greeting_state_and_intent():
    assert process("menú") == [("navigate", SENDER, NavigationAction.MENU)]
    assert process("Atrás") == [("navigate", SENDER, NavigationAction.BACK)]


def test_greeting_keeps_profile_name_and_language_step():
    assert process("  HOLA  ", profile_name="Ramon") == [
        ("begin", SENDER, {"profile_name": "Ramon"}),
        ("language", SENDER, {"display_name": "Ramon"}),
    ]


def test_custom_distance_text_is_handled_by_current_state():
    assert process(
        "3", state=ConversationState.WAITING_CUSTOM_DISTANCE, dispatch_result=True
    ) == [("state", ConversationState.WAITING_CUSTOM_DISTANCE)]


def test_waiting_for_location_reprompts_without_overwriting_preferences():
    assert process("diesel más barato", state=ConversationState.WAITING_LOCATION) == [
        ("state", ConversationState.WAITING_LOCATION),
        ("expected", ConversationState.WAITING_LOCATION),
    ]


def test_unrelated_text_uses_existing_session_for_expected_prompt():
    events = process(
        "xyz",
        interpretation=MessageInterpretation(intent=IntentType.UNKNOWN),
    )
    assert events == [
        ("state", ConversationState.WAITING_FUEL),
        ("interpret", "xyz"),
        ("ensure", SENDER),
        ("expected", ConversationState.WAITING_FUEL),
    ]


def test_search_intent_uses_existing_pure_decision_and_applies_it():
    events = process(
        "busca gasolina",
        interpretation=MessageInterpretation(
            intent=IntentType.SEARCH_GAS, language="es"
        ),
    )
    assert events[:2] == [
        ("state", ConversationState.WAITING_FUEL),
        ("interpret", "busca gasolina"),
    ]
    sender, decision = events[2][0], events[2][1]
    assert sender == "decision"
    assert decision.prompt == SearchFlowPrompt.FUEL
    assert decision.language == "es"
