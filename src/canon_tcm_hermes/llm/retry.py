from __future__ import annotations
import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
async def retry_async(fn: Callable[[], Awaitable[T]], attempts: int = 4, base_delay: float = 0.5) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await fn()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                await asyncio.sleep(base_delay * (2 ** i))
    assert last is not None
    raise last
