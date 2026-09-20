"""The extracted search-flow delivery keeps navigation and state rules."""

import pytest

from app.conversation import ConversationSession, ConversationState, SearchFlowDecision, SearchFlowPrompt
from app.handlers.search_flow_delivery import deliver_search_flow_decision
from app.services.whatsapp import WhatsAppServiceError


SENDER = "15551234567"


@pytest.mark.parametrize(
    ("prompt", "expected", "flags"),
    [
        (SearchFlowPrompt.FUEL, "fuel", {}),
        (SearchFlowPrompt.SORT, "sort", {"selected": True}),
        (SearchFlowPrompt.DISTANCE, "distance", {}),
        (SearchFlowPrompt.LOCATION, "location", {"saved": True}),
    ],
)
def test_decision_applies_changes_then_sends_one_prompt(prompt, expected, flags):
    events = []
    session = ConversationSession(
        sender=SENDER,
        state=ConversationState.WAITING_FUEL,
        language="es",
    )
    changes = {"language": "es", "fuel_type": "diesel"}
    decision = SearchFlowDecision(
        prompt=prompt,
        language="es",
        session_changes=changes,
        selected=True,
        saved=True,
    )

    def apply_changes(sender, passed_changes):
        assert sender == SENDER
        assert passed_changes == changes
        events.append("applied")
        return session

    def send(name):
        def inner(*args, **kwargs):
            events.append((name, args, kwargs))
        return inner

    deliver_search_flow_decision(
        SENDER,
        decision,
        apply_changes=apply_changes,
        send_text=send("text"),
        send_fuel=send("fuel"),
        send_sort=send("sort"),
        send_distance=send("distance"),
        send_location=send("location"),
    )

    assert events == ["applied", (expected, (SENDER, "es") if expected == "fuel" else (SENDER, session), flags)]


def test_invalid_distance_keeps_state_and_sends_localized_validation():
    messages = []
    decision = SearchFlowDecision(
        prompt=SearchFlowPrompt.INVALID_DISTANCE,
        language="es",
        session_changes={"state": ConversationState.WAITING_LOCATION},
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid input must not change state or send a prompt")

    deliver_search_flow_decision(
        SENDER, decision,
        apply_changes=forbidden,
        send_text=lambda **kwargs: messages.append(kwargs),
        send_fuel=forbidden,
        send_sort=forbidden,
        send_distance=forbidden,
        send_location=forbidden,
    )

    assert len(messages) == 1
    assert messages[0]["to"] == SENDER
    assert "distancia" in messages[0]["message"].lower()


def test_validation_send_error_does_not_change_state():
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid input must not advance state")

    def failed_send(**kwargs):
        raise WhatsAppServiceError("unavailable")

    deliver_search_flow_decision(
        SENDER,
        SearchFlowDecision(
            prompt=SearchFlowPrompt.INVALID_DISTANCE,
            language="en",
        ),
        apply_changes=forbidden,
        send_text=failed_send,
        send_fuel=forbidden,
        send_sort=forbidden,
        send_distance=forbidden,
        send_location=forbidden,
    )
