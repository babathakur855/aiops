from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, EmailStr


class Role(str, Enum):
    ADMIN = "admin"      # Full access — manage users, connectors, all agents
    SRE = "sre"          # Incidents, K8s, chat, dashboard
    FINOPS = "finops"    # Cost analysis, dashboard, chat
    VIEWER = "viewer"    # Read-only dashboard and reports


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN:   {"*"},
    Role.SRE:     {"dashboard:read", "incidents:*", "k8s:*", "chat:*", "postmortem:*", "runbooks:*"},
    Role.FINOPS:  {"dashboard:read", "cost:*", "chat:*"},
    Role.VIEWER:  {"dashboard:read"},
}


class User(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: Role
    hashed_password: str
    active: bool = True
    team: str = ""


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    role: Role
    password: str
    team: str = ""


class UserUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = None
    team: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class TokenData(BaseModel):
    username: str
    role: Role
    user_id: str
