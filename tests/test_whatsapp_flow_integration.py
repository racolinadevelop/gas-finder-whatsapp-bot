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
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert bot.sent[0][1]["button_text"] == "Abrir menú"
    bot.sent.clear()

    bot.button("home_search", kind="list_reply")
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
    assert reset.state == ConversationState.MAIN_MENU
    assert reset.profile_name == "Alex"
    bot.assert_sent("list")
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert bot.users and all(sender == SENDER for sender in bot.users)


def test_english_custom_distance_stale_buttons_and_provider_error(bot):
    bot.text("hello")
    bot.button("lang_en")
    bot.button("home_search", kind="list_reply")
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
    bot.assert_sent("buttons", "text", "buttons")
    assert "Premium (test)" in bot.sent[-2][1]["message"]
    assert "Premium (prueba)" in bot.sent[-2][1]["message"]

    bot.sent.clear()
    bot.button("lang_es")
    bot.button("home_search", kind="list_reply")
    bot.button("fuel_regular", kind="list_reply")
    bot.button("sort_price", kind="list_reply")
    bot.button("distance_3", kind="list_reply")
    original = handler.conversation_store.get(SENDER)
    assert original.state == ConversationState.WAITING_LOCATION
    bot.sent.clear()

    bot.text("  MI   PLAN  ")
    bot.assert_sent("text", "list")
    bot.assert_last_list(["home_search", "fav_list", "nav_language", "nav_menu"])
    assert "Premium (prueba de Stripe)" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER) == original
    assert bot.searches == []

    ledger.status = "canceled"
    bot.sent.clear()
    bot.text("mi plan")
    bot.assert_sent("text", "list")
    assert "Tu plan actual: Gratis" in bot.sent[0][1]["message"]
    assert "cancelada" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER) == original

    bot.sent.clear()
    bot.location()
    assert len(bot.searches) == 1
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )


def test_favorites_require_current_premium_and_preserve_free_search(bot, monkeypatch):
    from app.favorites import InMemoryFavoriteStore, SearchReply, shown_stations
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    class VerifiedTestLedger:
        active = True

        def has_premium_access(self, sender):
            assert sender == SENDER
            return self.active

    ledger = VerifiedTestLedger()
    store = InMemoryFavoriteStore()
    monkeypatch.setattr(handler, "favorites_store", store)
    monkeypatch.setattr(
        handler, "subscription_service",
        SubscriptionService(InMemorySubscriptionStore(), test_entitlements=ledger),
    )

    stations = shown_stations([{
        "id": "place-id-123", "name": "Example Station",
        "address": "123 Main St", "latitude": 38.25,
        "longitude": -85.75, "selected_fuel": {"price": 3.40},
    }])
    searches = []
    def one_search(**kwargs):
        searches.append(kwargs)
        return SearchReply("STATION_RESULTS", stations)

    monkeypatch.setattr(handler.location_search_service, "search", one_search)

    bot.text("hola")
    bot.button("lang_es")
    bot.button("home_search", kind="list_reply")
    bot.button("fuel_regular", kind="list_reply")
    bot.button("sort_price", kind="list_reply")
    bot.button("distance_3", kind="list_reply")
    bot.sent.clear()

    bot.location()
    assert len(searches) == 1
    assert searches[0]["capture_results"] is True
    bot.assert_sent("text", "list")
    bot.assert_last_list(["fav_save_1", "fav_list", "nav_back", "nav_menu"])
    original = handler.conversation_store.get(SENDER)

    bot.sent.clear()
    bot.button("fav_save_1", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list(["home_search", "fav_compare", "fav_list", "fav_remove_menu", "nav_menu"])
    assert "Guardada" in bot.sent[0][1]["message"]
    assert "Example Station" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER) == original
    assert len(searches) == 1

    bot.sent.clear()
    bot.text("mis favoritas")
    bot.assert_sent("text", "list")
    assert "123 Main St" in bot.sent[0][1]["message"]
    assert store.list_favorites(SENDER) == stations

    # A canceled payment must block both reads and mutations immediately.
    ledger.active = False
    bot.sent.clear()
    bot.text("mis favoritas")
    bot.assert_sent("text", "list")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert "123 Main St" not in bot.sent[0][1]["message"]

    bot.sent.clear()
    bot.button("fav_save_1", kind="list_reply")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert store.list_favorites(SENDER) == stations

    bot.sent.clear()
    bot.text("eliminar favorita 1")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert store.list_favorites(SENDER) == stations

    # Standard gas-station search remains free, without favorite actions.
    bot.sent.clear()
    bot.button("nav_back", kind="list_reply")
    bot.sent.clear()
    bot.location()
    assert len(searches) == 2
    bot.assert_sent("text", "list")
    bot.assert_last_list(["nav_back", "nav_menu"])

    # If the tested entitlement becomes active again, saved favorites return.
    ledger.active = True
    bot.sent.clear()
    bot.text("mis favoritas")
    assert "Example Station" in bot.sent[0][1]["message"]
    bot.sent.clear()
    bot.text("eliminar favorita 1")
    assert "Eliminada" in bot.sent[0][1]["message"]
    assert store.list_favorites(SENDER) == ()


