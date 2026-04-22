"""
SQLite persistence for checkout configurations and run history.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from checkouts.models import (
    Checkout, CheckoutCreate, CheckoutStatus, CheckoutUpdate, RunHistory,
)

_DB_PATH = Path(__file__).parent.parent / "data" / "opsbrain.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


# ── Next-run calculation (respects scheduled time) ────────────────────────────

def compute_next_run(
    frequency: str,
    scheduled_hour: int,
    scheduled_weekday: int,
    scheduled_day: int,
    after: datetime | None = None,
) -> datetime:
    """Return the next UTC datetime this checkout should run."""
    now = after or datetime.now(timezone.utc)

    if frequency == "daily":
        candidate = now.replace(hour=scheduled_hour, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "weekly":
        # scheduled_weekday: 0=Mon … 6=Sun
        days_ahead = scheduled_weekday - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.hour >= scheduled_hour):
            days_ahead += 7
        base = now + timedelta(days=days_ahead)
        return base.replace(hour=scheduled_hour, minute=0, second=0, microsecond=0)

    if frequency == "monthly":
        dom = min(scheduled_day, 28)
        candidate = now.replace(day=dom, hour=scheduled_hour, minute=0, second=0, microsecond=0)
        if candidate <= now:
            m = now.month % 12 + 1
            y = now.year + (1 if now.month == 12 else 0)
            candidate = candidate.replace(year=y, month=m)
        return candidate

    if frequency == "quarterly":
        # First day of the next quarter
        q_start_months = [1, 4, 7, 10]
        current_q_start = max(m for m in q_start_months if m <= now.month)
        next_q_idx = (q_start_months.index(current_q_start) + 1) % 4
        next_q_month = q_start_months[next_q_idx]
        next_q_year = now.year + (1 if next_q_month < now.month else 0)
        return datetime(next_q_year, next_q_month, min(scheduled_day, 28),
                        scheduled_hour, 0, 0, tzinfo=timezone.utc)

    if frequency == "half-yearly":
        months_ahead = 6
        m = (now.month - 1 + months_ahead) % 12 + 1
        y = now.year + ((now.month - 1 + months_ahead) // 12)
        return datetime(y, m, min(scheduled_day, 28), scheduled_hour, 0, 0, tzinfo=timezone.utc)

    # yearly
    return datetime(now.year + 1, now.month, min(scheduled_day, 28),
                    scheduled_hour, 0, 0, tzinfo=timezone.utc)


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS checkouts (
                id                TEXT PRIMARY KEY,
                name              TEXT NOT NULL,
                description       TEXT DEFAULT '',
                checkout_type     TEXT NOT NULL,
                frequency         TEXT NOT NULL,
                scheduled_hour    INTEGER NOT NULL DEFAULT 9,
                scheduled_weekday INTEGER NOT NULL DEFAULT 1,
                scheduled_day     INTEGER NOT NULL DEFAULT 1,
                enabled           INTEGER NOT NULL DEFAULT 1,
                custom_prompt     TEXT DEFAULT '',
                audience_emails   TEXT DEFAULT '[]',
                audience_slack    TEXT DEFAULT '[]',
                report_format     TEXT DEFAULT 'markdown',
                namespace         TEXT DEFAULT 'production',
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                last_run_at       TEXT,
                next_run_at       TEXT,
                last_status       TEXT DEFAULT 'pending',
                last_summary      TEXT DEFAULT '',
                run_count         INTEGER DEFAULT 0,
                is_compiled       INTEGER NOT NULL DEFAULT 0,
                compiled_at       TEXT,
                execution_plan    TEXT,
                tokens_saved_pct  INTEGER DEFAULT 0
            )
        """)
        # Safe column migrations for existing tables
        for col, defval in [
            ("scheduled_hour",    "9"),
            ("scheduled_weekday", "1"),
            ("scheduled_day",     "1"),
            ("is_compiled",       "0"),
            ("compiled_at",       "NULL"),
            ("execution_plan",    "NULL"),
            ("tokens_saved_pct",  "0"),
        ]:
            try:
                c.execute(f"ALTER TABLE checkouts ADD COLUMN {col} INTEGER NOT NULL DEFAULT {defval}")
            except Exception:
                pass  # column already exists

        c.execute("""
            CREATE TABLE IF NOT EXISTS checkout_runs (
                id               TEXT PRIMARY KEY,
                checkout_id      TEXT NOT NULL,
                checkout_name    TEXT NOT NULL,
                checkout_type    TEXT NOT NULL,
                started_at       TEXT NOT NULL,
                completed_at     TEXT,
                status           TEXT NOT NULL,
                summary          TEXT DEFAULT '',
                full_report      TEXT DEFAULT '',
                duration_seconds REAL,
                triggered_by     TEXT DEFAULT 'scheduler',
                error            TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_runs_checkout ON checkout_runs(checkout_id, started_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_checkouts_next ON checkouts(next_run_at, enabled)")


def _row_to_checkout(row: sqlite3.Row) -> Checkout:
    return Checkout(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        checkout_type=row["checkout_type"],
        frequency=row["frequency"],
        scheduled_hour=row["scheduled_hour"] if "scheduled_hour" in row.keys() else 9,
        scheduled_weekday=row["scheduled_weekday"] if "scheduled_weekday" in row.keys() else 1,
        scheduled_day=row["scheduled_day"] if "scheduled_day" in row.keys() else 1,
        enabled=bool(row["enabled"]),
        custom_prompt=row["custom_prompt"] or "",
        audience_emails=json.loads(row["audience_emails"] or "[]"),
        audience_slack=json.loads(row["audience_slack"] or "[]"),
        report_format=row["report_format"] or "markdown",
        namespace=row["namespace"] or "production",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_run_at=row["last_run_at"],
        next_run_at=row["next_run_at"],
        last_status=CheckoutStatus(row["last_status"] or "pending"),
        last_summary=row["last_summary"] or "",
        run_count=row["run_count"] or 0,
        knowledge_set_id=row["knowledge_set_id"] if "knowledge_set_id" in row.keys() else None,
        is_compiled=bool(row["is_compiled"]) if "is_compiled" in row.keys() else False,
        compiled_at=row["compiled_at"] if "compiled_at" in row.keys() else None,
        execution_plan=json.loads(row["execution_plan"]) if row["execution_plan"] else None
            if "execution_plan" in row.keys() else None,
        tokens_saved_pct=row["tokens_saved_pct"] if "tokens_saved_pct" in row.keys() else 0,
    )


def _row_to_run(row: sqlite3.Row) -> RunHistory:
    return RunHistory(
        id=row["id"],
        checkout_id=row["checkout_id"],
        checkout_name=row["checkout_name"],
        checkout_type=row["checkout_type"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        status=CheckoutStatus(row["status"]),
        summary=row["summary"] or "",
        full_report=row["full_report"] or "",
        duration_seconds=row["duration_seconds"],
        triggered_by=row["triggered_by"] or "scheduler",
        error=row["error"],
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_checkouts() -> list[Checkout]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM checkouts ORDER BY created_at DESC").fetchall()
    return [_row_to_checkout(r) for r in rows]


def get_checkout(checkout_id: str) -> Checkout | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM checkouts WHERE id = ?", (checkout_id,)).fetchone()
    return _row_to_checkout(row) if row else None


def create_checkout(data: CheckoutCreate) -> Checkout:
    now = datetime.now(timezone.utc)
    cid = str(uuid.uuid4())
    next_run = compute_next_run(
        data.frequency, data.scheduled_hour,
        data.scheduled_weekday, data.scheduled_day,
    )
    with _conn() as c:
        c.execute("""
            INSERT INTO checkouts
            (id, name, description, checkout_type, frequency,
             scheduled_hour, scheduled_weekday, scheduled_day,
             enabled, custom_prompt, audience_emails, audience_slack,
             report_format, namespace, created_at, updated_at, next_run_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cid, data.name, data.description,
            data.checkout_type.value, data.frequency.value,
            data.scheduled_hour, data.scheduled_weekday, data.scheduled_day,
            int(data.enabled), data.custom_prompt,
            json.dumps(data.audience_emails), json.dumps(data.audience_slack),
            data.report_format, data.namespace,
            now.isoformat(), now.isoformat(), next_run.isoformat(),
        ))
    return get_checkout(cid)  # type: ignore


