"""Shared controller network pacing across discovery and PDF hops."""

import asyncio
import time


class RequestPacer:
    def __init__(self, interval=1.1):
        if interval < 1:
            raise ValueError("Interval must be >=1s")
        self.interval, self.last = interval, 0
        self.lock = asyncio.Lock()
        self.starts = []

    async def wait(self):
        async with self.lock:
            await asyncio.sleep(max(0, self.interval - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            self.starts.append(time.time())
