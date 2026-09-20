"""Regression coverage for the guided flow's router registrations."""

from app.conversation import ConversationSession, ConversationState
from app.models import IncomingMessage
from app.routing.whatsapp_routers import build_whatsapp_routers


SENDER = "15551234567"


class FakeStateHandlers:
    def __init__(self, events):
        self.events = events

    def distance_text(self, message, session):
        self.events.append(("distance_text", session.state))

    def menu_interaction(self, message, session):
        self.events.append(("menu", session.state))

    def fuel_interaction(self, message, session):
        self.events.append(("fuel", session.state))

    def sort_interaction(self, message, session):
        self.events.append(("sort", session.state))

    def distance_interaction(self, message, session):
        self.events.append(("distance_button", session.state))


def test_router_wiring_preserves_registered_types_states_and_dispatch():
    events = []
    text_router, interactive_router, location_router, message_router = (
        build_whatsapp_routers(
            state_handlers=FakeStateHandlers(events),
            search_from_location=lambda message, session: events.append(
                ("location_search", session.state)
            ),
            handle_text=lambda message: events.append(("text", message)),
            handle_interactive=lambda message: events.append(("interactive", message)),
            handle_location=lambda message: events.append(("location", message)),
            handle_unsupported=lambda message: events.append(("unsupported", message)),
        )
    )
    assert text_router.registered_states == (
        ConversationState.WAITING_DISTANCE,
        ConversationState.WAITING_CUSTOM_DISTANCE,
    )
    assert interactive_router.registered_states == (
        ConversationState.MAIN_MENU,
        ConversationState.WAITING_FUEL,
        ConversationState.WAITING_SORT,
        ConversationState.WAITING_DISTANCE,
    )
    assert location_router.registered_states == (ConversationState.WAITING_LOCATION,)
    assert message_router.registered_types == ("text", "interactive", "location")

    text_message = IncomingMessage(sender=SENDER, message_type="text", text="3")
    for state in text_router.registered_states:
        assert text_router.dispatch(
            text_message, ConversationSession(sender=SENDER, state=state)
        ) is True
        assert events.pop() == ("distance_text", state)

    interactive_message = IncomingMessage(
        sender=SENDER, message_type="interactive", selection_id="fuel_regular"
    )
    for state, label in [
        (ConversationState.MAIN_MENU, "menu"),
        (ConversationState.WAITING_FUEL, "fuel"),
        (ConversationState.WAITING_SORT, "sort"),
        (ConversationState.WAITING_DISTANCE, "distance_button"),
    ]:
        assert interactive_router.dispatch(
            interactive_message, ConversationSession(sender=SENDER, state=state)
        ) is True
        assert events.pop() == (label, state)

    location_message = IncomingMessage(
        sender=SENDER, message_type="location", latitude=38.25, longitude=-85.75
    )
    assert location_router.dispatch(
        location_message,
        ConversationSession(sender=SENDER, state=ConversationState.WAITING_LOCATION),
    ) is True
    assert events.pop() == ("location_search", ConversationState.WAITING_LOCATION)

    for kind in message_router.registered_types:
        msg = IncomingMessage(sender=SENDER, message_type=kind)
        assert message_router.dispatch(msg) is True
        assert events.pop() == (kind, msg)

    image = IncomingMessage(sender=SENDER, message_type="image")
    assert message_router.dispatch(image) is False
    assert events.pop() == ("unsupported", image)


def test_unregistered_state_stays_unhandled():
    events = []
    text_router, interactive_router, location_router, _ = build_whatsapp_routers(
        state_handlers=FakeStateHandlers(events),
        search_from_location=lambda msg, session: events.append("location"),
        handle_text=lambda msg: None,
        handle_interactive=lambda msg: None,
        handle_location=lambda msg: None,
        handle_unsupported=lambda msg: None,
    )
    msg = IncomingMessage(sender=SENDER, message_type="text", text="hello")
    session = ConversationSession(
        sender=SENDER, state=ConversationState.WAITING_LANGUAGE
    )
    assert text_router.dispatch(msg, session) is False
    assert interactive_router.dispatch(msg, session) is False
    assert location_router.dispatch(msg, session) is False
    assert events == []
