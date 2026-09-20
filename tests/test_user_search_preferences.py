"""User preferences survive a session expiry without modifying an active flow."""

from hashlib import sha256

import pytest

from app.conversation import ConversationSession, ConversationState
from app.handlers import whatsapp as handler
from app.handlers.location_messages import process_location_message
from app.handlers.location_results import run_location_search
from app.models import IncomingMessage
from app.preferences import (
    InMemorySearchPreferencesStore,
    PostgresSearchPreferencesStore,
    SearchPreferences,
)
from app.runtime import build_runtime_state
from app.services.whatsapp import WhatsAppServiceError


SENDER = "15551234567"


def settings():
    return SearchPreferences(
        language="es", fuel_type="diesel", sort="price",
        max_distance_miles=3.0,
    )


def location():
    return IncomingMessage(
        sender=SENDER, message_type="location",
        latitude=38.25, longitude=-85.75,
    )


class FakeDatabase:
    def __init__(self):
        self.rows = {}
        self.schema_created = False

    def connect(self, _url):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor(self.db)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("create table"):
            self.db.schema_created = True
        elif normalized.startswith("select"):
            self.row = self.db.rows.get(params[0])
        elif normalized.startswith("insert"):
            self.db.rows[params[0]] = params[1:]
        else:
            raise AssertionError("Unexpected SQL statement")

    def fetchone(self):
        return self.row


def test_postgres_pref_store_survives_recreation_without_raw_identifiers():
    db = FakeDatabase()
    first = PostgresSearchPreferencesStore(
        "postgresql://example", connect_fn=db.connect,
    )
    first.save(SENDER, settings())
    second = PostgresSearchPreferencesStore(
        "postgresql://example", connect_fn=db.connect,
    )
    assert db.schema_created
    assert second.get(SENDER) == settings()
    assert second.get("another-sender") is None
    assert list(db.rows) == [sha256(SENDER.encode()).hexdigest()]
    assert SENDER not in repr(db.rows)


def test_runtime_configures_independent_preferences_store():
    memory = build_runtime_state(redis_url=None, database_url=None)
    assert isinstance(memory.search_preferences_store, InMemorySearchPreferencesStore)
    db = FakeDatabase()
    persistent = build_runtime_state(
        redis_url=None, database_url="postgresql://example",
        postgres_connect_fn=db.connect,
    )
    assert isinstance(
        persistent.search_preferences_store, PostgresSearchPreferencesStore
    )
    persistent.search_preferences_store.save(SENDER, settings())
    assert persistent.search_preferences_store.get(SENDER) == settings()


@pytest.mark.parametrize("field,bad_value", [
    ("language", "fr"), ("fuel_type", "jet"), ("sort", "unknown"),
    ("max_distance_miles", 1000),
])
def test_invalid_preferences_rejected(field, bad_value):
    values = dict(language="en", fuel_type="regular", sort="best",
                  max_distance_miles=3)
    values[field] = bad_value
    with pytest.raises(ValueError):
        SearchPreferences(**values)


def test_missing_conversation_restores_saved_preferences_for_direct_location():
    saved = settings()
    found = []
    message = location()
    process_location_message(
        message,
        get_session=lambda sender: None,
        load_preferences=lambda sender: saved,
        search_from_location=lambda incoming, session: found.append(
            (incoming, session)
        ),
        dispatch_state_location=lambda *args: pytest.fail("no active state"),
        send_expected=lambda *args: pytest.fail("should search"),
    )
    assert found == [(message, ConversationSession(
        sender=SENDER, language="es", fuel_type="diesel",
        sort="price", max_distance_miles=3.0,
    ))]


def test_active_session_does_not_load_or_overwrite_saved_preferences():
    session = ConversationSession(sender=SENDER, state=ConversationState.WAITING_SORT)
    prompts = []
    process_location_message(
        location(),
        get_session=lambda sender: session,
        load_preferences=lambda sender: pytest.fail("must not load profile"),
        search_from_location=lambda *args: pytest.fail("must not search"),
        dispatch_state_location=lambda incoming, active: False,
        send_expected=lambda sender, active: prompts.append(active),
    )
    assert prompts == [session]


def test_completed_guided_search_saves_settings_once_without_extra_lookup():
    events = []
    session = ConversationSession(
        sender=SENDER, state=ConversationState.WAITING_LOCATION,
        language="es", fuel_type="diesel", sort="price",
        max_distance_miles=3.0,
    )
    run_location_search(
        location(), session,
        allow_search=lambda sender: True,
        search=lambda **kwargs: events.append("lookup") or "results",
        send_text=lambda **kwargs: events.append("sent"),
        update_session=lambda *args: events.append("state"),
        send_prompt=lambda *args: events.append("navigation"),
        save_preferences=lambda sender, pref: events.append(("saved", sender, pref)),
    )
    assert events == [
        "lookup", "sent", "state", ("saved", SENDER, settings()), "navigation"
    ]


def test_failed_delivery_does_not_save_a_profile():
    run_location_search(
        location(),
        ConversationSession(sender=SENDER, state=ConversationState.WAITING_LOCATION),
        allow_search=lambda sender: True,
        search=lambda **kwargs: "results",
        send_text=lambda **kwargs: (_ for _ in ()).throw(
            WhatsAppServiceError("fail")
        ),
        update_session=lambda *args: pytest.fail("no advance"),
        send_prompt=lambda *args: pytest.fail("no navigation"),
        save_preferences=lambda *args: pytest.fail("no save"),
    )


def test_first_time_direct_location_does_not_overwrite_existing_profile():
    session = ConversationSession(sender=SENDER)
    run_location_search(
        location(), session,
        allow_search=lambda sender: True,
        search=lambda **kwargs: "results",
        send_text=lambda **kwargs: None,
        update_session=lambda *args: None,
        send_prompt=lambda *args: None,
        save_preferences=lambda *args: pytest.fail("default not an explicit choice"),
    )


def test_whatsapp_handler_remembers_after_conversation_expiry(monkeypatch):
    handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_LOCATION,
        language="es", fuel_type="diesel", sort="price",
        max_distance_miles=3.0,
    )
    sent_searches = []
    monkeypatch.setattr(handler.location_search_service, "search",
                        lambda **kwargs: sent_searches.append(kwargs) or "results")
    monkeypatch.setattr(handler, "send_text_message", lambda **kwargs: None)
    monkeypatch.setattr(handler, "send_list_message", lambda **kwargs: None)

    handler.handle_location_message(location())
    assert handler.search_preferences_store.get(SENDER) == settings()
    handler.conversation_store.clear()  # Simulate Redis conversation TTL.
    handler.handle_location_message(location())
    assert len(sent_searches) == 2
    restored = sent_searches[1]["session"]
    assert (restored.language, restored.fuel_type, restored.sort,
            restored.max_distance_miles) == ("es", "diesel", "price", 3)
