import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    func: Callable[..., Coroutine[Any, Any, None]]
    interval_seconds: int
    last_run: datetime | None = field(default=None)
    enabled: bool = field(default=True)


class BackgroundScheduler:
    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def register(self, name: str, func: Callable[..., Coroutine[Any, Any, None]], interval_seconds: int) -> None:
        self._jobs.append(ScheduledJob(name=name, func=func, interval_seconds=interval_seconds))

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Background scheduler started with %d jobs", len(self._jobs))

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background scheduler stopped")

    async def _run_loop(self) -> None:
        while self._running:
            now = datetime.now(timezone.utc)
            for job in self._jobs:
                if not job.enabled:
                    continue
                if job.last_run is None or (now - job.last_run).total_seconds() >= job.interval_seconds:
                    try:
                        await job.func()
                        job.last_run = now
                        logger.info("Job '%s' completed", job.name)
                    except Exception:
                        logger.exception("Job '%s' failed", job.name)
            await asyncio.sleep(60)


scheduler = BackgroundScheduler()
