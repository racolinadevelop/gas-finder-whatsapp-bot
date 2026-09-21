"""Routes element caps are atomic, calendar bounded and fail closed in production."""

from datetime import datetime, timezone

import pytest

from app.services.route_budget import RouteBudget, reserve_production_route_elements
from app.services import road_routes
import httpx


def places(count=5):
    return {"stations": [
        {"latitude": 38.25 + i / 1000, "longitude": -85.75 - i / 1000}
        for i in range(count)
    ]}


class FakeResponse:
    def __init__(self, body):
        self._body = body
        self.response = httpx.Response(
            200, json=body,
            request=httpx.Request("POST", "https://routes.googleapis.com/"),
        )

    def raise_for_status(self):
        self.response.raise_for_status()

    def json(self):
        return self._body


class FakeRedis:
    """Represent the atomic Lua operation without depending on a live Redis."""
    def __init__(self):
        self.counters = {}
        self.expiry = {}
        self.calls = []

    def eval(self, script, n_keys, *args):
        assert n_keys == 2 and "INCRBY" in script
        day_key, month_key, requested, day_limit, month_limit, day_end, month_end = args
        self.calls.append((day_key, month_key, requested))
        daily = self.counters.get(day_key, 0)
        monthly = self.counters.get(month_key, 0)
        if daily + requested > day_limit or monthly + requested > month_limit:
            return 0
        self.counters[day_key] = daily + requested
        self.counters[month_key] = monthly + requested
        self.expiry[day_key] = day_end
        self.expiry[month_key] = month_end
        return 1


def test_daily_and_monthly_caps_shared_across_multiple_workers():
    redis = FakeRedis()
    clock = lambda: datetime(2026, 9, 21, 15, tzinfo=timezone.utc)
    a = RouteBudget(redis, key_prefix="test", daily_limit=7, monthly_limit=13,
                    now_fn=clock)
    b = RouteBudget(redis, key_prefix="test", daily_limit=7, monthly_limit=13,
                    now_fn=clock)
    assert a.reserve(5)
    assert not b.reserve(5)
    assert b.reserve(2)
    assert not a.reserve(1)
    assert list(redis.counters.values()) == [7, 7]
    day_key, month_key = redis.counters
    assert ":day:20260921" in day_key
    assert ":month:202609" in month_key
    assert redis.expiry[day_key] == int(datetime(
        2026, 9, 22, tzinfo=timezone.utc
    ).timestamp())
    assert redis.expiry[month_key] == int(datetime(
        2026, 10, 1, tzinfo=timezone.utc
    ).timestamp())


def test_new_day_resets_only_daily_allowance_and_month_cap_persists():
    redis = FakeRedis()
    current = [datetime(2026, 9, 21, 23, tzinfo=timezone.utc)]
    quota = RouteBudget(
        redis, daily_limit=5, monthly_limit=8, now_fn=lambda: current[0]
    )
    assert quota.reserve(5)
    current[0] = datetime(2026, 9, 22, 0, tzinfo=timezone.utc)
    assert quota.reserve(3)
    assert not quota.reserve(1)
    assert redis.counters[
        next(key for key in redis.counters if ":month:202609" in key)
    ] == 8
    current[0] = datetime(2026, 10, 1, 0, tzinfo=timezone.utc)
    assert quota.reserve(5)
    assert not quota.reserve(1)


@pytest.mark.parametrize("bad", [0, -1, 2.5, True])
def test_invalid_or_oversize_reservations_do_not_change_counters(bad):
    redis = FakeRedis()
    budget = RouteBudget(redis, daily_limit=5, monthly_limit=10)
    with pytest.raises(ValueError):
        budget.reserve(bad)
    assert not budget.reserve(6)
    assert redis.counters == {}


def test_prod_routes_request_is_skipped_without_budget_or_redis(monkeypatch):
    outbound = []
    monkeypatch.setattr(road_routes, "APP_ENV", "production")
    monkeypatch.setattr(
        road_routes, "reserve_production_route_elements",
        lambda count: outbound.append(("reserve", count)) or False,
    )
    monkeypatch.setattr(
        road_routes.httpx, "post",
        lambda *a, **k: pytest.fail("Must not call billable Routes after rejection"),
    )
    result = places(5)
    assert road_routes.add_road_routes(
        result, latitude=38.25, longitude=-85.75, api_key="fake",
    ) is result
    assert outbound == [("reserve", 5)]


def test_prod_routes_reserves_actual_eligible_elements_before_one_request(monkeypatch):
    outbound = []
    monkeypatch.setattr(road_routes, "APP_ENV", "production")
    monkeypatch.setattr(
        road_routes, "reserve_production_route_elements",
        lambda count: outbound.append(("reserve", count)) or True,
    )
    monkeypatch.setattr(
        road_routes.httpx, "post",
        lambda *a, **k: outbound.append(("post", len(k["json"]["destinations"])))
        or FakeResponse([]),
    )
    stations = places(4)
    stations["stations"][1]["latitude"] = None
    road_routes.add_road_routes(
        stations, latitude=38.25, longitude=-85.75,
        api_key="fake", max_destinations=5,
    )
    assert outbound == [("reserve", 3), ("post", 3)]


def test_production_budget_failure_closed_if_redis_unreachable(monkeypatch):
    import app.services.route_budget as guard
    monkeypatch.setattr(guard, "REDIS_URL", "redis://fake")
    monkeypatch.setattr(guard, "_budget", None)
    monkeypatch.setattr(
        guard, "build_redis_client",
        lambda _: (_ for _ in ()).throw(ConnectionError("Redis unreachable")),
    )
    assert not reserve_production_route_elements(5)
    monkeypatch.setattr(guard, "REDIS_URL", None)
    assert not reserve_production_route_elements(1)
