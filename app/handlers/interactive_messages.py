"""Route interactive WhatsApp selections without owning shared runtime state."""

from collections.abc import Callable, Mapping

from app.conversation import (
    ConversationSession,
    ConversationState,
    NavigationAction,
    parse_navigation_action,
)
from app.models import IncomingMessage


def process_interactive_message(
    incoming_message: IncomingMessage,
    *,
    navigate: Callable[[str, NavigationAction], None],
    ensure_started: Callable[[str], ConversationSession],
    language_buttons: Mapping[str, str],
    select_language: Callable[..., None],
    dispatch_state_interactive: Callable[[IncomingMessage, ConversationSession], bool],
    send_expected: Callable[[str, ConversationSession], None],
) -> None:
    """Prioritize global navigation and reject stale language buttons."""
    sender = incoming_message.sender
    button_id = incoming_message.selection_id or ""
    navigation_action = parse_navigation_action(button_id)

    if navigation_action is not None:
        navigate(sender, navigation_action)
        return

    session = ensure_started(sender)

    if button_id in language_buttons:
        # WhatsApp keeps old interactive messages available to tap. A language
        # choice may only advance the active language-selection step.
        if session.state != ConversationState.WAITING_LANGUAGE:
            send_expected(sender, session)
            return

        select_language(
            sender,
            language_buttons[button_id],
            display_name=incoming_message.profile_name,
        )
        return

    if not dispatch_state_interactive(incoming_message, session):
        send_expected(sender, session)
