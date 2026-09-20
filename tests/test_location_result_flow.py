"""Location search delivery contract, independent of WhatsApp transports."""

from app.conversation import ConversationSession, ConversationState
from app.handlers.location_results import run_location_search
from app.models import IncomingMessage
from app.providers import GasStationProviderError
from app.services.whatsapp import WhatsAppServiceError


SENDER = "15551234567"


def message(*, latitude=38.25, longitude=-85.75):
    return IncomingMessage(
        sender=SENDER, message_type="location",
        latitude=latitude, longitude=longitude,
    )


def session():
    return ConversationSession(
        sender=SENDER, state=ConversationState.WAITING_LOCATION,
        language="es", fuel_type="diesel", sort="price",
        max_distance_miles=3,
    )


def test_success_sends_results_then_updates_state_then_navigation():
    events = []
    original = session()

    def search(**kwargs):
        assert kwargs == {
            "session": original, "latitude": 38.25, "longitude": -85.75,
        }
        events.append("search")
        return "Resultados"

    def send_text(**kwargs):
        assert kwargs == {"to": SENDER, "message": "Resultados"}
        events.append("results")

    def update(sender, changes):
        assert sender == SENDER
        assert changes == {"state": ConversationState.WAITING_RESULTS}
        events.append("state")

    def send_prompt(sender, prompt):
        assert sender == SENDER
        assert [button["id"] for button in prompt.buttons] == [
            "nav_back", "nav_menu",
        ]
        events.append("navigation")

    run_location_search(
        message(), original,
        allow_search=lambda sender: events.append("rate_limit") or True,
        search=search,
        send_text=send_text,
        update_session=update,
        send_prompt=send_prompt,
    )
    assert events == [
        "rate_limit", "search", "results", "state", "navigation",
    ]
    assert original.state == ConversationState.WAITING_LOCATION
    assert original.fuel_type == "diesel"
    assert original.max_distance_miles == 3


def test_rate_limit_prevents_search_and_keeps_state():
    sent = []
    original = session()

    run_location_search(
        message(), original,
        allow_search=lambda sender: False,
        search=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("must not search")
        ),
        send_text=lambda **kwargs: sent.append(kwargs),
        update_session=lambda *args: (_ for _ in ()).throw(
            AssertionError("must not update state")
        ),
        send_prompt=lambda *args: (_ for _ in ()).throw(
            AssertionError("must not send navigation")
        ),
    )

    assert len(sent) == 1
    assert sent[0]["to"] == SENDER
    assert "demasiadas búsquedas" in sent[0]["message"].lower()
    assert original.state == ConversationState.WAITING_LOCATION


def test_provider_error_shows_retry_without_advancing():
    sent = []

    def failing_search(**kwargs):
        raise GasStationProviderError("failed")

    run_location_search(
        message(), session(),
        allow_search=lambda sender: True,
        search=failing_search,
        send_text=lambda **kwargs: sent.append(kwargs),
        update_session=lambda *args: (_ for _ in ()).throw(
            AssertionError("must not advance")
        ),
        send_prompt=lambda *args: (_ for _ in ()).throw(
            AssertionError("must not send navigation")
        ),
    )

    assert len(sent) == 1
    assert "preferencias siguen guardadas" in sent[0]["message"]


def test_results_delivery_error_preserves_location_state():
    original = session()

    def failing_send(**kwargs):
        raise WhatsAppServiceError("WhatsApp temporarily unavailable")

    run_location_search(
        message(), original,
        allow_search=lambda sender: True,
        search=lambda **kwargs: "Resultados",
        send_text=failing_send,
        update_session=lambda *args: (_ for _ in ()).throw(
            AssertionError("must not advance")
        ),
        send_prompt=lambda *args: (_ for _ in ()).throw(
            AssertionError("must not send navigation")
        ),
    )
    assert original.state == ConversationState.WAITING_LOCATION