def test_favorite_remove_is_not_replayed_if_whatsapp_acknowledgement_fails(
    bot, monkeypatch,
):
    from app.favorites import InMemoryFavoriteStore, shown_stations
    from app.services.whatsapp import WhatsAppServiceError
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    store = InMemoryFavoriteStore()
    store.record_results(SENDER, shown_stations([
        {"id": "a", "name": "Station A", "address": "A Street"},
        {"id": "b", "name": "Station B", "address": "B Street"},
    ]))
    store.add_from_recent(SENDER, 1)
    store.add_from_recent(SENDER, 2)
    monkeypatch.setattr(handler, "favorites_store", store)
    subscriptions = SubscriptionService(InMemorySubscriptionStore())
    subscriptions.activate_premium(SENDER)
    monkeypatch.setattr(handler, "subscription_service", subscriptions)
    monkeypatch.setattr(
        handler, "send_text_message",
        lambda **kwargs: (_ for _ in ()).throw(
            WhatsAppServiceError("simulated delivery failure")
        ),
    )
    message = {"type": "text", "text": {"body": "eliminar favorita 1"}}
    bot.post(message, message_id="wamid.favorite-remove-once")
    assert [item.name for item in store.list_favorites(SENDER)] == ["Station B"]
    # Meta retry of the same message must never delete a second item.
    bot.post(message, message_id="wamid.favorite-remove-once")
    assert [item.name for item in store.list_favorites(SENDER)] == ["Station B"]


def test_singular_mi_favorita_is_handled_globally_without_reprompting_fuel(bot, monkeypatch):
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    # The sender has no active Premium entitlement. Both requests must go
    # directly to the feature gate rather than the current conversation state.
    monkeypatch.setattr(
        handler, "subscription_service",
        SubscriptionService(InMemorySubscriptionStore()),
    )
    bot.text("hola")
    bot.sent.clear()

    bot.text("Mi favorita")
    bot.assert_sent("text", "list")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )

    bot.sent.clear()
    bot.button("lang_es")
    bot.sent.clear()
    original = handler.conversation_store.get(SENDER)
    assert original.state == ConversationState.MAIN_MENU

    bot.text("Mi favorita")
    bot.assert_sent("text", "list")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert "Esa opción no corresponde" not in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER) == original
    assert bot.searches == []

    bot.sent.clear()
    bot.button("home_search", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_FUEL
    )
    bot.sent.clear()
    bot.text("Mi favorita")
    bot.assert_sent("text", "list")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_FUEL
    )
    bot.sent.clear()
    bot.button("fuel_regular", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_SORT
    )


