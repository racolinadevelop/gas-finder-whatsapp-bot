"""Process incoming text while preserving the guided WhatsApp conversation.

The handler supplies active state, prompts, and interpreter so this module
does not own persistence or construct application runtime dependencies.
"""

from collections.abc import Callable

from app.conversation import (
    ConversationSession,
    ConversationState,
    NavigationAction,
    SearchFlowDecision,
    decide_search_flow,
    parse_navigation_action,
)
from app.intelligence import IntentType, MessageInterpretation
from app.models import IncomingMessage
from app.favorites.commands import parse_favorite_action
from app.handlers.plan_messages import is_plan_command


GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hola",
    "good morning",
    "good afternoon",
    "good evening",
}


def process_text_message(
    incoming_message: IncomingMessage,
    *,
    navigate: Callable[[str, NavigationAction], None],
    begin: Callable[..., ConversationSession],
    send_language: Callable[..., None],
    get_session: Callable[[str], ConversationSession | None],
    dispatch_state_text: Callable[[IncomingMessage, ConversationSession], bool],
    send_expected: Callable[[str, ConversationSession], None],
    interpret: Callable[[str], MessageInterpretation],
    ensure_started: Callable[[str], ConversationSession],
    apply_decision: Callable[[str, SearchFlowDecision], None],
    show_plan: Callable[[str], None] | None = None,
    show_favorite: Callable[[str, str, int | None], None] | None = None,
) -> None:
    """Prioritize navigation and current state before interpreting new text."""
    sender = incoming_message.sender
    text = incoming_message.text or ""
    normalized_text = text.lower().strip()
    navigation_action = parse_navigation_action(text)

    if navigation_action is not None:
        navigate(sender, navigation_action)
        return

    if show_plan is not None and is_plan_command(text):
        show_plan(sender)
        return

    favorite_action = parse_favorite_action(text=text)
    if show_favorite is not None and favorite_action is not None:
        show_favorite(sender, *favorite_action)
        return

    if normalized_text in GREETINGS:
        begin(
            sender,
            profile_name=incoming_message.profile_name,
        )
        send_language(
            sender,
            display_name=incoming_message.profile_name,
        )
        return

    current_session = get_session(sender)
    if current_session is not None and dispatch_state_text(
        incoming_message,
        current_session,
    ):
        return

    # Do not silently overwrite saved preferences with unrelated text
    # while waiting for the user's location.
    if (
        current_session is not None
        and current_session.state == ConversationState.WAITING_LOCATION
    ):
        send_expected(sender, current_session)
        return

    interpretation = interpret(text)
    if interpretation.intent != IntentType.SEARCH_GAS:
        session = ensure_started(sender)
        send_expected(sender, session)
        return

    decision = decide_search_flow(get_session(sender), interpretation)
    apply_decision(sender, decision)
