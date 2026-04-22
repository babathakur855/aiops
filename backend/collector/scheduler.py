"""
Background collection scheduler.
Runs as an asyncio task inside the FastAPI app — no separate process needed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

COLLECTION_INTERVAL_SECONDS = 300  # 5 minutes default
_task: asyncio.Task | None = None


async def _run_forever(interval: int) -> None:
    from collector.cloud_poller import collect_all
    while True:
        try:
            log.info("Collection cycle starting…")
            summary = await collect_all()
            total = sum(r.get("collected", 0) for r in summary.get("results", []))
            log.info("Collection cycle complete — %d metrics across %d sources",
                     total, summary.get("total_sources", 0))
        except Exception as e:
            log.warning("Collection cycle error: %s", e)
        await asyncio.sleep(interval)


def start(interval_seconds: int = COLLECTION_INTERVAL_SECONDS) -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run_forever(interval_seconds))
    log.info("Collector scheduler started — interval: %ds", interval_seconds)


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        log.info("Collector scheduler stopped")


def is_running() -> bool:
    return _task is not None and not _task.done()


async def run_now() -> dict:
    """Trigger an immediate collection cycle (for the API endpoint)."""
    from collector.cloud_poller import collect_all
    return await collect_all()
