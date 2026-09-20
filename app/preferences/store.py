"""Remember search selections without persisting locations or message content."""

from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from typing import Protocol

from app.constants import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES
from app.conversation.models import ConversationSession


@dataclass(frozen=True, slots=True)
class SearchPreferences:
    language: str
    fuel_type: str
    sort: str
    max_distance_miles: float | None

    @classmethod
    def from_session(cls, session: ConversationSession) -> "SearchPreferences":
        return cls(
            language=session.language,
            fuel_type=session.fuel_type,
            sort=session.sort,
            max_distance_miles=session.max_distance_miles,
        )

    def __post_init__(self) -> None:
        if self.language not in {"es", "en"}:
            raise ValueError("Invalid preference language")
        if self.fuel_type not in {"regular", "premium", "diesel"}:
            raise ValueError("Invalid preference fuel type")
        if self.sort not in {"best", "price", "distance"}:
            raise ValueError("Invalid preference sort")
        if self.max_distance_miles is not None and not (
            MIN_DISTANCE_MILES <= self.max_distance_miles <= MAX_DISTANCE_MILES
        ):
            raise ValueError("Invalid preference distance")


class SearchPreferencesStore(Protocol):
    def get(self, whatsapp_id: str) -> SearchPreferences | None: ...
    def save(self, whatsapp_id: str, preferences: SearchPreferences) -> None: ...


class InMemorySearchPreferencesStore:
    """Local/test storage; unlike conversations it has no session TTL."""

    def __init__(self) -> None:
        self._values: dict[str, SearchPreferences] = {}
        self._lock = RLock()

    def get(self, whatsapp_id: str) -> SearchPreferences | None:
        with self._lock:
            return self._values.get(whatsapp_id)

    def save(self, whatsapp_id: str, preferences: SearchPreferences) -> None:
        with self._lock:
            self._values[whatsapp_id] = preferences

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


class PostgresSearchPreferencesStore:
    """Durable profile backed by a table independent of conversation TTL.

    Only a SHA-256 WhatsApp-ID hash and explicitly selected search settings
    are stored. No raw phone number, coordinates, or WhatsApp message text.
    """

    def __init__(self, database_url: str, *, connect_fn=None) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._connect_fn = connect_fn
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_search_preferences (
                        whatsapp_id_hash TEXT PRIMARY KEY,
                        language TEXT NOT NULL,
                        fuel_type TEXT NOT NULL,
                        sort TEXT NOT NULL,
                        max_distance_miles DOUBLE PRECISION,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def get(self, whatsapp_id: str) -> SearchPreferences | None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT language, fuel_type, sort, max_distance_miles
                    FROM user_search_preferences
                    WHERE whatsapp_id_hash = %s
                    """,
                    (self._hash(whatsapp_id),),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return SearchPreferences(
            language=row[0], fuel_type=row[1], sort=row[2],
            max_distance_miles=row[3],
        )

    def save(self, whatsapp_id: str, preferences: SearchPreferences) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_search_preferences (
                        whatsapp_id_hash, language, fuel_type, sort,
                        max_distance_miles
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (whatsapp_id_hash) DO UPDATE SET
                        language = EXCLUDED.language,
                        fuel_type = EXCLUDED.fuel_type,
                        sort = EXCLUDED.sort,
                        max_distance_miles = EXCLUDED.max_distance_miles,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        self._hash(whatsapp_id),
                        preferences.language,
                        preferences.fuel_type,
                        preferences.sort,
                        preferences.max_distance_miles,
                    ),
                )

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url)

    @staticmethod
    def _hash(whatsapp_id: str) -> str:
        return sha256(whatsapp_id.encode("utf-8")).hexdigest()
