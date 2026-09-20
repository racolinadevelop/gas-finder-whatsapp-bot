"""Isolated tests for sending WhatsApp prompts independently of the handler."""

import pytest

from app.conversation import ConversationSession, ConversationState
from app.presentation.delivery import deliver_prompt
from app.presentation.prompts import ListPrompt, ReplyButtonsPrompt, TextPrompt


SENDER = "15551234567"


@pytest.mark.parametrize(
    ("state", "expected_kinds"),
    [
        (ConversationState.WAITING_LANGUAGE, ["primary_buttons"]),
        (ConversationState.WAITING_LOCATION, ["text", "navigation_buttons"]),
        (ConversationState.WAITING_RESULTS, ["primary_buttons"]),
    ],
)
def test_delivery_preserves_primary_then_navigation_order(state, expected_kinds):
    calls = []
    primary = (
        TextPrompt("Comparte tu ubicación")
        if state == ConversationState.WAITING_LOCATION
        else ReplyButtonsPrompt("Elige", [{"id": "lang_es", "title": "Español"}])
    )

    def send_buttons(**kwargs):
        calls.append((
            "primary_buttons"
            if kwargs["buttons"][0]["id"] == "lang_es"
            else "navigation_buttons",
            kwargs,
        ))

    def send_text(**kwargs):
        calls.append(("text", kwargs))

    deliver_prompt(
        SENDER,
        primary,
        ConversationSession(sender=SENDER, state=state, language="es"),
        send_buttons=send_buttons,
        send_list=lambda **kwargs: calls.append(("list", kwargs)),
        send_text=send_text,
    )

    assert [kind for kind, _ in calls] == expected_kinds
    if state == ConversationState.WAITING_LOCATION:
        assert [b["id"] for b in calls[-1][1]["buttons"]] == [
            "nav_back", "nav_menu",
        ]


def test_list_prompt_is_sent_before_navigation():
    calls = []

    deliver_prompt(
        SENDER,
        ListPrompt(
            body_text="Distance",
            button_text="Choose",
            section_title="Miles",
            rows=[{"id": "distance_3", "title": "3 miles"}],
        ),
        ConversationSession(
            sender=SENDER, state=ConversationState.WAITING_DISTANCE,
            language="en",
        ),
        send_buttons=lambda **kwargs: calls.append(("buttons", kwargs)),
        send_list=lambda **kwargs: calls.append(("list", kwargs)),
        send_text=lambda **kwargs: calls.append(("text", kwargs)),
    )

    assert [kind for kind, _ in calls] == ["list", "buttons"]
    assert calls[0][1]["rows"][0]["id"] == "distance_3"


def test_no_session_does_not_append_navigation():
    calls = []

    deliver_prompt(
        SENDER,
        TextPrompt("Hello"),
        None,
        send_buttons=lambda **kwargs: calls.append("buttons"),
        send_list=lambda **kwargs: calls.append("list"),
        send_text=lambda **kwargs: calls.append("text"),
    )

    assert calls == ["text"]
