"""Webhook orchestration tests without Meta, storage, or network calls."""

import pytest

from app.handlers.webhook_dispatch import process_webhook
from app.models import IncomingMessage


def test_status_event_is_acknowledged_without_claiming_or_dispatching():
    events = []

    result = process_webhook(
        {"event": "status"},
        parse_message=lambda payload: None,
        claim_message=lambda key: events.append("claim") or True,
        release_message=lambda key: events.append("release"),
        ensure_user=lambda sender: events.append("user"),
        dispatch_message=lambda msg: events.append("dispatch"),
    )

    assert result == {"status": "ok"}
    assert events == []


def test_new_message_is_claimed_then_user_ensured_then_dispatched():
    events = []
    incoming = IncomingMessage(
        sender="15551234567",
        message_type="text",
        message_id="wamid.first",
        text="hola",
    )

    result = process_webhook(
        {"event": "message"},
        parse_message=lambda payload: incoming,
        claim_message=lambda key: events.append(("claim", key)) or True,
        release_message=lambda key: events.append(("release", key)),
        ensure_user=lambda sender: events.append(("user", sender)),
        dispatch_message=lambda msg: events.append(("dispatch", msg)),
    )

    assert result == {"status": "ok"}
    assert events == [
        ("claim", "wamid.first"),
        ("user", "15551234567"),
        ("dispatch", incoming),
    ]


def test_duplicate_is_acknowledged_without_creating_user_or_dispatching():
    events = []
    incoming = IncomingMessage(
        sender="15551234567",
        message_type="text",
        message_id="wamid.duplicate",
    )

    result = process_webhook(
        {},
        parse_message=lambda payload: incoming,
        claim_message=lambda key: events.append("claim") or False,
        release_message=lambda key: events.append("release"),
        ensure_user=lambda sender: events.append("user"),
        dispatch_message=lambda msg: events.append("dispatch"),
    )

    assert result == {"status": "ok"}
    assert events == ["claim"]


@pytest.mark.parametrize("failing_step", ["ensure_user", "dispatch"])
def test_error_releases_claim_and_propagates_for_retry(failing_step):
    events = []
    incoming = IncomingMessage(
        sender="15551234567",
        message_type="location",
        message_id="wamid.retry",
    )

    def ensure_user(sender):
        events.append("user")
        if failing_step == "ensure_user":
            raise RuntimeError("temporary error")

    def dispatch(msg):
        events.append("dispatch")
        if failing_step == "dispatch":
            raise RuntimeError("temporary error")

    with pytest.raises(RuntimeError, match="temporary error"):
        process_webhook(
            {},
            parse_message=lambda payload: incoming,
            claim_message=lambda key: events.append("claim") or True,
            release_message=lambda key: events.append(("release", key)),
            ensure_user=ensure_user,
            dispatch_message=dispatch,
        )

    expected = ["claim", "user"]
    if failing_step == "dispatch":
        expected.append("dispatch")
    assert events == expected + [("release", "wamid.retry")]


def test_missing_message_id_passes_none_to_deduplicator():
    captured = []
    incoming = IncomingMessage(sender="15551234567", message_type="text")

    result = process_webhook(
        {},
        parse_message=lambda payload: incoming,
        claim_message=lambda key: captured.append(key) or True,
        release_message=lambda key: None,
        ensure_user=lambda sender: None,
        dispatch_message=lambda message: None,
    )

    assert result == {"status": "ok"}
    assert captured == [None]
