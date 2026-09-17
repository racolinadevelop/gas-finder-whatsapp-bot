import pytest

from app.conversation import ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.intelligence import IntentType, RuleBasedIntentInterpreter
from app.models import IncomingMessage


@pytest.fixture
def interpreter():
    return RuleBasedIntentInterpreter()


def test_interprets_spanish_natural_search(interpreter):
    result = interpreter.interpret(
        "Búscame gasolina premium lo más cerca posible"
    )

    assert result.intent == IntentType.SEARCH_GAS
    assert result.fuel_type == "premium"
    assert result.sort == "distance"
    assert result.language == "es"
    assert result.confidence == 0.95


def test_interprets_english_natural_search(interpreter):
    result = interpreter.interpret("I need the cheapest diesel near me")

    assert result.intent == IntentType.SEARCH_GAS
    assert result.fuel_type == "diesel"
    assert result.sort == "best"
    assert result.language == "en"


def test_balanced_request_uses_best_sort(interpreter):
    result = interpreter.interpret(
        "I want regular gas that is cheap but not too far"
    )

    assert result.fuel_type == "regular"
    assert result.sort == "best"


def test_unknown_message_is_not_treated_as_search(interpreter):
    result = interpreter.interpret("How are you today?")

    assert result.intent == IntentType.UNKNOWN
    assert result.search_preferences == {}
    assert result.confidence == 0.0


def test_search_without_preferences_starts_guided_flow(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=sender,
            message_type="text",
            text="Necesito gasolina",
        )
    )

    session = whatsapp_handler.conversation_store.get(sender)
    assert session.state == ConversationState.WAITING_FUEL
    assert session.language == "es"
    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "fuel_regular",
        "fuel_premium",
        "fuel_diesel",
    ]

    whatsapp_handler.conversation_store.clear()


def test_natural_spanish_search_sets_preferences(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=sender,
            message_type="text",
            text="Búscame diésel más barato",
        )
    )

    session = whatsapp_handler.conversation_store.get(sender)
    assert session.state == ConversationState.WAITING_LOCATION
    assert session.language == "es"
    assert session.fuel_type == "diesel"
    assert session.sort == "price"
    assert "Ahora comparte tu ubicación" in sent_messages[0]["message"]

    whatsapp_handler.conversation_store.clear()


def test_fuel_text_advances_expected_fuel_step(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_FUEL,
        language="es",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(sender=sender, message_type="text", text="diésel")
    )

    session = whatsapp_handler.conversation_store.get(sender)
    assert session.state == ConversationState.WAITING_SORT
    assert session.fuel_type == "diesel"
    assert sent_messages[0]["buttons"][0]["id"] == "sort_distance"

    whatsapp_handler.conversation_store.clear()


def test_sort_text_advances_expected_sort_step(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_SORT,
        language="es",
        fuel_type="premium",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(sender=sender, message_type="text", text="más barato")
    )

    session = whatsapp_handler.conversation_store.get(sender)
    assert session.state == ConversationState.WAITING_LOCATION
    assert session.fuel_type == "premium"
    assert session.sort == "price"
    assert "Más barato" in sent_messages[0]["message"]

    whatsapp_handler.conversation_store.clear()
