from dataclasses import replace
from threading import RLock

from app.conversation.models import ConversationSession


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
