"""
SQLite-backed user store. Persists across restarts.
Drop-in replacement for the original in-memory UserStore.
"""
from __future__ import annotations

import asyncio
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

from auth.models import Role, User, UserUpdate
from auth.jwt_handler import hash_password

_DB_PATH = Path(__file__).parent.parent / "data" / "opsbrain.db"


def _ensure_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                email         TEXT,
                full_name     TEXT,
                role          TEXT NOT NULL DEFAULT 'viewer',
                hashed_password TEXT NOT NULL,
                team          TEXT,
                disabled      INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Seed admin if table is empty
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO users (id, username, email, full_name, role, hashed_password, team) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), "admin", "admin@opsbrain.local", "OpsBrain Admin",
                 "admin", hash_password("admin123"), "platform"),
            )


_ensure_db()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"] or "",
        full_name=row["full_name"] or "",
        role=Role(row["role"]),
        hashed_password=row["hashed_password"],
        team=row["team"] or "",
        disabled=bool(row["disabled"]),
    )


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


class UserStore:
    # All public methods are synchronous because the auth router calls them
    # on the main thread. For high-throughput use, wrap with asyncio.to_thread.

    def get_by_username(self, username: str) -> Optional[User]:
        with _conn() as c:
            row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return _row_to_user(row) if row else None

    def get_by_id(self, user_id: str) -> Optional[User]:
        with _conn() as c:
            row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return _row_to_user(row) if row else None

    def list_users(self) -> list[User]:
        with _conn() as c:
            rows = c.execute("SELECT * FROM users ORDER BY username").fetchall()
            return [_row_to_user(r) for r in rows]

    def add(self, user: User) -> None:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (id, username, email, full_name, role, hashed_password, team, disabled) VALUES (?,?,?,?,?,?,?,?)",
                (user.id, user.username, user.email, user.full_name,
                 user.role.value, user.hashed_password, user.team, int(user.disabled)),
            )

    def update(self, user_id: str, update: UserUpdate) -> None:
        patch = update.model_dump(exclude_none=True)
        if not patch:
            return
        cols = ", ".join(f"{k} = ?" for k in patch)
        vals = list(patch.values()) + [user_id]
        with _conn() as c:
            c.execute(f"UPDATE users SET {cols} WHERE id = ?", vals)

    def delete(self, user_id: str) -> bool:
        with _conn() as c:
            cur = c.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0


user_store = UserStore()
