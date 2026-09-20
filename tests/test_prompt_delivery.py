"""Isolated tests for unified WhatsApp choice and navigation lists."""

import pytest

from app.conversation import ConversationSession, ConversationState
from app.presentation.delivery import deliver_prompt
from app.presentation.prompts import ListPrompt, ReplyButtonsPrompt, TextPrompt


SENDER = "15551234567"


def capture():
    calls = []
    return calls, {
        "send_buttons": lambda **kwargs: calls.append(("buttons", kwargs)),
        "send_list": lambda **kwargs: calls.append(("list", kwargs)),
        "send_text": lambda **kwargs: calls.append(("text", kwargs)),
    }


@pytest.mark.parametrize(
    ("state", "primary", "kinds", "ids"),
    [
        (ConversationState.WAITING_LANGUAGE,
         ReplyButtonsPrompt("Elige", [{"id": "lang_es", "title": "Español"}]),
         ["buttons"], ["lang_es"]),
        (ConversationState.WAITING_FUEL,
         ReplyButtonsPrompt("Fuel", [
             {"id": "fuel_regular", "title": "Regular"},
             {"id": "fuel_diesel", "title": "Diesel"},
         ]), ["list"], ["fuel_regular", "fuel_diesel", "nav_back", "nav_menu"]),
        (ConversationState.WAITING_SORT,
         ReplyButtonsPrompt("Sort", [
             {"id": "sort_best", "title": "Best"},
         ]), ["list"], ["sort_best", "nav_back", "nav_menu"]),
        (ConversationState.WAITING_LOCATION, TextPrompt("Location"),
         ["text", "list"], ["nav_back", "nav_menu"]),
        (ConversationState.WAITING_RESULTS,
         ReplyButtonsPrompt("Next", [
             {"id": "nav_back", "title": "Back"},
             {"id": "nav_menu", "title": "Menu"},
         ]), ["list"], ["nav_back", "nav_menu"]),
    ],
)
def test_delivery_unifies_choices_and_navigation(state, primary, kinds, ids):
    calls, transports = capture()
    deliver_prompt(
        SENDER, primary,
        ConversationSession(sender=SENDER, state=state, language="es"),
        **transports,
    )
    assert [kind for kind, _ in calls] == kinds
    last = calls[-1][1]
    choices = last["buttons"] if kinds == ["buttons"] else last["rows"]
    assert [choice["id"] for choice in choices] == ids
    if state == ConversationState.WAITING_SORT:
        assert last["button_text"] == "Elegir categoría"


def test_distance_list_includes_navigation_without_mutating_original_rows():
    calls, transports = capture()
    prompt = ListPrompt(
        body_text="Distance", button_text="Choose", section_title="Miles",
        rows=[{"id": "distance_3", "title": "3 miles"}],
    )
    deliver_prompt(
        SENDER, prompt,
        ConversationSession(
            sender=SENDER, state=ConversationState.WAITING_DISTANCE,
            language="en",
        ),
        **transports,
    )
    assert [kind for kind, _ in calls] == ["list"]
    assert [row["id"] for row in calls[0][1]["rows"]] == [
        "distance_3", "nav_back", "nav_menu",
    ]
    assert len(prompt.rows) == 1


def test_text_with_no_session_does_not_append_navigation():
    calls, transports = capture()
    deliver_prompt(SENDER, TextPrompt("Hello"), None, **transports)
    assert [kind for kind, _ in calls] == ["text"]