def update_checkout(checkout_id: str, patch: dict) -> Checkout | None:
    if not patch:
        return get_checkout(checkout_id)
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    for field in ("audience_emails", "audience_slack"):
        if field in patch and isinstance(patch[field], list):
            patch[field] = json.dumps(patch[field])
    # Recompute next_run if schedule fields changed
    schedule_fields = {"frequency", "scheduled_hour", "scheduled_weekday", "scheduled_day"}
    if schedule_fields & set(patch.keys()):
        existing = get_checkout(checkout_id)
        if existing:
            next_run = compute_next_run(
                patch.get("frequency", existing.frequency),
                patch.get("scheduled_hour", existing.scheduled_hour),
                patch.get("scheduled_weekday", existing.scheduled_weekday),
                patch.get("scheduled_day", existing.scheduled_day),
            )
            patch["next_run_at"] = next_run.isoformat()
    cols = ", ".join(f"{k} = ?" for k in patch)
    vals = list(patch.values()) + [checkout_id]
    with _conn() as c:
        c.execute(f"UPDATE checkouts SET {cols} WHERE id = ?", vals)
    return get_checkout(checkout_id)


def delete_checkout(checkout_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM checkouts WHERE id = ?", (checkout_id,))
        c.execute("DELETE FROM checkout_runs WHERE checkout_id = ?", (checkout_id,))
    return cur.rowcount > 0


def get_due_checkouts() -> list[Checkout]:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM checkouts WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?",
            (now,),
        ).fetchall()
    return [_row_to_checkout(r) for r in rows]