def test_language_choice_is_remembered_and_change_language_is_explicit(bot, monkeypatch):
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    monkeypatch.setattr(
        handler, "subscription_service",
        SubscriptionService(InMemorySubscriptionStore()),
    )
    bot.text("hola")
    bot.assert_sent("buttons")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )

    bot.sent.clear()
    bot.button("lang_es")
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU
    assert handler.user_language_store.get(SENDER) == "es"
    bot.assert_sent("list")
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert bot.sent[-1][1]["button_text"] == "Abrir menú"

    # Favorites is now available as a visible action before a gas search;
    # free users receive the Premium gate rather than an invalid-step prompt.
    bot.sent.clear()
    bot.button("fav_list", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list(["home_search", "account_plan", "nav_menu"])
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU
    assert bot.searches == []

    # Simulate a fresh worker or an expired Redis session. No second language
    # prompt is allowed: the durable selection opens the Spanish home menu.
    handler.conversation_store.clear()
    bot.sent.clear()
    bot.text("hola")
    bot.assert_sent("list")
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert bot.sent[-1][1]["button_text"] == "Abrir menú"
    assert handler.conversation_store.get(SENDER).language == "es"

    bot.sent.clear()
    bot.button("nav_language", kind="list_reply")
    bot.assert_sent("buttons")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )
    # The old preference must not be erased until the replacement is selected.
    assert handler.user_language_store.get(SENDER) == "es"
    bot.sent.clear()
    bot.button("lang_en")
    bot.assert_sent("list")
    assert bot.sent[-1][1]["button_text"] == "Open menu"
    assert handler.user_language_store.get(SENDER) == "en"

    bot.sent.clear()
    bot.text("menu")
    bot.assert_sent("list")
    assert bot.sent[-1][1]["button_text"] == "Open menu"
    handler.conversation_store.clear()
    bot.sent.clear()
    bot.text("hello")
    bot.assert_sent("list")
    assert bot.sent[-1][1]["button_text"] == "Open menu"
    assert handler.conversation_store.get(SENDER).language == "en"

    bot.sent.clear()
    bot.button("home_search", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list([
        "fuel_regular", "fuel_premium", "fuel_diesel", "nav_back", "nav_menu",
    ])
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_FUEL
    )

    bot.sent.clear()
    bot.button("nav_back", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert handler.conversation_store.get(SENDER).language == "en"


def test_existing_saved_search_language_is_migrated_on_next_greeting(bot):
    from app.preferences import SearchPreferences

    handler.search_preferences_store.save(SENDER, SearchPreferences(
        language="es", fuel_type="diesel", sort="price", max_distance_miles=3,
    ))
    assert handler.user_language_store.get(SENDER) is None
    bot.text("hola")
    bot.assert_sent("list")
    assert bot.sent[-1][1]["button_text"] == "Abrir menú"
    assert handler.user_language_store.get(SENDER) == "es"
    assert bot.searches == []


def test_active_legacy_chat_language_is_saved_without_repeating_language_screen(bot):
    handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_FUEL, language="es",
    )
    assert handler.user_language_store.get(SENDER) is None
    bot.text("hola")
    bot.assert_sent("list")
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU
    assert handler.user_language_store.get(SENDER) == "es"
    assert bot.searches == []


