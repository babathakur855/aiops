"""
Background scheduler for automated checkout runs.
Checks every 60 s for due checkouts and executes them via Claude.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from core.claude_client import ClaudeClient

log = structlog.get_logger()

_task: asyncio.Task | None = None
_claude: "ClaudeClient | None" = None
_interval: int = 60


def configure(claude: "ClaudeClient") -> None:
    global _claude
    _claude = claude


def start(interval_seconds: int = 60) -> None:
    global _task, _interval
    _interval = interval_seconds
    if _task and not _task.done():
        return
    _task = asyncio.ensure_future(_run_forever())
    log.info("checkout_scheduler.started", interval_seconds=interval_seconds)


def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
    log.info("checkout_scheduler.stopped")


def is_running() -> bool:
    return _task is not None and not _task.done()


async def run_due_now() -> list[str]:
    """Immediately check for due checkouts and run them (useful for testing)."""
    return await _check_and_run()


async def _run_forever() -> None:
    while True:
        try:
            ran = await _check_and_run()
            if ran:
                log.info("checkout_scheduler.completed", count=len(ran), ids=ran)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.warning("checkout_scheduler.error", error=str(exc))
        await asyncio.sleep(_interval)


async def _check_and_run() -> list[str]:
    if _claude is None:
        return []
    from checkouts.store import get_due_checkouts
    from checkouts.runner import run_checkout

    due = get_due_checkouts()
    ran: list[str] = []
    for checkout in due:
        try:
            log.info("checkout_scheduler.running", name=checkout.name, id=checkout.id)
            await run_checkout(checkout, _claude, triggered_by="scheduler")
            ran.append(checkout.id)
        except Exception as exc:
            log.warning("checkout_scheduler.run_failed", id=checkout.id, error=str(exc))
    return ran
