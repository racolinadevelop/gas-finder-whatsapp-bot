"""Fail-closed, shared Redis reservation of billable Google Route Matrix elements.

Reserve *before* HTTP; count every attempted request conservatively, including
timeouts and failed responses. An atomic Lua operation prevents independent
Railway workers from exceeding configured daily and monthly element budgets.
These budgets protect only this app/key usage; they are not Google billing caps.
"""

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.config import (
    REDIS_KEY_PREFIX,
    REDIS_URL,
    ROUTES_DAILY_ELEMENT_LIMIT,
    ROUTES_MONTHLY_ELEMENT_LIMIT,
)
from app.persistence.redis_client import build_redis_client

logger = logging.getLogger(__name__)

_RESERVE_LUA = """
local daily = tonumber(redis.call('GET', KEYS[1]) or '0')
local monthly = tonumber(redis.call('GET', KEYS[2]) or '0')
local count = tonumber(ARGV[1])
if daily + count > tonumber(ARGV[2])
   or monthly + count > tonumber(ARGV[3]) then
    return 0
end
redis.call('INCRBY', KEYS[1], count)
redis.call('EXPIREAT', KEYS[1], tonumber(ARGV[4]))
redis.call('INCRBY', KEYS[2], count)
redis.call('EXPIREAT', KEYS[2], tonumber(ARGV[5]))
return 1
"""


class RouteBudget:
    def __init__(
        self,
        client,
        *,
        key_prefix: str = REDIS_KEY_PREFIX,
        daily_limit: int = ROUTES_DAILY_ELEMENT_LIMIT,
        monthly_limit: int = ROUTES_MONTHLY_ELEMENT_LIMIT,
        now_fn=None,
    ):
        if not 0 < daily_limit <= monthly_limit:
            raise ValueError("Routes daily limit must be positive and <= monthly limit")
        self._client = client
        self._prefix = key_prefix.rstrip(":")
        self._daily_limit = daily_limit
        self._monthly_limit = monthly_limit
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def reserve(self, elements: int) -> bool:
        if not isinstance(elements, int) or isinstance(elements, bool) or elements < 1:
            raise ValueError("Elements must be a positive integer")
        if elements > self._daily_limit or elements > self._monthly_limit:
            return False
        now = self._now_fn().astimezone(timezone.utc)
        next_day = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        next_month = (
            now.replace(year=now.year + (now.month == 12),
                        month=1 if now.month == 12 else now.month + 1,
                        day=1, hour=0, minute=0, second=0, microsecond=0)
        )
        keys = [
            f"{self._prefix}:routes-budget:day:{now:%Y%m%d}",
            f"{self._prefix}:routes-budget:month:{now:%Y%m}",
        ]
        return int(self._client.eval(
            _RESERVE_LUA, 2, *keys, elements,
            self._daily_limit, self._monthly_limit,
            int(next_day.timestamp()), int(next_month.timestamp()),
        )) == 1


_budget = None
_budget_lock = Lock()


def reserve_production_route_elements(elements: int) -> bool:
    """No reachable Redis => no external billable Routes call (fail closed)."""
    global _budget
    if not REDIS_URL:
        logger.warning("Routes budget unavailable: Redis is not configured")
        return False
    try:
        if _budget is None:
            with _budget_lock:
                if _budget is None:
                    _budget = RouteBudget(build_redis_client(REDIS_URL))
        accepted = _budget.reserve(elements)
    except Exception:
        logger.warning("Routes budget unavailable; skipped billable request")
        return False
    if not accepted:
        logger.info("Routes element cap reached; skipped billable request")
    return accepted
