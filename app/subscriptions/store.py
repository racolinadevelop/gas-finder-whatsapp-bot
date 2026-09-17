from dataclasses import replace
from threading import RLock

from app.subscriptions.models import UserSubscription


class InMemorySubscriptionStore:
    """Temporary subscription storage for the current single-process app."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, UserSubscription] = {}
        self._lock = RLock()

    def get(self, whatsapp_id: str) -> UserSubscription | None:
        with self._lock:
            return self._subscriptions.get(whatsapp_id)

    def get_or_create(self, whatsapp_id: str) -> UserSubscription:
        with self._lock:
            subscription = self._subscriptions.get(whatsapp_id)

            if subscription is None:
                subscription = UserSubscription(whatsapp_id=whatsapp_id)
                self._subscriptions[whatsapp_id] = subscription

            return subscription

    def update(self, whatsapp_id: str, **changes) -> UserSubscription:
        with self._lock:
            subscription = self.get_or_create(whatsapp_id)
            updated = replace(subscription, **changes)
            self._subscriptions[whatsapp_id] = updated
            return updated

    def clear(self) -> None:
        with self._lock:
            self._subscriptions.clear()
