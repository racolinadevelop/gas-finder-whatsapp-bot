"""Deliver guided WhatsApp prompts without managing conversation state.

WhatsApp cannot combine a list-picker and reply buttons in one message.
Put each step's choices and Back/Menu into one list instead of sending
an additional, visually disconnected navigation message.
"""

from collections.abc import Callable

from app.conversation import ConversationSession, ConversationState
from app.i18n import t
from app.presentation.prompts import (
    ListPrompt,
    Prompt,
    ReplyButtonsPrompt,
    TextPrompt,
)


def _navigation_rows(language: str) -> list[dict]:
    return [
        {
            "id": "nav_back",
            "title": t(language, "button_nav_back"),
            "description": t(language, "nav_back_description"),
        },
        {
            "id": "nav_menu",
            "title": t(language, "button_nav_menu"),
            "description": t(language, "nav_menu_description"),
        },
    ]


def _send_navigation_list(sender: str, language: str, send_list: Callable) -> None:
    send_list(
        to=sender,
        body_text=t(language, "navigation_list_prompt"),
        button_text=t(language, "navigation_list_button"),
        section_title=t(language, "navigation_list_section"),
        rows=_navigation_rows(language),
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
    """Deliver one combined choice + navigation list whenever possible."""
    state = session.state if session is not None else None
    language = session.language if session is not None else "en"

    if isinstance(prompt, ReplyButtonsPrompt):
        if state in {ConversationState.WAITING_FUEL, ConversationState.WAITING_SORT}:
            # The three choices and two navigation actions fit in one list.
            prefix = "fuel" if state == ConversationState.WAITING_FUEL else "sort"
            send_list(
                to=sender,
                body_text=prompt.body_text,
                button_text=t(language, f"{prefix}_list_button"),
                section_title=t(language, f"{prefix}_list_section"),
                rows=[
                    {"id": button["id"], "title": button["title"]}
                    for button in prompt.buttons
                ] + _navigation_rows(language),
            )
        elif state == ConversationState.WAITING_RESULTS:
            _send_navigation_list(sender, language, send_list)
        else:
            # Language selection stays simple: no Back/Menu before a language.
            send_buttons(
                to=sender,
                body_text=prompt.body_text,
                buttons=prompt.buttons,
            )
        return

    if isinstance(prompt, ListPrompt):
        rows = prompt.rows
        if state not in {
            None, ConversationState.NEW, ConversationState.WAITING_LANGUAGE
        }:
            rows = [*rows, *_navigation_rows(language)]
        send_list(
            to=sender,
            body_text=prompt.body_text,
            button_text=prompt.button_text,
            section_title=prompt.section_title,
            rows=rows,
        )
        return

    if isinstance(prompt, TextPrompt):
        send_text(to=sender, message=prompt.message)
        # Native share-location and custom-distance entry use separate
        # WhatsApp messages; these cannot contain a list in the same bubble.
        if state not in {
            None, ConversationState.NEW,
            ConversationState.WAITING_LANGUAGE, ConversationState.WAITING_RESULTS,
        }:
            _send_navigation_list(sender, language, send_list)
