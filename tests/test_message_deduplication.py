from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.handlers import whatsapp as whatsapp_handler
from app.webhooks import InMemoryMessageDeduplicator


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def webhook_payload(message_id: str | None = "wamid.duplicate") -> dict:
    message = {
        "from": "15551234567",
        "type": "text",
        "text": {"body": "hello"},
    }
    if message_id is not None:
        message["id"] = message_id

    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [message],
                        }
                    }
                ]
            }
        ]
    }


def test_claim_rejects_duplicate_until_ttl_expires():
    clock = FakeClock()
    deduplicator = InMemoryMessageDeduplicator(
        ttl_seconds=10,
        clock=clock,
    )

    assert deduplicator.claim("wamid.one") is True
    assert deduplicator.claim("wamid.one") is False

    clock.now = 10

    assert deduplicator.claim("wamid.one") is True


def test_release_allows_message_to_be_claimed_again():
    deduplicator = InMemoryMessageDeduplicator()

    assert deduplicator.claim("wamid.one") is True

    deduplicator.release("wamid.one")

    assert deduplicator.claim("wamid.one") is True


def test_only_one_concurrent_claim_succeeds():
    deduplicator = InMemoryMessageDeduplicator()
    barrier = Barrier(8)

    def claim_message() -> bool:
        barrier.wait()
        return deduplicator.claim("wamid.concurrent")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: claim_message(), range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7


def test_missing_message_id_is_never_deduplicated():
    deduplicator = InMemoryMessageDeduplicator()

    assert deduplicator.claim(None) is True
    assert deduplicator.claim(None) is True


def test_oldest_claim_is_evicted_when_capacity_is_reached():
    clock = FakeClock()
    deduplicator = InMemoryMessageDeduplicator(
        ttl_seconds=10,
        max_entries=2,
        clock=clock,
    )

    assert deduplicator.claim("wamid.one") is True
    clock.now = 1
    assert deduplicator.claim("wamid.two") is True
    clock.now = 2
    assert deduplicator.claim("wamid.three") is True

    assert len(deduplicator) == 2
    assert deduplicator.claim("wamid.one") is True


def test_webhook_dispatches_duplicate_message_only_once(monkeypatch):
    ensured_users = []
    dispatched_messages = []
    monkeypatch.setattr(
        whatsapp_handler.subscription_service,
        "ensure_user",
        lambda sender: ensured_users.append(sender),
    )
    monkeypatch.setattr(
        whatsapp_handler.message_router,
        "dispatch",
        lambda message: dispatched_messages.append(message),
    )
    payload = webhook_payload()

    first_result = whatsapp_handler.handle_whatsapp_webhook(payload)
    retry_result = whatsapp_handler.handle_whatsapp_webhook(payload)

    assert first_result == {"status": "ok"}
    assert retry_result == {"status": "ok"}
    assert ensured_users == ["15551234567"]
    assert len(dispatched_messages) == 1


def test_webhook_releases_claim_after_unexpected_failure(monkeypatch):
    attempts = []

    def dispatch(message):
        attempts.append(message)
        if len(attempts) == 1:
            raise RuntimeError("temporary failure")

    monkeypatch.setattr(
        whatsapp_handler.subscription_service,
        "ensure_user",
        lambda sender: None,
    )
    monkeypatch.setattr(
        whatsapp_handler.message_router,
        "dispatch",
        dispatch,
    )
    payload = webhook_payload("wamid.retryable")

    with pytest.raises(RuntimeError, match="temporary failure"):
        whatsapp_handler.handle_whatsapp_webhook(payload)

    result = whatsapp_handler.handle_whatsapp_webhook(payload)

    assert result == {"status": "ok"}
    assert len(attempts) == 2
