"""Durable explicit language choice, independent of temporary search sessions.

Only a SHA-256 WhatsApp sender hash and an allowlisted language are stored.
No raw phone number, location, or message text is persisted.
"""

from hashlib import sha256
from threading import RLock


class InMemoryLanguageStore:
    def __init__(self):
        self._values = {}
        self._lock = RLock()

    def get(self, sender: str) -> str | None:
        with self._lock:
            return self._values.get(sha256(sender.encode()).hexdigest())

    def save(self, sender: str, language: str) -> None:
        if language not in {"es", "en"}:
            raise ValueError("Unsupported language")
        with self._lock:
            self._values[sha256(sender.encode()).hexdigest()] = language

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


class PostgresLanguageStore:
    def __init__(self, database_url: str, *, connect_fn=None):
        if not database_url:
            raise ValueError("Database URL is required")
        self._url = database_url
        self._connect_fn = connect_fn
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_language_preferences (
                        whatsapp_id_hash TEXT PRIMARY KEY,
                        language TEXT NOT NULL CHECK (language IN ('es', 'en')),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._url)
        import psycopg
        return psycopg.connect(self._url)

    def get(self, sender: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT language FROM user_language_preferences
                    WHERE whatsapp_id_hash = %s
                """, (sha256(sender.encode()).hexdigest(),))
                row = cur.fetchone()
        return row[0] if row else None

    def save(self, sender: str, language: str) -> None:
        if language not in {"es", "en"}:
            raise ValueError("Unsupported language")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_language_preferences (whatsapp_id_hash, language)
                    VALUES (%s, %s)
                    ON CONFLICT (whatsapp_id_hash) DO UPDATE SET
                        language = EXCLUDED.language,
                        updated_at = CURRENT_TIMESTAMP
                """, (sha256(sender.encode()).hexdigest(), language))
