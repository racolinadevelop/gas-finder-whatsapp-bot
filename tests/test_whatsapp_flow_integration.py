"""Exercise the real FastAPI webhook, parser, routers and conversation flow.

Only external WhatsApp delivery, station lookup and subscription persistence
are replaced. Tests never send real messages, call providers, or need secrets.
"""

from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.conversation import ConversationState
from app.handlers import whatsapp as handler
from app.main import app
from app.providers import GasStationProviderError
from app.routers import whatsapp as whatsapp_api


SENDER = "15551234567"
WEBHOOK_PATH = "/api/v1/whatsapp/webhook"


class WhatsAppHarness:
    def __init__(self):
        self.client = TestClient(app)
        self.sent = []
        self.searches = []
        self.users = []
        self.message_numbers = count(1)
        self.search_error = False

    def search(self, **kwargs):
        self.searches.append(kwargs)
        if self.search_error:
            raise GasStationProviderError("simulated outage")
        return "STATION_RESULTS"

    def post(self, message, *, message_id=None):
        event = {
            "from": SENDER,
            "id": message_id or f"wamid.flow.{next(self.message_numbers)}",
            **message,
        }
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Alex"}}],
                        "messages": [event],
                    },
                }],
            }],
        }
        response = self.client.post(WEBHOOK_PATH, json=payload)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        return payload

    def text(self, body):
        return self.post({"type": "text", "text": {"body": body}})

    def button(self, selection_id, *, kind="button_reply"):
        return self.post({
            "type": "interactive",
            "interactive": {
                "type": kind,
                kind: {"id": selection_id, "title": selection_id},
            },
        })

    def location(self, *, message_id=None):
        return self.post(
            {
                "type": "location",
                "location": {"latitude": 38.25, "longitude": -85.75},
            },
            message_id=message_id,
        )

    def assert_sent(self, *kinds):
        assert [kind for kind, _ in self.sent] == list(kinds)

    def assert_last_buttons(self, expected):
        kind, payload = self.sent[-1]
        assert kind == "buttons"
        assert [item["id"] for item in payload["buttons"]] == expected

    def assert_last_list(self, expected):
        kind, payload = self.sent[-1]
        assert kind == "list"
        assert [item["id"] for item in payload["rows"]] == expected


@pytest.fixture
def bot(monkeypatch):
    # Isolate HTTP request processing from Meta credentials, external APIs
    # and paid storage; keep the actual parser, routers and state transitions.
    monkeypatch.setattr(whatsapp_api, "META_APP_SECRET", None)
    handler.conversation_store.clear()
    bot = WhatsAppHarness()
    monkeypatch.setattr(
        handler, "send_reply_buttons",
        lambda **kwargs: bot.sent.append(("buttons", kwargs)),
    )
    monkeypatch.setattr(
        handler, "send_list_message",
        lambda **kwargs: bot.sent.append(("list", kwargs)),
    )
    monkeypatch.setattr(
        handler, "send_text_message",
        lambda **kwargs: bot.sent.append(("text", kwargs)),
    )
    monkeypatch.setattr(handler.location_search_service, "search", bot.search)
    monkeypatch.setattr(
        handler.subscription_service,
        "ensure_user",
        lambda sender: bot.users.append(sender),
    )
    yield bot
    handler.conversation_store.clear()


def test_spanish_flow_from_real_webhook_through_results_and_menu(bot):
    bot.text("hola")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )
    bot.assert_sent("buttons")
    bot.assert_last_buttons(["lang_en", "lang_es", "account_plan"])
    bot.sent.clear()

    bot.button("lang_es")
    bot.assert_sent("list")
    bot.assert_last_list(["fuel_regular", "fuel_premium", "fuel_diesel",
                          "nav_back", "nav_menu"])
    assert bot.sent[0][1]["button_text"] == "Elegir combustible"
    bot.sent.clear()

    bot.button("fuel_premium", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list(["sort_distance", "sort_price", "sort_best",
                          "nav_back", "nav_menu"])
    assert bot.sent[0][1]["button_text"] == "Elegir categoría"
    bot.sent.clear()

    bot.button("sort_price", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list(["distance_1", "distance_3", "distance_5",
                          "distance_10", "distance_custom",
                          "nav_back", "nav_menu"])
    bot.sent.clear()

    bot.button("distance_3", kind="list_reply")
    session = handler.conversation_store.get(SENDER)
    assert session.state == ConversationState.WAITING_LOCATION
    assert (session.language, session.fuel_type, session.sort) == (
        "es", "premium", "price",
    )
    assert session.max_distance_miles == 3
    bot.assert_sent("text", "list")
    bot.assert_last_list(["nav_back", "nav_menu"])
    bot.sent.clear()

    # Unrelated text must not replace the selected fuel, sort or radius.
    bot.text("unrelated")
    assert handler.conversation_store.get(SENDER) == session
    assert bot.searches == []
    bot.assert_sent("text", "list")
    bot.sent.clear()

    bot.location(message_id="wamid.integration.first-location")
    assert len(bot.searches) == 1
    assert bot.searches[0] == {
        "session": session, "latitude": 38.25, "longitude": -85.75,
        "capture_results": True,
    }
    bot.assert_sent("text", "list")
    assert bot.sent[0][1]["message"] == "STATION_RESULTS"
    bot.assert_last_list(["nav_back", "nav_menu"])
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )
    bot.sent.clear()

    # Meta may retry the identical webhook: never search or send twice.
    bot.location(message_id="wamid.integration.first-location")
    assert len(bot.searches) == 1
    assert bot.sent == []

    bot.button("nav_back", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LOCATION
    )
    bot.assert_sent("text", "list")
    bot.sent.clear()

    bot.location(message_id="wamid.integration.second-location")
    assert len(bot.searches) == 2
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )
    bot.sent.clear()

    bot.button("nav_menu", kind="list_reply")
    reset = handler.conversation_store.get(SENDER)
    assert reset.state == ConversationState.WAITING_LANGUAGE
    assert reset.profile_name == "Alex"
    assert reset.max_distance_miles is None
    bot.assert_sent("buttons")
    bot.assert_last_buttons(["lang_en", "lang_es", "account_plan"])
    assert bot.users and all(sender == SENDER for sender in bot.users)


