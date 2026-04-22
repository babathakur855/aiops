"""
SQLite-backed knowledge base.  Documents (SOPs, templates, context) are stored
as text in the DB so they are always queryable.  The data/knowledge/ folder is
used only for uploaded binary originals.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from knowledge.models import DocType, KnowledgeDoc, KnowledgeDocCreate, KnowledgeDocUpdate

_DB_PATH    = Path(__file__).parent.parent / "data" / "opsbrain.db"
_FILES_DIR  = Path(__file__).parent.parent / "data" / "knowledge"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    _FILES_DIR.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_docs (
                id             TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                doc_type       TEXT NOT NULL,
                checkout_types TEXT NOT NULL DEFAULT '["*"]',
                description    TEXT DEFAULT '',
                content        TEXT NOT NULL DEFAULT '',
                file_name      TEXT,
                file_size      INTEGER DEFAULT 0,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                is_default     INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_kb_type ON knowledge_docs(doc_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kb_checkout ON knowledge_docs(checkout_types)")


def _row(row: sqlite3.Row) -> KnowledgeDoc:
    return KnowledgeDoc(
        id=row["id"],
        name=row["name"],
        doc_type=DocType(row["doc_type"]),
        checkout_types=json.loads(row["checkout_types"] or '["*"]'),
        description=row["description"] or "",
        content=row["content"] or "",
        file_name=row["file_name"],
        file_size=row["file_size"] or 0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        is_default=bool(row["is_default"]),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_docs(doc_type: str | None = None, checkout_type: str | None = None) -> list[KnowledgeDoc]:
    with _conn() as c:
        if doc_type and checkout_type:
            rows = c.execute(
                "SELECT * FROM knowledge_docs WHERE doc_type=? AND (checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%') ORDER BY is_default DESC, name",
                (doc_type, f'%"{checkout_type}"%'),
            ).fetchall()
        elif doc_type:
            rows = c.execute(
                "SELECT * FROM knowledge_docs WHERE doc_type=? ORDER BY is_default DESC, name", (doc_type,)
            ).fetchall()
        elif checkout_type:
            rows = c.execute(
                "SELECT * FROM knowledge_docs WHERE checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%' ORDER BY is_default DESC, name",
                (f'%"{checkout_type}"%',),
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM knowledge_docs ORDER BY is_default DESC, doc_type, name").fetchall()
    return [_row(r) for r in rows]


def get_doc(doc_id: str) -> KnowledgeDoc | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM knowledge_docs WHERE id=?", (doc_id,)).fetchone()
    return _row(row) if row else None


def get_docs_for_checkout(checkout_type: str, doc_type: str | None = None) -> list[KnowledgeDoc]:
    """Return all docs applicable to a checkout type (type-specific + wildcard)."""
    with _conn() as c:
        if doc_type:
            rows = c.execute(
                "SELECT * FROM knowledge_docs WHERE doc_type=? AND (checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%') ORDER BY is_default DESC",
                (doc_type, f'%"{checkout_type}"%'),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM knowledge_docs WHERE checkout_types LIKE ? OR checkout_types LIKE '%\"*\"%' ORDER BY is_default DESC, doc_type",
                (f'%"{checkout_type}"%',),
            ).fetchall()
    return [_row(r) for r in rows]


def create_doc(data: KnowledgeDocCreate, file_name: str | None = None, is_default: bool = False) -> KnowledgeDoc:
    now = datetime.now(timezone.utc).isoformat()
    did = str(uuid.uuid4())
    with _conn() as c:
        c.execute("""
            INSERT INTO knowledge_docs (id,name,doc_type,checkout_types,description,content,file_name,file_size,created_at,updated_at,is_default)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            did, data.name, data.doc_type.value,
            json.dumps(data.checkout_types), data.description, data.content,
            file_name, len(data.content.encode()), now, now, int(is_default),
        ))
    return get_doc(did)  # type: ignore


def update_doc(doc_id: str, patch: KnowledgeDocUpdate) -> KnowledgeDoc | None:
    p = patch.model_dump(exclude_none=True)
    if not p:
        return get_doc(doc_id)
    if "checkout_types" in p:
        p["checkout_types"] = json.dumps(p["checkout_types"])
    if "doc_type" in p and hasattr(p["doc_type"], "value"):
        p["doc_type"] = p["doc_type"].value
    p["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "content" in p:
        p["file_size"] = len(p["content"].encode())
    cols = ", ".join(f"{k}=?" for k in p)
    with _conn() as c:
        c.execute(f"UPDATE knowledge_docs SET {cols} WHERE id=?", list(p.values()) + [doc_id])
    return get_doc(doc_id)


def delete_doc(doc_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM knowledge_docs WHERE id=?", (doc_id,))
    return cur.rowcount > 0


def doc_exists_by_name(name: str) -> bool:
    with _conn() as c:
        return bool(c.execute("SELECT 1 FROM knowledge_docs WHERE name=?", (name,)).fetchone())