# ── Run history ───────────────────────────────────────────────────────────────

def save_run(run: RunHistory) -> None:
    with _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO checkout_runs
            (id, checkout_id, checkout_name, checkout_type, started_at, completed_at,
             status, summary, full_report, duration_seconds, triggered_by, error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run.id, run.checkout_id, run.checkout_name, run.checkout_type,
            run.started_at, run.completed_at, run.status.value,
            run.summary, run.full_report, run.duration_seconds,
            run.triggered_by, run.error,
        ))


def update_checkout_after_run(
    checkout_id: str,
    status: CheckoutStatus,
    summary: str,
    next_run_at: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("""
            UPDATE checkouts
            SET last_run_at = ?, next_run_at = ?, last_status = ?,
                last_summary = ?, run_count = run_count + 1, updated_at = ?
            WHERE id = ?
        """, (now, next_run_at, status.value, summary, now, checkout_id))


def list_runs(checkout_id: str, limit: int = 20) -> list[RunHistory]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM checkout_runs WHERE checkout_id = ? ORDER BY started_at DESC LIMIT ?",
            (checkout_id, limit),
        ).fetchall()
    return [_row_to_run(r) for r in rows]


def list_recent_runs(limit: int = 50) -> list[RunHistory]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM checkout_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_run(r) for r in rows]


def save_plan(checkout_id: str, plan_dict: dict, tokens_saved_pct: int) -> None:
    """Store the compiled execution plan on the checkout record."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("""
            UPDATE checkouts
            SET is_compiled=1, compiled_at=?, execution_plan=?, tokens_saved_pct=?, updated_at=?
            WHERE id=?
        """, (now, json.dumps(plan_dict), tokens_saved_pct, now, checkout_id))


def clear_plan(checkout_id: str) -> None:
    """Remove a compiled plan so the next run recompiles from SOPs."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("""
            UPDATE checkouts SET is_compiled=0, compiled_at=NULL, execution_plan=NULL, updated_at=?
            WHERE id=?
        """, (now, checkout_id))


def get_stats() -> dict:
    with _conn() as c:
        total   = c.execute("SELECT COUNT(*) FROM checkouts WHERE enabled=1").fetchone()[0]
        passed  = c.execute("SELECT COUNT(*) FROM checkouts WHERE last_status='passed'").fetchone()[0]
        warning = c.execute("SELECT COUNT(*) FROM checkouts WHERE last_status='warning'").fetchone()[0]
        failed  = c.execute("SELECT COUNT(*) FROM checkouts WHERE last_status='failed'").fetchone()[0]
        now = datetime.now(timezone.utc).isoformat()
        tomorrow = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        due_today = c.execute(
            "SELECT COUNT(*) FROM checkouts WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at <= ?",
            (tomorrow,),
        ).fetchone()[0]
    return {"total": total, "passed": passed, "warning": warning, "failed": failed, "due_today": due_today}
