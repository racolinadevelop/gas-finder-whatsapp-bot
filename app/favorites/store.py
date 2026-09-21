"""Per-user favorite stations; snapshots never contain search coordinates or fuel prices.

Recent numbered results are valid for 24 hours. Favorites remain stored if
Premium expires, but reads, additions and deletions must be separately gated
by SubscriptionService.can_use_feature at the authenticated WhatsApp boundary.
"""

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import RLock

from app.favorites.models import FavoriteStation

MAX_FAVORITES = 10
RECENT_TTL = timedelta(hours=24)


class FavoriteStoreError(Exception):
    pass


def user_key(whatsapp_id: str) -> str:
    return sha256(whatsapp_id.encode("utf-8")).hexdigest()


def _serialize(stations: tuple[FavoriteStation, ...]) -> str:
    return json.dumps(
        [{"key": s.key, "name": s.name, "address": s.address} for s in stations],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _deserialize(payload: str) -> tuple[FavoriteStation, ...]:
    return tuple(FavoriteStation(**entry) for entry in json.loads(payload))


class InMemoryFavoriteStore:
    def __init__(self):
        self._lock = RLock()
        self._recent = {}
        self._favorites = {}

    def record_results(self, whatsapp_id: str, stations: tuple[FavoriteStation, ...]):
        with self._lock:
            self._recent[user_key(whatsapp_id)] = (
                tuple(stations[:5]), datetime.now(timezone.utc)
            )

    def add_from_recent(self, whatsapp_id: str, index: int) -> FavoriteStation:
        hashed = user_key(whatsapp_id)
        with self._lock:
            recent = self._recent.get(hashed)
            if (
                recent is None
                or datetime.now(timezone.utc) - recent[1] >= RECENT_TTL
                or not 1 <= index <= len(recent[0])
            ):
                raise FavoriteStoreError("no_recent_result")
            chosen = recent[0][index - 1]
            favorites = self._favorites.setdefault(hashed, [])
            if any(item.key == chosen.key for item in favorites):
                return chosen
            if len(favorites) >= MAX_FAVORITES:
                raise FavoriteStoreError("limit")
            favorites.append(chosen)
            return chosen

    def list_favorites(self, whatsapp_id: str) -> tuple[FavoriteStation, ...]:
        with self._lock:
            return tuple(self._favorites.get(user_key(whatsapp_id), []))

    def remove_by_digest(self, whatsapp_id: str, digest: str) -> FavoriteStation:
        with self._lock:
            favorites = self._favorites.get(user_key(whatsapp_id), [])
            for index, station in enumerate(favorites):
                if sha256(station.key.encode()).hexdigest() == digest:
                    return favorites.pop(index)
        raise FavoriteStoreError("missing_favorite")

    def remove_favorite(self, whatsapp_id: str, index: int) -> FavoriteStation:
        with self._lock:
            favorites = self._favorites.get(user_key(whatsapp_id), [])
            if not 1 <= index <= len(favorites):
                raise FavoriteStoreError("missing_favorite")
            return favorites.pop(index - 1)


class PostgresFavoriteStore:
    def __init__(self, database_url: str, *, connect_fn=None):
        if not database_url:
            raise ValueError("PostgreSQL URL is required for favorites")
        self._database_url = database_url
        self._connect_fn = connect_fn
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS premium_recent_stations (
                        whatsapp_id_hash TEXT PRIMARY KEY,
                        stations_json TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS premium_favorite_stations (
                        whatsapp_id_hash TEXT NOT NULL,
                        station_key TEXT NOT NULL,
                        name TEXT NOT NULL,
                        address TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (whatsapp_id_hash, station_key)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS premium_favorites_user_order_idx
                    ON premium_favorite_stations (whatsapp_id_hash, created_at, station_key)
                """)

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url)

    def record_results(self, whatsapp_id: str, stations: tuple[FavoriteStation, ...]):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO premium_recent_stations
                        (whatsapp_id_hash, stations_json)
                    VALUES (%s, %s)
                    ON CONFLICT (whatsapp_id_hash) DO UPDATE SET
                        stations_json = EXCLUDED.stations_json,
                        updated_at = CURRENT_TIMESTAMP
                """, (user_key(whatsapp_id), _serialize(tuple(stations[:5]))))

    def add_from_recent(self, whatsapp_id: str, index: int) -> FavoriteStation:
        if not 1 <= index <= 5:
            raise FavoriteStoreError("no_recent_result")
        hashed = user_key(whatsapp_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Serialize concurrent add/remove operations for this user.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (hashed,))
                cur.execute("""
                    SELECT stations_json FROM premium_recent_stations
                    WHERE whatsapp_id_hash = %s
                    AND updated_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                """, (hashed,))
                row = cur.fetchone()
                if row is None:
                    raise FavoriteStoreError("no_recent_result")
                recent = _deserialize(row[0])
                if index > len(recent):
                    raise FavoriteStoreError("no_recent_result")
                chosen = recent[index - 1]
                cur.execute("""
                    SELECT 1 FROM premium_favorite_stations
                    WHERE whatsapp_id_hash = %s AND station_key = %s
                """, (hashed, chosen.key))
                if cur.fetchone() is not None:
                    return chosen
                cur.execute("""
                    SELECT COUNT(*) FROM premium_favorite_stations
                    WHERE whatsapp_id_hash = %s
                """, (hashed,))
                if cur.fetchone()[0] >= MAX_FAVORITES:
                    raise FavoriteStoreError("limit")
                cur.execute("""
                    INSERT INTO premium_favorite_stations
                        (whatsapp_id_hash, station_key, name, address)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (whatsapp_id_hash, station_key) DO NOTHING
                """, (hashed, chosen.key, chosen.name, chosen.address))
        return chosen

    def list_favorites(self, whatsapp_id: str) -> tuple[FavoriteStation, ...]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT station_key, name, address
                    FROM premium_favorite_stations
                    WHERE whatsapp_id_hash = %s
                    ORDER BY created_at, station_key
                    LIMIT %s
                """, (user_key(whatsapp_id), MAX_FAVORITES))
                return tuple(FavoriteStation(*row) for row in cur.fetchall())

    def remove_by_digest(self, whatsapp_id: str, digest: str) -> FavoriteStation:
        hashed = user_key(whatsapp_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (hashed,))
                cur.execute("""
                    SELECT station_key, name, address
                    FROM premium_favorite_stations
                    WHERE whatsapp_id_hash = %s
                """, (hashed,))
                for row in cur.fetchall():
                    station = FavoriteStation(*row)
                    if sha256(station.key.encode()).hexdigest() == digest:
                        cur.execute("""
                            DELETE FROM premium_favorite_stations
                            WHERE whatsapp_id_hash = %s AND station_key = %s
                        """, (hashed, station.key))
                        return station
        raise FavoriteStoreError("missing_favorite")

    def remove_favorite(self, whatsapp_id: str, index: int) -> FavoriteStation:
        if not 1 <= index <= MAX_FAVORITES:
            raise FavoriteStoreError("missing_favorite")
        hashed = user_key(whatsapp_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (hashed,))
                cur.execute("""
                    SELECT station_key, name, address
                    FROM premium_favorite_stations
                    WHERE whatsapp_id_hash = %s
                    ORDER BY created_at, station_key LIMIT %s
                """, (hashed, MAX_FAVORITES))
                rows = cur.fetchall()
                if index > len(rows):
                    raise FavoriteStoreError("missing_favorite")
                chosen = FavoriteStation(*rows[index - 1])
                cur.execute("""
                    DELETE FROM premium_favorite_stations
                    WHERE whatsapp_id_hash = %s AND station_key = %s
                """, (hashed, chosen.key))
                return chosen