def test_english_custom_distance_stale_buttons_and_provider_error(bot):
    bot.text("hello")
    bot.button("lang_en")
    bot.button("fuel_regular", kind="list_reply")
    bot.button("sort_best", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_DISTANCE
    )
    bot.sent.clear()

    # A location sent too soon cannot skip the distance choice.
    bot.location()
    assert bot.searches == []
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_DISTANCE
    )
    bot.assert_sent("list")
    bot.sent.clear()

    bot.button("distance_custom", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_CUSTOM_DISTANCE
    )
    bot.assert_sent("text", "list")
    bot.sent.clear()

    bot.text("invalid distance")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_CUSTOM_DISTANCE
    )
    bot.assert_sent("text", "list")
    bot.sent.clear()

    bot.text("2.5")
    original = handler.conversation_store.get(SENDER)
    assert original.state == ConversationState.WAITING_LOCATION
    assert original.max_distance_miles == 2.5
    bot.assert_sent("text", "list")
    bot.sent.clear()

    # Old buttons cannot change the language or skip a pending location.
    bot.button("lang_es")
    assert handler.conversation_store.get(SENDER) == original
    bot.assert_sent("text", "list")
    bot.sent.clear()

    bot.search_error = True
    bot.location()
    assert len(bot.searches) == 1
    assert handler.conversation_store.get(SENDER) == original
    bot.assert_sent("text")
    assert "preferences are still saved" in bot.sent[0][1]["message"]
    bot.sent.clear()

    bot.search_error = False
    bot.location()
    assert len(bot.searches) == 2
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )
    bot.assert_sent("text", "list")
    bot.assert_last_list(["nav_back", "nav_menu"])
    bot.sent.clear()

    # An unsupported message at results must not start a second search.
    bot.post({"type": "image", "image": {"id": "media.example"}})
    assert len(bot.searches) == 2
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )
    bot.assert_sent("list")
    bot.assert_last_list(["nav_back", "nav_menu"])


def test_status_only_webhook_has_no_conversation_side_effects(bot):
    response = bot.client.post(
        WEBHOOK_PATH,
        json={
            "entry": [{
                "changes": [{
                    "value": {"statuses": [{"id": "wamid.delivery-status"}]},
                }],
            }],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert handler.conversation_store.get(SENDER) is None
    assert bot.users == []
    assert bot.sent == []
    assert bot.searches == []



def test_my_plan_shows_real_sandbox_access_without_resetting_search(bot, monkeypatch):
    from app.subscriptions.models import UserSubscription

    class SandboxLedger:
        status = "active"

        def get_test_subscription(self, sender):
            assert sender == SENDER
            return {"status": self.status}

    ledger = SandboxLedger()
    monkeypatch.setattr(handler, "test_billing_store", ledger)
    monkeypatch.setattr(
        handler.subscription_service,
        "get_subscription",
        lambda sender: UserSubscription(whatsapp_id=sender),
    )

    bot.text("hola")
    bot.button("account_plan")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )
    bot.assert_sent("buttons", "text")
    assert "Premium (Stripe test)" in bot.sent[-1][1]["message"]
    assert "Premium (prueba de Stripe)" in bot.sent[-1][1]["message"]

    bot.sent.clear()
    bot.button("lang_es")
    bot.button("fuel_regular", kind="list_reply")
    bot.button("sort_price", kind="list_reply")
    bot.button("distance_3", kind="list_reply")
    original = handler.conversation_store.get(SENDER)
    assert original.state == ConversationState.WAITING_LOCATION
    bot.sent.clear()

    bot.text("  MI   PLAN  ")
    bot.assert_sent("text")
    assert "Premium (prueba de Stripe)" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER) == original
    assert bot.searches == []

    ledger.status = "canceled"
    bot.sent.clear()
    bot.text("mi plan")
    bot.assert_sent("text")
    assert "Tu plan actual: Gratis" in bot.sent[0][1]["message"]
    assert "cancelada" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER) == original

    bot.sent.clear()
    bot.location()
    assert len(bot.searches) == 1
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )
