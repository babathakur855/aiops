"""
Knowledge Set persistence — groups exactly one SOP + one template + N context docs
into a named, reusable bundle that gets assigned to a checkout.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from knowledge.set_models import KnowledgeSet, KnowledgeSetCreate, KnowledgeSetUpdate

_DB_PATH = Path(__file__).parent.parent / "data" / "opsbrain.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_sets (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                description      TEXT DEFAULT '',
                checkout_types   TEXT NOT NULL DEFAULT '[]',
                sop_doc_id       TEXT,
                template_doc_id  TEXT,
                context_doc_ids  TEXT NOT NULL DEFAULT '[]',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                is_default       INTEGER NOT NULL DEFAULT 0
            )
        """)
        # safe migration: add knowledge_set_id to checkouts if missing
        try:
            c.execute("ALTER TABLE checkouts ADD COLUMN knowledge_set_id TEXT")
        except Exception:
            pass


def _denorm_doc_name(doc_id: str | None) -> str | None:
    """Look up doc name for display — called only when building response."""
    if not doc_id:
        return None
    with _conn() as c:
        row = c.execute("SELECT name FROM knowledge_docs WHERE id=?", (doc_id,)).fetchone()
    return row["name"] if row else f"(deleted: {doc_id[:8]})"


def _denorm_doc_names(doc_ids: list[str]) -> list[str]:
    if not doc_ids:
        return []
    placeholders = ",".join("?" * len(doc_ids))
    with _conn() as c:
        rows = c.execute(f"SELECT id, name FROM knowledge_docs WHERE id IN ({placeholders})", doc_ids).fetchall()
    name_map = {r["id"]: r["name"] for r in rows}
    return [name_map.get(d, f"(deleted: {d[:8]})") for d in doc_ids]


def _row_to_set(row: sqlite3.Row) -> KnowledgeSet:
    sop_id      = row["sop_doc_id"]
    tpl_id      = row["template_doc_id"]
    ctx_ids     = json.loads(row["context_doc_ids"] or "[]")
    return KnowledgeSet(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        checkout_types=json.loads(row["checkout_types"] or "[]"),
        sop_doc_id=sop_id,
        sop_doc_name=_denorm_doc_name(sop_id),
        template_doc_id=tpl_id,
        template_doc_name=_denorm_doc_name(tpl_id),
        context_doc_ids=ctx_ids,
        context_doc_names=_denorm_doc_names(ctx_ids),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        is_default=bool(row["is_default"]),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_sets(checkout_type: str | None = None) -> list[KnowledgeSet]:
    with _conn() as c:
        if checkout_type:
            rows = c.execute(
                "SELECT * FROM knowledge_sets WHERE checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%' ORDER BY is_default DESC, name",
                (f'%"{checkout_type}"%',),
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM knowledge_sets ORDER BY is_default DESC, name").fetchall()
    return [_row_to_set(r) for r in rows]


def get_set(set_id: str) -> KnowledgeSet | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM knowledge_sets WHERE id=?", (set_id,)).fetchone()
    return _row_to_set(row) if row else None


def get_default_set_for_type(checkout_type: str) -> KnowledgeSet | None:
    """Return the default set for this checkout type, or None."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM knowledge_sets WHERE is_default=1 AND (checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%') LIMIT 1",
            (f'%"{checkout_type}"%',),
        ).fetchone()
        if not row:
            row = c.execute(
                "SELECT * FROM knowledge_sets WHERE checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%' ORDER BY created_at DESC LIMIT 1",
                (f'%"{checkout_type}"%',),
            ).fetchone()
    return _row_to_set(row) if row else None


def get_set_for_checkout(checkout_id: str) -> KnowledgeSet | None:
    """Return the explicitly assigned set for a specific checkout."""
    with _conn() as c:
        row = c.execute("SELECT knowledge_set_id FROM checkouts WHERE id=?", (checkout_id,)).fetchone()
        if not row or not row["knowledge_set_id"]:
            return None
        return get_set(row["knowledge_set_id"])


def create_set(data: KnowledgeSetCreate) -> KnowledgeSet:
    now = datetime.now(timezone.utc).isoformat()
    sid = str(uuid.uuid4())
    with _conn() as c:
        c.execute("""
            INSERT INTO knowledge_sets
            (id,name,description,checkout_types,sop_doc_id,template_doc_id,context_doc_ids,created_at,updated_at,is_default)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            sid, data.name, data.description,
            json.dumps(data.checkout_types),
            data.sop_doc_id, data.template_doc_id,
            json.dumps(data.context_doc_ids),
            now, now, int(data.is_default),
        ))
    return get_set(sid)  # type: ignore


def update_set(set_id: str, patch: KnowledgeSetUpdate) -> KnowledgeSet | None:
    p = patch.model_dump(exclude_none=True)
    if not p:
        return get_set(set_id)
    if "checkout_types" in p:
        p["checkout_types"] = json.dumps(p["checkout_types"])
    if "context_doc_ids" in p:
        p["context_doc_ids"] = json.dumps(p["context_doc_ids"])
    if "is_default" in p:
        p["is_default"] = int(p["is_default"])
    p["updated_at"] = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(f"{k}=?" for k in p)
    with _conn() as c:
        c.execute(f"UPDATE knowledge_sets SET {cols} WHERE id=?", list(p.values()) + [set_id])
    return get_set(set_id)


def delete_set(set_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM knowledge_sets WHERE id=?", (set_id,))
    return cur.rowcount > 0


def assign_set_to_checkout(checkout_id: str, set_id: str | None) -> None:
    """Attach (or detach) a knowledge set to a specific checkout."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("UPDATE checkouts SET knowledge_set_id=?, updated_at=? WHERE id=?",
                  (set_id, now, checkout_id))


def resolve_set(checkout) -> KnowledgeSet | None:
    """
    Find the right knowledge set for a checkout run.
    Priority:
      1. Checkout has an explicitly assigned set  → use it
      2. A default set exists for this checkout type → use it
      3. No set found → fall back to type-based doc query (legacy)
    """
    explicit = get_set_for_checkout(checkout.id) if hasattr(checkout, "id") else None
    if explicit:
        return explicit
    ks_id = getattr(checkout, "knowledge_set_id", None)
    if ks_id:
        return get_set(ks_id)
    return get_default_set_for_type(checkout.checkout_type)
