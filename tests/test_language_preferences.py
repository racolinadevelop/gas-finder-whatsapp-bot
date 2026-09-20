"""Explicit language choice persists independently of searches or Redis session TTL."""

from hashlib import sha256

import pytest

from app.preferences.language import InMemoryLanguageStore, PostgresLanguageStore


class FakeDb:
    def __init__(self):
        self.rows = {}
        self.created = False

    def connect(self, _url):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return FakeCursor(self.db)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        statement = " ".join(query.split()).lower()
        if statement.startswith("create table"):
            self.db.created = True
        elif statement.startswith("select"):
            lang = self.db.rows.get(params[0])
            self.row = (lang,) if lang else None
        elif statement.startswith("insert"):
            self.db.rows[params[0]] = params[1]
        else:
            raise AssertionError(f"Unexpected SQL: {statement}")

    def fetchone(self):
        return self.row


def test_language_is_durable_without_a_search_and_identifiers_are_hashed():
    sender = "15551234567"
    db = FakeDb()
    first = PostgresLanguageStore("postgres://test", connect_fn=db.connect)
    assert first.get(sender) is None
    first.save(sender, "es")
    another_process = PostgresLanguageStore("postgres://test", connect_fn=db.connect)
    assert another_process.get(sender) == "es"
    assert another_process.get("15550000000") is None
    another_process.save(sender, "en")
    assert first.get(sender) == "en"
    assert db.created
    assert db.rows == {sha256(sender.encode()).hexdigest(): "en"}
    assert sender not in repr(db.rows)


@pytest.mark.parametrize("invalid", ["", "fr", "ES", "spanish"])
def test_language_store_rejects_unsupported_values(invalid):
    memory = InMemoryLanguageStore()
    with pytest.raises(ValueError):
        memory.save("user", invalid)
    assert memory.get("user") is None
    db = FakeDb()
    durable = PostgresLanguageStore("postgres://test", connect_fn=db.connect)
    with pytest.raises(ValueError):
        durable.save("user", invalid)
    assert durable.get("user") is None
