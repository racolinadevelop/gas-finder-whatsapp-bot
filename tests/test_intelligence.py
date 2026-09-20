import json

import httpx
import pytest

from app.conversation import ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.intelligence import (
    AIInterpretationError,
    HybridIntentInterpreter,
    IntentType,
    MessageInterpretation,
    OpenAIIntentInterpreter,
    RuleBasedIntentInterpreter,
    build_intent_interpreter,
)
from app import config
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


def test_interprets_maximum_distance_in_miles(interpreter):
    result = interpreter.interpret("Find regular gas within 3 miles")

    assert result.intent == IntentType.SEARCH_GAS
    assert result.fuel_type == "regular"
    assert result.max_distance_miles == 3
    assert result.search_preferences == {
        "fuel_type": "regular",
        "max_distance_miles": 3,
    }


def test_interprets_spanish_decimal_distance(interpreter):
    result = interpreter.interpret("Búscame diésel a menos de 2,5 millas")

    assert result.language == "es"
    assert result.fuel_type == "diesel"
    assert result.max_distance_miles == 2.5


def test_converts_kilometers_to_miles_without_ai(interpreter):
    result = interpreter.interpret("Gasolina premium dentro de 5 km")

    assert result.language == "es"
    assert result.max_distance_miles == 3.107


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
        "send_list_message",
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
    assert [row["id"] for row in sent_messages[0]["rows"]] == [
        "fuel_regular",
        "fuel_premium",
        "fuel_diesel", "nav_back", "nav_menu",
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
        "send_list_message",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(sender=sender, message_type="text", text="diésel")
    )

    session = whatsapp_handler.conversation_store.get(sender)
    assert session.state == ConversationState.WAITING_SORT
    assert session.fuel_type == "diesel"
    assert sent_messages[0]["rows"][0]["id"] == "sort_distance"

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
        "send_list_message",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(sender=sender, message_type="text", text="más barato")
    )

    session = whatsapp_handler.conversation_store.get(sender)
    assert session.state == ConversationState.WAITING_DISTANCE
    assert session.fuel_type == "premium"
    assert session.sort == "price"
    assert sent_messages[0]["button_text"] == "Elegir distancia"

    whatsapp_handler.conversation_store.clear()


class FakeOpenAIResponse:
    def __init__(self, response_data):
        self.response_data = response_data

    def raise_for_status(self):
        return None

    def json(self):
        return self.response_data


def openai_response_for(data):
    return {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(data),
                    }
                ],
            }
        ]
    }


def test_openai_interpreter_uses_structured_outputs_without_storage():
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeOpenAIResponse(
            openai_response_for(
                {
                    "intent": "search_gas",
                    "fuel_type": "premium",
                    "sort": "best",
                    "max_distance_miles": 4.5,
                    "language": "es",
                    "confidence": 0.91,
                }
            )
        )

    interpreter = OpenAIIntentInterpreter(
        api_key="test-key",
        model="test-model",
        http_post=fake_post,
    )

    result = interpreter.interpret(
        "Quiero una opción premium que realmente me convenga"
    )

    assert result == MessageInterpretation(
        intent=IntentType.SEARCH_GAS,
        fuel_type="premium",
        sort="best",
        max_distance_miles=4.5,
        language="es",
        confidence=0.91,
        source="openai",
    )
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["store"] is False
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["text"]["format"]["strict"] is True


def test_openai_interpreter_converts_timeout_to_domain_error():
    def timeout_post(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    interpreter = OpenAIIntentInterpreter(
        api_key="test-key",
        model="test-model",
        http_post=timeout_post,
    )

    with pytest.raises(AIInterpretationError, match="timed out"):
        interpreter.interpret("find a station")


def test_openai_interpreter_rejects_invalid_structured_result():
    def fake_post(*args, **kwargs):
        return FakeOpenAIResponse(
            openai_response_for(
                {
                    "intent": "search_gas",
                    "fuel_type": "jet_fuel",
                    "sort": "price",
                    "max_distance_miles": None,
                    "language": "en",
                    "confidence": 0.9,
                }
            )
        )

    interpreter = OpenAIIntentInterpreter(
        api_key="test-key",
        model="test-model",
        http_post=fake_post,
    )

    with pytest.raises(AIInterpretationError, match="fuel type"):
        interpreter.interpret("I need jet fuel")


class RecordingInterpreter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.messages = []

    def interpret(self, text):
        self.messages.append(text)
        if self.error is not None:
            raise self.error
        return self.result


def test_hybrid_interpreter_does_not_call_ai_for_clear_rule_result():
    fallback = RecordingInterpreter(
        result=MessageInterpretation(intent=IntentType.UNKNOWN)
    )
    interpreter = HybridIntentInterpreter(
        rules=RuleBasedIntentInterpreter(),
        fallback=fallback,
    )

    result = interpreter.interpret("premium closest")

    assert result.fuel_type == "premium"
    assert result.sort == "distance"
    assert result.source == "rules"
    assert fallback.messages == []


def test_hybrid_interpreter_calls_ai_for_ambiguous_message():
    fallback_result = MessageInterpretation(
        intent=IntentType.SEARCH_GAS,
        fuel_type="regular",
        sort="best",
        language="en",
        confidence=0.88,
        source="openai",
    )
    fallback = RecordingInterpreter(result=fallback_result)
    interpreter = HybridIntentInterpreter(
        rules=RuleBasedIntentInterpreter(),
        fallback=fallback,
    )

    result = interpreter.interpret("Show me the option that makes most sense")

    assert result == fallback_result
    assert fallback.messages == ["Show me the option that makes most sense"]


def test_hybrid_interpreter_keeps_rule_result_when_ai_fails():
    fallback = RecordingInterpreter(
        error=AIInterpretationError("service unavailable")
    )
    interpreter = HybridIntentInterpreter(
        rules=RuleBasedIntentInterpreter(),
        fallback=fallback,
    )

    result = interpreter.interpret("Necesito gasolina")

    assert result.intent == IntentType.SEARCH_GAS
    assert result.source == "rules"


def test_hybrid_does_not_replace_known_search_with_ai_unknown():
    fallback = RecordingInterpreter(
        result=MessageInterpretation(
            intent=IntentType.UNKNOWN,
            confidence=0.9,
            source="openai",
        )
    )
    interpreter = HybridIntentInterpreter(
        rules=RuleBasedIntentInterpreter(),
        fallback=fallback,
    )

    result = interpreter.interpret("Necesito gasolina")

    assert result.intent == IntentType.SEARCH_GAS
    assert result.language == "es"
    assert result.source == "rules"


def test_factory_keeps_ai_disabled_without_explicit_flag(monkeypatch):
    monkeypatch.setattr(config, "AI_INTENT_ENABLED", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")

    interpreter = build_intent_interpreter()

    assert isinstance(interpreter, RuleBasedIntentInterpreter)


def test_factory_builds_hybrid_when_ai_is_configured(monkeypatch):
    monkeypatch.setattr(config, "AI_INTENT_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(config, "OPENAI_MODEL", "test-model")

    interpreter = build_intent_interpreter()

    assert isinstance(interpreter, HybridIntentInterpreter)
    assert isinstance(interpreter.fallback, OpenAIIntentInterpreter)
    assert interpreter.fallback.model == "test-model"