def test_account_views_have_buttons_and_search_is_one_tap_from_any_state(bot, monkeypatch):
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService
    monkeypatch.setattr(
        handler, "subscription_service",
        SubscriptionService(InMemorySubscriptionStore()),
    )
    bot.text("hola")
    bot.button("lang_es")
    bot.sent.clear()

    bot.button("account_plan", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list(["home_search", "fav_list", "nav_language", "nav_menu"])
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU

    bot.sent.clear()
    bot.button("fav_list", kind="list_reply")
    bot.assert_sent("text", "list")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    bot.assert_last_list(["home_search", "account_plan", "nav_menu"])
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU

    bot.sent.clear()
    bot.button("home_search", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list(["fuel_regular", "fuel_premium", "fuel_diesel",
                          "nav_back", "nav_menu"])
    session = handler.conversation_store.get(SENDER)
    assert session.state == ConversationState.WAITING_FUEL
    assert bot.searches == []

    bot.sent.clear()
    bot.button("account_plan", kind="list_reply")
    bot.assert_sent("text", "list")
    assert handler.conversation_store.get(SENDER) == session

    bot.sent.clear()
    bot.button("nav_menu", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list(["home_search", "fav_list", "account_plan", "nav_language"])
    assert handler.conversation_store.get(SENDER).language == "es"


def test_favorites_empty_saved_and_remove_menu_use_one_tap_choices(bot, monkeypatch):
    from app.favorites import InMemoryFavoriteStore, shown_stations
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    store = InMemoryFavoriteStore()
    monkeypatch.setattr(handler, "favorites_store", store)
    subscription = SubscriptionService(InMemorySubscriptionStore())
    subscription.activate_premium(SENDER)
    monkeypatch.setattr(handler, "subscription_service", subscription)

    bot.text("hola")
    bot.button("lang_es")
    bot.sent.clear()
    bot.button("fav_list", kind="list_reply")
    bot.assert_sent("text", "list")
    assert "Aún no tienes favoritas" in bot.sent[0][1]["message"]
    bot.assert_last_list(["home_search", "nav_menu"])

    # Save a station from the existing displayed results; no provider calls.
    items = shown_stations([{
        "id": "example-place", "name": "Station Example",
        "address": "100 Main St",
    }])
    store.record_results(SENDER, items)
    bot.sent.clear()
    bot.button("fav_save_1", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list(["home_search", "fav_compare", "fav_list", "fav_remove_menu", "nav_menu"])
    assert len(bot.searches) == 0

    bot.sent.clear()
    bot.button("fav_list", kind="list_reply")
    bot.assert_sent("text", "list")
    assert "Station Example" in bot.sent[0][1]["message"]
    bot.assert_last_list(["home_search", "fav_compare", "fav_remove_menu", "nav_menu"])

    bot.sent.clear()
    bot.button("fav_remove_menu", kind="list_reply")
    bot.assert_sent("list")
    button_ids = [row["id"] for row in bot.sent[-1][1]["rows"]]
    assert len(button_ids) == 3
    assert button_ids[-2:] == ["fav_remove_back", "nav_menu"]
    selected = button_ids[0]
    assert selected.startswith("fav_delete_")
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU

    bot.sent.clear()
    bot.button("fav_remove_back", kind="list_reply")
    bot.assert_sent("text", "list")
    assert store.list_favorites(SENDER) == items

    bot.sent.clear()
    bot.button("fav_remove_menu", kind="list_reply")
    bot.button(selected, kind="list_reply")
    assert "Eliminada" in bot.sent[-2][1]["message"]
    assert store.list_favorites(SENDER) == ()
    bot.assert_last_list(["home_search", "nav_menu"])

    # A stale button refers to the old station and cannot remove another one.
    store.record_results(SENDER, shown_stations([{
        "id": "other-place", "name": "Other Station", "address": "200 Main St",
    }]))
    store.add_from_recent(SENDER, 1)
    bot.sent.clear()
    bot.button(selected, kind="list_reply")
    assert store.list_favorites(SENDER)[0].name == "Other Station"
    assert "ya no está disponible" in bot.sent[0][1]["message"]


def test_favorite_removal_pagination_and_revoked_access(bot, monkeypatch):
    from app.favorites import InMemoryFavoriteStore, shown_stations
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    class Ledger:
        active = True

        def has_premium_access(self, sender):
            assert sender == SENDER
            return self.active

    ledger = Ledger()
    store = InMemoryFavoriteStore()
    monkeypatch.setattr(handler, "favorites_store", store)
    monkeypatch.setattr(
        handler, "subscription_service",
        SubscriptionService(InMemorySubscriptionStore(), test_entitlements=ledger),
    )
    for index in range(10):
        store.record_results(SENDER, shown_stations([{
            "id": f"place-{index}", "name": f"Station {index}",
            "address": f"{index} Main Street",
        }]))
        store.add_from_recent(SENDER, 1)

    bot.text("hola")
    bot.button("lang_en")
    bot.sent.clear()
    bot.button("fav_remove_menu", kind="list_reply")
    bot.assert_sent("list")
    first_page = [row["id"] for row in bot.sent[-1][1]["rows"]]
    assert len(first_page) == 8
    assert first_page[-3:] == ["fav_remove_page_2", "fav_remove_back", "nav_menu"]

    bot.sent.clear()
    bot.button("fav_remove_page_2", kind="list_reply")
    bot.assert_sent("list")
    second_page = [row["id"] for row in bot.sent[-1][1]["rows"]]
    assert len(second_page) == 8
    assert second_page[-3:] == ["fav_remove_page_1", "fav_remove_back", "nav_menu"]
    chosen = second_page[0]

    ledger.active = False
    bot.sent.clear()
    bot.button(chosen, kind="list_reply")
    bot.assert_sent("text", "list")
    assert "requires Premium" in bot.sent[0][1]["message"]
    assert len(store.list_favorites(SENDER)) == 10

    ledger.active = True
    bot.sent.clear()
    bot.button(chosen, kind="list_reply")
    bot.assert_sent("text", "list")
    assert "Removed: Station 5" in bot.sent[0][1]["message"]
    assert len(store.list_favorites(SENDER)) == 9


def test_premium_favorites_comparison_is_guided_and_only_uses_selected_saved_stations(
    bot, monkeypatch,
):
    from app.favorites import InMemoryFavoriteStore, shown_stations
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    store = InMemoryFavoriteStore()
    for i in range(7):
        store.record_results(SENDER, shown_stations([{
            "id": f"googlePlace{i}", "name": f"Station {i}",
            "address": f"{i} Main Street",
        }]))
        store.add_from_recent(SENDER, 1)
    monkeypatch.setattr(handler, "favorites_store", store)
    paid = SubscriptionService(InMemorySubscriptionStore())
    paid.activate_premium(SENDER)
    monkeypatch.setattr(handler, "subscription_service", paid)
    monkeypatch.setattr(handler, "GAS_STATION_PROVIDER", "google")
    calls = []

    def fake_comparison(favorites, *, latitude, longitude, fuel_type):
        calls.append((favorites, latitude, longitude, fuel_type))
        return {
            "fuel_type": fuel_type,
            "stations": [{
                "name": station.name, "address": station.address,
                "open_now": None, "details_available": False,
                "selected_fuel": {
                    "price": None, "updated_at": None, "currency": None,
                },
            } for station in favorites],
        }

    monkeypatch.setattr(handler, "compare_saved_places", fake_comparison)

    bot.text("hola")
    bot.button("lang_es")
    bot.sent.clear()
    bot.button("fav_list", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list([
        "home_search", "fav_compare", "fav_remove_menu", "nav_menu",
    ])
    bot.sent.clear()

    bot.button("fav_compare", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list([
        "fav_compare_page_1", "fav_compare_page_2", "fav_list", "nav_menu",
    ])
    assert calls == [] and bot.searches == []
    bot.sent.clear()

    bot.button("fav_compare_page_2", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list([
        "fav_fuel_regular", "fav_fuel_premium", "fav_fuel_diesel",
        "nav_back", "nav_menu",
    ])
    session = handler.conversation_store.get(SENDER)
    assert session.state == ConversationState.WAITING_FAVORITES_FUEL
    assert session.favorite_page == 2
    bot.sent.clear()

    bot.location()
    assert calls == [] and bot.searches == []
    bot.assert_sent("list")  # Must select fuel before location is valid.
    bot.sent.clear()

    bot.button("fav_fuel_diesel", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_FAVORITES_LOCATION
    )
    bot.assert_sent("text", "list")
    bot.assert_last_list(["nav_back", "nav_menu"])
    bot.sent.clear()

    bot.location()
    bot.assert_sent("text", "list")
    assert len(calls) == 1
    compared, lat, lng, fuel = calls[0]
    assert [s.name for s in compared] == ["Station 5", "Station 6"]
    assert (lat, lng, fuel) == (38.25, -85.75, "diesel")
    assert "Station 5" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU
    bot.assert_last_list(["fav_compare", "fav_list", "home_search", "nav_menu"])
    assert bot.searches == []
    bot.sent.clear()

    bot.button("home_search", kind="list_reply")
    bot.assert_sent("list")
    bot.assert_last_list([
        "fuel_regular", "fuel_premium", "fuel_diesel", "nav_back", "nav_menu",
    ])
    assert handler.conversation_store.get(SENDER).state == ConversationState.WAITING_FUEL


def test_cancelled_premium_blocks_comparison_even_after_location_prompt(bot, monkeypatch):
    from app.favorites import InMemoryFavoriteStore, shown_stations
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    class Ledger:
        active = True
        def has_premium_access(self, sender):
            assert sender == SENDER
            return self.active

    ledger = Ledger()
    store = InMemoryFavoriteStore()
    store.record_results(SENDER, shown_stations([{
        "id": "googlePlace1", "name": "Saved Station", "address": "Main St",
    }]))
    store.add_from_recent(SENDER, 1)
    monkeypatch.setattr(handler, "favorites_store", store)
    monkeypatch.setattr(
        handler, "subscription_service",
        SubscriptionService(InMemorySubscriptionStore(), test_entitlements=ledger),
    )
    monkeypatch.setattr(handler, "GAS_STATION_PROVIDER", "google")
    calls = []
    monkeypatch.setattr(
        handler, "compare_saved_places",
        lambda *args, **kwargs: calls.append(args) or {"stations": []},
    )

    bot.text("hola")
    bot.button("lang_es")
    bot.button("fav_compare", kind="list_reply")
    bot.button("fav_fuel_regular", kind="list_reply")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_FAVORITES_LOCATION
    )
    ledger.active = False
    bot.sent.clear()
    bot.location()
    bot.assert_sent("text", "list")
    assert "requiere Premium" in bot.sent[0][1]["message"]
    assert calls == [] and bot.searches == []
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU


def test_compare_favorites_rate_limit_and_back_keep_normal_search_free(bot, monkeypatch):
    from app.favorites import InMemoryFavoriteStore, shown_stations
    from app.subscriptions import InMemorySubscriptionStore, SubscriptionService

    store = InMemoryFavoriteStore()
    store.record_results(SENDER, shown_stations([{
        "id": "googlePlace1", "name": "Saved Station", "address": "Main St",
    }]))
    store.add_from_recent(SENDER, 1)
    monkeypatch.setattr(handler, "favorites_store", store)
    paid = SubscriptionService(InMemorySubscriptionStore())
    paid.activate_premium(SENDER)
    monkeypatch.setattr(handler, "subscription_service", paid)
    monkeypatch.setattr(handler, "GAS_STATION_PROVIDER", "google")
    monkeypatch.setattr(handler.search_rate_limiter, "allow", lambda _sender: False)
    monkeypatch.setattr(
        handler, "compare_saved_places",
        lambda *a, **kw: pytest.fail("rate-limited comparison must not fetch"),
    )

    bot.text("hola")
    bot.button("lang_en")
    bot.button("fav_compare", kind="list_reply")
    bot.sent.clear()
    bot.button("nav_back", kind="list_reply")
    bot.assert_sent("text", "list")  # Back from fuel returns to saved favorites.
    assert handler.conversation_store.get(SENDER).state == ConversationState.MAIN_MENU
    bot.sent.clear()

    bot.button("fav_compare", kind="list_reply")
    bot.button("fav_fuel_premium", kind="list_reply")
    bot.sent.clear()
    bot.location()
    assert "Wait a few minutes" in bot.sent[0][1]["message"]
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_FAVORITES_LOCATION
    )
    assert bot.searches == []


def test_whatsapp_test_checkout_and_portal_buttons_are_user_bound_and_keep_search_state(
    bot, monkeypatch,
):
    from types import SimpleNamespace

    class Ledger:
        record = None
        def get_test_subscription(self, sender):
            assert sender == SENDER
            return self.record

    ledger = Ledger()
    monkeypatch.setattr(handler, "test_billing_store", ledger)
    monkeypatch.setattr(handler, "links_enabled", lambda: True)
    monkeypatch.setattr(
        handler.subscription_service, "get_subscription",
        lambda sender: SimpleNamespace(has_premium_access=False),
    )
    requested, managed = [], []
    test_url = "https://checkout.stripe.com/c/pay/cs_test_user_link"
    portal_url = "https://billing.stripe.com/p/session/test"
    monkeypatch.setattr(
        handler, "create_sender_checkout",
        lambda sender, *, store, subscription_service: (
            requested.append((sender, store, subscription_service)) or test_url
        ),
    )
    monkeypatch.setattr(
        handler, "create_sender_portal",
        lambda sender, *, store: managed.append((sender, store)) or portal_url,
    )

    bot.text("hola")
    bot.button("lang_es")
    bot.button("home_search", kind="list_reply")
    original = handler.conversation_store.get(SENDER)
    assert original.state == ConversationState.WAITING_FUEL
    bot.sent.clear()

    bot.button("account_plan", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list([
        "home_search", "fav_list", "account_test_checkout",
        "nav_language", "nav_menu",
    ])
    assert handler.conversation_store.get(SENDER) == original
    bot.sent.clear()

    bot.button("account_test_checkout", kind="list_reply")
    bot.assert_sent("text")
    assert test_url in bot.sent[0][1]["message"]
    assert "Stripe TEST" in bot.sent[0][1]["message"]
    assert "no se cobra dinero real" in bot.sent[0][1]["message"]
    assert requested == [(SENDER, ledger, handler.subscription_service)]
    assert handler.conversation_store.get(SENDER) == original
    assert bot.searches == []
    bot.sent.clear()

    # Only the verified billing webhook changes the entitlement ledger.
    # The test mode active status must show Manage, never buy a second plan.
    ledger.record = {
        "status": "active", "customer_id": "cus_sandbox",
        "subscription_id": "sub_sandbox",
    }
    bot.button("account_plan", kind="list_reply")
    bot.assert_sent("text", "list")
    bot.assert_last_list([
        "home_search", "fav_list", "account_test_portal",
        "nav_language", "nav_menu",
    ])
    bot.sent.clear()
    bot.button("account_test_portal", kind="list_reply")
    bot.assert_sent("text")
    assert portal_url in bot.sent[0][1]["message"]
    assert managed == [(SENDER, ledger)]
    assert handler.conversation_store.get(SENDER) == original
    bot.sent.clear()

    ledger.record["status"] = "canceled"
    bot.button("account_plan", kind="list_reply")
    bot.assert_last_list([
        "home_search", "fav_list", "account_test_checkout",
        "nav_language", "nav_menu",
    ])


def test_whatsapp_billing_links_are_not_offered_when_disabled_or_before_language(
    bot, monkeypatch,
):
    from types import SimpleNamespace

    class Ledger:
        def get_test_subscription(self, sender):
            return None

    monkeypatch.setattr(handler, "test_billing_store", Ledger())
    monkeypatch.setattr(
        handler.subscription_service, "get_subscription",
        lambda sender: SimpleNamespace(has_premium_access=False),
    )
    monkeypatch.setattr(handler, "links_enabled", lambda: False)
    bot.text("hola")
    bot.sent.clear()
    bot.button("account_plan", kind="button_reply")
    bot.assert_sent("text", "buttons")
    bot.assert_last_buttons(["lang_en", "lang_es", "account_plan"])
    bot.sent.clear()
    bot.button("account_test_checkout", kind="list_reply")
    bot.assert_sent("buttons")
    assert handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )
    bot.sent.clear()
    bot.button("lang_en")
    bot.button("account_plan", kind="list_reply")
    bot.assert_last_list(["home_search", "fav_list", "nav_language", "nav_menu"])
    bot.sent.clear()
    bot.button("account_test_checkout", kind="list_reply")
    assert "isn't available yet" in bot.sent[0][1]["message"]
    assert "checkout.stripe.com" not in repr(bot.sent)
