"""The extracted interactive handler preserves navigation and state safety."""

from app.conversation import ConversationSession, ConversationState, NavigationAction
from app.handlers.interactive_messages import process_interactive_message
from app.models import IncomingMessage


SENDER = "15551234567"
LANGUAGE_BUTTONS = {"lang_en": "en", "lang_es": "es"}


def run_selection(selection_id, *, state, dispatch_result=False, profile_name=None):
    events = []
    session = ConversationSession(sender=SENDER, state=state, language="es")
    message = IncomingMessage(
        sender=SENDER,
        message_type="interactive",
        selection_id=selection_id,
        profile_name=profile_name,
    )

    def started(sender):
        events.append(("ensure", sender))
        return session

    def state_dispatch(incoming, active_session):
        assert incoming is message
        assert active_session is session
        events.append(("dispatch", active_session.state))
        return dispatch_result

    process_interactive_message(
        message,
        navigate=lambda sender, action: events.append(("navigate", sender, action)),
        ensure_started=started,
        language_buttons=LANGUAGE_BUTTONS,
        select_language=lambda sender, language, **kwargs: events.append(
            ("language", sender, language, kwargs)
        ),
        dispatch_state_interactive=state_dispatch,
        send_expected=lambda sender, active: events.append(
            ("expected", sender, active.state)
        ),
    )
    return events


def test_back_and_menu_take_priority_without_changing_conversation():
    assert run_selection("nav_back", state=ConversationState.WAITING_LOCATION) == [
        ("navigate", SENDER, NavigationAction.BACK)
    ]
    assert run_selection("nav_menu", state=ConversationState.WAITING_SORT) == [
        ("navigate", SENDER, NavigationAction.MENU)
    ]


def test_language_button_works_only_during_language_step():
    assert run_selection(
        "lang_es", state=ConversationState.WAITING_LANGUAGE,
        profile_name="Ramon",
    ) == [
        ("ensure", SENDER),
        ("language", SENDER, "es", {"display_name": "Ramon"}),
    ]


def test_stale_language_button_cannot_reset_pending_location():
    assert run_selection(
        "lang_en", state=ConversationState.WAITING_LOCATION
    ) == [
        ("ensure", SENDER),
        ("expected", SENDER, ConversationState.WAITING_LOCATION),
    ]


def test_valid_fuel_button_dispatches_to_state_router():
    assert run_selection(
        "fuel_regular",
        state=ConversationState.WAITING_FUEL,
        dispatch_result=True,
    ) == [
        ("ensure", SENDER),
        ("dispatch", ConversationState.WAITING_FUEL),
    ]


def test_unexpected_selection_reprompts_in_current_state():
    assert run_selection(
        "fuel_regular",
        state=ConversationState.WAITING_LOCATION,
    ) == [
        ("ensure", SENDER),
        ("dispatch", ConversationState.WAITING_LOCATION),
        ("expected", SENDER, ConversationState.WAITING_LOCATION),
    ]
