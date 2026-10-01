"""Fixed-window rate limiting. Redis when configured (shared across API replicas),
an in-process store otherwise. Fails open on Redis errors so an outage never locks users out."""

import threading
import time

from fastapi import HTTPException

from .config import settings

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class RateLimiter:
    def __init__(self) -> None:
        self._redis = redis.from_url(settings.redis_url) if (redis and settings.redis_url) else None
        self._mem: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: int) -> bool:
        bucket = int(time.time() // window_s)
        k = f"rl:{key}:{bucket}"
        if self._redis is not None:
            try:
                n = self._redis.incr(k)
                if n == 1:
                    self._redis.expire(k, window_s)
                return n <= limit
            except Exception:
                pass
        now = time.time()
        with self._lock:
            if len(self._mem) > 50_000:
                self._mem = {kk: v for kk, v in self._mem.items() if v[1] > now}
            count, expires = self._mem.get(k, (0, now + window_s))
            count += 1
            self._mem[k] = (count, expires)
        return count <= limit

    def reset(self) -> None:
        with self._lock:
            self._mem.clear()


limiter = RateLimiter()


def enforce(key: str, limit: int, window_s: int, message: str = "Too many attempts. Wait a minute and try again.") -> None:
    if not limiter.hit(key, limit, window_s):
        raise HTTPException(status_code=429, detail=message)
