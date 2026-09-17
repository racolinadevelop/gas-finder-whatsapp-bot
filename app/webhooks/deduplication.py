import time
from collections.abc import Callable
from threading import RLock


class InMemoryMessageDeduplicator:
    def __init__(
        self,
        ttl_seconds: float = 24 * 60 * 60,
        max_entries: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")

        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._expires_at: dict[str, float] = {}
        self._lock = RLock()

    def claim(self, message_id: str | None) -> bool:
        """Atomically reserve a message ID if it has not been seen recently."""
        if not message_id:
            return True

        now = self._clock()
        with self._lock:
            self._remove_expired(now)

            if message_id in self._expires_at:
                return False

            if len(self._expires_at) >= self._max_entries:
                oldest_message_id = min(
                    self._expires_at,
                    key=self._expires_at.__getitem__,
                )
                self._expires_at.pop(oldest_message_id)

            self._expires_at[message_id] = now + self._ttl_seconds
            return True

    def release(self, message_id: str | None) -> None:
        """Release a claim so a failed delivery can be retried."""
        if not message_id:
            return

        with self._lock:
            self._expires_at.pop(message_id, None)

    def clear(self) -> None:
        with self._lock:
            self._expires_at.clear()

    def __len__(self) -> int:
        with self._lock:
            self._remove_expired(self._clock())
            return len(self._expires_at)

    def _remove_expired(self, now: float) -> None:
        expired_message_ids = [
            message_id
            for message_id, expires_at in self._expires_at.items()
            if expires_at <= now
        ]
        for message_id in expired_message_ids:
            self._expires_at.pop(message_id)
