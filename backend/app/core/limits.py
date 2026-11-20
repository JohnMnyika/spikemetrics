import asyncio
import time
from collections import deque


class SpacedRateLimiter:
    """Serializes calls with a minimum inter-request delay and rolling quota."""

    def __init__(self, interval: float, limit: int | None = None, period: float = 60):
        self.interval, self.limit, self.period = interval, limit, period
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._calls: deque[float] = deque()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= self.period:
                self._calls.popleft()
            delay = max(0.0, self.interval - (now - self._last))
            if self.limit is not None and len(self._calls) >= self.limit:
                delay = max(delay, self.period - (now - self._calls[0]))
            if delay:
                await asyncio.sleep(delay)
            now = time.monotonic()
            self._last = now
            self._calls.append(now)


class QuotaTracker:
    """In-memory development tracker; production requests are persisted in api_quota_usage."""

    def __init__(self, daily_limit: int = 100):
        self.daily_limit, self.used = daily_limit, 0

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.used)

    def consume(self, count: int = 1) -> bool:
        if count > self.remaining:
            return False
        self.used += count
        return True
