"""``DailyTurnCap`` — a ready-made per-key daily turn cap for ``quota`` + ``on_turn``.

    cap = DailyTurnCap(50)                 # 50 model calls per user per UTC day
    AskPanelConfig(..., quota=cap.quota, on_turn=cap.on_turn)

The default counter is **in-memory and per process**: it resets on restart and is not
shared across workers, so treat it as best-effort. For a shared or durable cap, pass a
``counter`` implementing ``get(key, day) -> int`` and ``incr(key, day) -> None``
(sync or async) backed by Redis or a table.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, tzinfo
from typing import Any, Protocol

from .provider import Usage

DEFAULT_MESSAGE = "You've used today's {limit} questions — try again tomorrow."


class TurnCounter(Protocol):
    """Storage for ``DailyTurnCap``. Methods may be sync or async."""

    def get(self, key: str, day: date) -> int | Any: ...

    def incr(self, key: str, day: date) -> None | Any: ...


class MemoryCounter:
    """Per-process, thread-safe dict counter. Old days are dropped as new ones start."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, date], int] = {}
        self._lock = threading.Lock()

    def get(self, key: str, day: date) -> int:
        with self._lock:
            return self._counts.get((key, day), 0)

    def incr(self, key: str, day: date) -> None:
        with self._lock:
            self._counts[(key, day)] = self._counts.get((key, day), 0) + 1
            stale = [k for k in self._counts if k[1] < day]
            for k in stale:
                del self._counts[k]


def default_key(user: Any) -> str:
    """``user.id`` / ``user["id"]``, else ``email``, else ``str(user)``."""
    for attr in ("id", "email"):
        val = user.get(attr) if isinstance(user, dict) else getattr(user, attr, None)
        if val:
            return str(val)
    return str(user)


class DailyTurnCap:
    """Cap model calls (``/chat`` + ``/summarize``) per key per day.

    - ``limit``: calls allowed per key per day.
    - ``key``: maps the host's user object to a string (default: id, email, or str).
      Use ``lambda u: u.org_id`` for a per-organisation cap.
    - ``message``: the 429 text; ``{limit}`` is substituted.
    - ``counter``: storage; default ``MemoryCounter()`` (per process, best-effort).
    - ``tz``: which day it is; default UTC.
    - ``count_failed``: whether a stream that died midway (``usage is None``) counts.
      Default True — the model was called.
    """

    def __init__(
        self,
        limit: int,
        *,
        key: Callable[[Any], str] = default_key,
        message: str = DEFAULT_MESSAGE,
        counter: TurnCounter | None = None,
        tz: tzinfo = UTC,
        count_failed: bool = True,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.key = key
        self.message = message
        self.counter: TurnCounter = counter or MemoryCounter()
        self.tz = tz
        self.count_failed = count_failed

    def today(self) -> date:
        return datetime.now(self.tz).date()

    async def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        result = fn(*args)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def used(self, user: Any) -> int:
        """Calls made today by this user's key."""
        return int(await self._call(self.counter.get, self.key(user), self.today()))

    async def remaining(self, user: Any) -> int:
        return max(0, self.limit - await self.used(user))

    async def quota(self, user: Any, mode: str | None = None) -> bool | str:
        """Pass as ``AskPanelConfig(quota=cap.quota)``."""
        if await self.used(user) < self.limit:
            return True
        return self.message.format(limit=self.limit)

    async def on_turn(self, user: Any, mode: str, usage: Usage | None) -> None:
        """Pass as ``AskPanelConfig(on_turn=cap.on_turn)``. Chain your own logging after it."""
        if usage is None and not self.count_failed:
            return
        await self._call(self.counter.incr, self.key(user), self.today())

    # Allow ``quota=cap`` directly as a convenience.
    async def __call__(self, user: Any, mode: str | None = None) -> bool | str:
        return await self.quota(user, mode)


__all__ = ["DailyTurnCap", "MemoryCounter", "TurnCounter", "default_key", "DEFAULT_MESSAGE"]
