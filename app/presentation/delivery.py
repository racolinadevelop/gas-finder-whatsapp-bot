"""Deliver guided WhatsApp prompts without managing conversation state.

The handler supplies the current session and transports so delivery remains
independent of session storage, Meta credentials and webhook dispatch.
"""

from collections.abc import Callable

from app.conversation import ConversationSession, ConversationState
from app.presentation.prompts import (
    ListPrompt,
    Prompt,
    ReplyButtonsPrompt,
    TextPrompt,
    build_navigation_prompt,
)


def deliver_prompt(
    sender: str,
    prompt: Prompt,
    session: ConversationSession | None,
    *,
    send_buttons: Callable,
    send_list: Callable,
    send_text: Callable,
) -> None:
    """Send the requested prompt first, then navigation when appropriate."""
    if isinstance(prompt, ReplyButtonsPrompt):
        send_buttons(
            to=sender,
            body_text=prompt.body_text,
            buttons=prompt.buttons,
        )
    elif isinstance(prompt, ListPrompt):
        send_list(
            to=sender,
            body_text=prompt.body_text,
            button_text=prompt.button_text,
            section_title=prompt.section_title,
            rows=prompt.rows,
        )
    elif isinstance(prompt, TextPrompt):
        send_text(to=sender, message=prompt.message)

    # Keep Back/Menu below the primary prompt, including native location.
    # Initial language and final results already have dedicated buttons.
    if session is not None and session.state not in {
        ConversationState.NEW,
        ConversationState.WAITING_LANGUAGE,
        ConversationState.WAITING_RESULTS,
    }:
        navigation = build_navigation_prompt(session.language)
        send_buttons(
            to=sender,
            body_text=navigation.body_text,
            buttons=navigation.buttons,
        )
