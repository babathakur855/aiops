"""
Enrollment token system for collector agents.
Each customer cluster gets a unique short-lived or long-lived token that:
  - Identifies the environment (env_id)
  - Controls what the collector is allowed to send
  - Can be revoked without redeploying the collector
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from jose import jwt, JWTError

from config.settings import settings

ALGORITHM = "HS256"
ENROLLMENT_PURPOSE = "collector_enrollment"


def generate_enrollment_token(
    env_id: str,
    env_name: str,
    created_by: str,
    expires_in_days: int = 3650,  # ~10 years — permanent by default
    capabilities: list[str] | None = None,
) -> dict[str, str]:
    """Generate a signed enrollment token for a new collector environment."""
    payload = {
        "purpose": ENROLLMENT_PURPOSE,
        "env_id": env_id,
        "env_name": env_name,
        "created_by": created_by,
        "capabilities": capabilities or ["metrics", "logs", "events"],
        "iat": int(time.time()),
        "exp": int(time.time()) + (expires_in_days * 86400),
        "jti": secrets.token_hex(8),  # unique token ID for revocation
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)
    return {
        "token": token,
        "env_id": env_id,
        "env_name": env_name,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat(),
        "capabilities": payload["capabilities"],
    }


def validate_enrollment_token(token: str) -> dict[str, Any]:
    """Validate and decode an enrollment token. Raises ValueError if invalid."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid enrollment token: {e}")

    if payload.get("purpose") != ENROLLMENT_PURPOSE:
        raise ValueError("Token is not an enrollment token")

    return payload


# ── In-memory enrollment registry ───────────────────────────────
# In production replace with Supabase/PostgreSQL

class EnrollmentRegistry:
    def __init__(self) -> None:
        self._enrollments: dict[str, dict] = {}  # env_id → enrollment record
        self._revoked_jtis: set[str] = set()

    def register(self, token_payload: dict) -> None:
        env_id = token_payload["env_id"]
        self._enrollments[env_id] = {
            **token_payload,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_seen": None,
            "data_points_received": 0,
            "status": "registered",
        }

    def heartbeat(self, env_id: str, data_points: int) -> None:
        if env_id in self._enrollments:
            self._enrollments[env_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
            self._enrollments[env_id]["data_points_received"] += data_points
            self._enrollments[env_id]["status"] = "active"

    def revoke(self, env_id: str) -> bool:
        if env_id in self._enrollments:
            jti = self._enrollments[env_id].get("jti", "")
            if jti:
                self._revoked_jtis.add(jti)
            self._enrollments[env_id]["status"] = "revoked"
            return True
        return False

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked_jtis

    def list_environments(self) -> list[dict]:
        return [
            {
                "env_id": v["env_id"],
                "env_name": v["env_name"],
                "status": v["status"],
                "first_seen": v["first_seen"],
                "last_seen": v["last_seen"],
                "data_points_received": v["data_points_received"],
                "capabilities": v.get("capabilities", []),
            }
            for v in self._enrollments.values()
        ]

    def get(self, env_id: str) -> dict | None:
        return self._enrollments.get(env_id)


enrollment_registry = EnrollmentRegistry()
