"""Route interactive WhatsApp selections without owning shared runtime state."""

from collections.abc import Callable, Mapping

from app.conversation import (
    ConversationSession,
    ConversationState,
    NavigationAction,
    parse_navigation_action,
)
from app.models import IncomingMessage
from app.favorites.commands import parse_favorite_action
from app.handlers.plan_messages import PLAN_SELECTION_ID


def process_interactive_message(
    incoming_message: IncomingMessage,
    *,
    navigate: Callable[[str, NavigationAction], None],
    ensure_started: Callable[[str], ConversationSession],
    language_buttons: Mapping[str, str],
    select_language: Callable[..., None],
    dispatch_state_interactive: Callable[[IncomingMessage, ConversationSession], bool],
    send_expected: Callable[[str, ConversationSession], None],
    show_plan: Callable[[str], None] | None = None,
    show_favorite: Callable[[str, str, int | str | None], None] | None = None,
    start_search: Callable[[str], None] | None = None,
    create_test_checkout: Callable[[str], None] | None = None,
    manage_test_subscription: Callable[[str], None] | None = None,
) -> None:
    """Prioritize global navigation and reject stale language buttons."""
    sender = incoming_message.sender
    button_id = incoming_message.selection_id or ""
    navigation_action = parse_navigation_action(button_id)

    if navigation_action is not None:
        navigate(sender, navigation_action)
        return

    if button_id == "home_search" and start_search is not None:
        start_search(sender)
        return

    if button_id == PLAN_SELECTION_ID and show_plan is not None:
        show_plan(sender)
        return

    if button_id == "account_test_checkout" and create_test_checkout is not None:
        create_test_checkout(sender)
        return

    if button_id == "account_test_portal" and manage_test_subscription is not None:
        manage_test_subscription(sender)
        return

    favorite_action = parse_favorite_action(selection_id=button_id)
    if show_favorite is not None and favorite_action is not None:
        show_favorite(sender, *favorite_action)
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
