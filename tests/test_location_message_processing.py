"""Regression tests for incoming location routing."""

from app.conversation import ConversationSession, ConversationState
from app.handlers.location_messages import process_location_message
from app.models import IncomingMessage


SENDER = "15551234567"


def location(*, latitude=38.25, longitude=-85.75):
    return IncomingMessage(
        sender=SENDER,
        message_type="location",
        latitude=latitude,
        longitude=longitude,
    )


def test_missing_coordinate_does_not_access_storage_or_send_message():
    events = []

    def accessed(*args, **kwargs):
        events.append("unexpected")
        raise AssertionError("Invalid location must be ignored")

    process_location_message(
        location(longitude=None),
        get_session=accessed,
        search_from_location=accessed,
        dispatch_state_location=accessed,
        send_expected=accessed,
    )
    process_location_message(
        location(latitude=None),
        get_session=accessed,
        search_from_location=accessed,
        dispatch_state_location=accessed,
        send_expected=accessed,
    )
    assert events == []


def test_new_user_location_uses_default_session_for_search():
    message = location()
    events = []

    def search(incoming, session):
        assert incoming is message
        assert session == ConversationSession(sender=SENDER)
        events.append("search")

    process_location_message(
        message,
        get_session=lambda sender: None,
        search_from_location=search,
        dispatch_state_location=lambda *args: events.append("unexpected"),
        send_expected=lambda *args: events.append("unexpected"),
    )
    assert events == ["search"]


def test_active_location_step_dispatches_saved_session():
    message = location()
    session = ConversationSession(
        sender=SENDER,
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )
    events = []

    def dispatch(incoming, actual_session):
        assert incoming is message
        assert actual_session is session
        events.append("dispatch")
        return True

    process_location_message(
        message,
        get_session=lambda sender: session,
        search_from_location=lambda *args: events.append("unexpected"),
        dispatch_state_location=dispatch,
        send_expected=lambda *args: events.append("unexpected"),
    )
    assert events == ["dispatch"]


def test_out_of_sequence_location_reprompts_without_searching():
    message = location()
    session = ConversationSession(
        sender=SENDER,
        state=ConversationState.WAITING_SORT,
        language="es",
    )
    events = []

    process_location_message(
        message,
        get_session=lambda sender: session,
        search_from_location=lambda *args: events.append("unexpected"),
        dispatch_state_location=lambda incoming, actual: (
            events.append("dispatch") or False
        ),
        send_expected=lambda sender, actual: (
            events.append(("expected", sender, actual))
        ),
    )
    assert events == ["dispatch", ("expected", SENDER, session)]
