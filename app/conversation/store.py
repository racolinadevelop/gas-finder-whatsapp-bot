import json
from dataclasses import asdict, replace
from hashlib import sha256
from threading import RLock

from app.conversation.models import ConversationSession, ConversationState
from app.persistence import RedisClient


class InMemoryConversationStore:
    """Temporary conversation storage for the current single-process app."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = RLock()

    def get(self, sender: str) -> ConversationSession | None:
        with self._lock:
            return self._sessions.get(sender)

    def get_or_create(self, sender: str) -> ConversationSession:
        with self._lock:
            session = self._sessions.get(sender)

            if session is None:
                session = ConversationSession(sender=sender)
                self._sessions[sender] = session

            return session

    def update(self, sender: str, **changes) -> ConversationSession:
        with self._lock:
            session = self._sessions.get(sender)

            if session is None:
                session = ConversationSession(sender=sender)

            updated_session = replace(session, **changes)
            self._sessions[sender] = updated_session
            return updated_session

    def pop(self, sender: str) -> ConversationSession | None:
        with self._lock:
            return self._sessions.pop(sender, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


class RedisConversationStore:
    """Conversation storage shared by every application instance."""

    def __init__(
        self,
        client: RedisClient,
        *,
        key_prefix: str = "gas-finder",
        ttl_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")

        self._client = client
        self._key_prefix = key_prefix.rstrip(":")
        self._ttl_seconds = ttl_seconds

    def get(self, sender: str) -> ConversationSession | None:
        return self._read(sender)

    def get_or_create(self, sender: str) -> ConversationSession:
        with self._sender_lock(sender):
            session = self._read(sender)
            if session is None:
                session = ConversationSession(sender=sender)
                self._write(session)
            return session

    def update(self, sender: str, **changes) -> ConversationSession:
        with self._sender_lock(sender):
            session = self._read(sender) or ConversationSession(sender=sender)
            updated_session = replace(session, **changes)
            self._write(updated_session)
            return updated_session

    def pop(self, sender: str) -> ConversationSession | None:
        with self._sender_lock(sender):
            session = self._read(sender)
            self._client.delete(self._key(sender))
            return session

    def clear(self) -> None:
        keys = list(
            self._client.scan_iter(
                match=f"{self._key_prefix}:conversation:*",
            )
        )
        if keys:
            self._client.delete(*keys)

    def _read(self, sender: str) -> ConversationSession | None:
        raw_session = self._client.get(self._key(sender))
        if raw_session is None:
            return None
        if isinstance(raw_session, bytes):
            raw_session = raw_session.decode("utf-8")

        data = json.loads(raw_session)
        return ConversationSession(
            sender=data["sender"],
            state=ConversationState(data["state"]),
            language=data["language"],
            fuel_type=data["fuel_type"],
            sort=data["sort"],
            max_distance_miles=data["max_distance_miles"],
        )

    def _write(self, session: ConversationSession) -> None:
        self._client.set(
            self._key(session.sender),
            json.dumps(asdict(session), separators=(",", ":")),
            ex=self._ttl_seconds,
        )

    def _key(self, sender: str) -> str:
        sender_hash = sha256(sender.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:conversation:{sender_hash}"

    def _sender_lock(self, sender: str):
        sender_hash = sha256(sender.encode("utf-8")).hexdigest()
        return self._client.lock(
            f"{self._key_prefix}:lock:conversation:{sender_hash}",
            timeout=10,
            blocking_timeout=5,
        )
