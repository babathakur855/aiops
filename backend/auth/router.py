from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from auth.jwt_handler import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    hash_password,
    verify_password,
)
from auth.models import Role, TokenResponse, User, UserCreate, UserUpdate
from auth.rbac import get_current_user, require_admin, require_any
from auth.user_store import user_store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(username: str, password: str):
    user = user_store.get_by_username(username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token(user.username, user.role, user.id)
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"id": user.id, "username": user.username, "role": user.role, "full_name": user.full_name, "team": user.team},
    )


@router.get("/me")
async def get_me(current_user=Depends(get_current_user)):
    user = user_store.get_by_username(current_user.username)
    if not user:
        raise HTTPException(404, "User not found")
    return {"id": user.id, "username": user.username, "email": user.email,
            "full_name": user.full_name, "role": user.role, "team": user.team}


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users():
    return [
        {"id": u.id, "username": u.username, "email": u.email,
         "full_name": u.full_name, "role": u.role, "active": u.active, "team": u.team}
        for u in user_store.list_users()
    ]


@router.post("/users", dependencies=[Depends(require_admin)], status_code=201)
async def create_user(body: UserCreate):
    if user_store.get_by_username(body.username):
        raise HTTPException(400, "Username already exists")
    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        hashed_password=hash_password(body.password),
        team=body.team,
    )
    user_store.add(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.put("/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(user_id: str, body: UserUpdate):
    user = user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user_store.update(user_id, body)
    return {"status": "updated"}


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: str):
    if not user_store.delete(user_id):
        raise HTTPException(404, "User not found")
    return {"status": "deleted"}


@router.get("/roles")
async def list_roles(_=Depends(require_admin)):
    return {
        "roles": [
            {"name": "admin", "description": "Full access — manage users, connectors, all agents"},
            {"name": "sre", "description": "Incidents, K8s ops, chat, post-mortems, runbooks"},
            {"name": "finops", "description": "Cost analysis, optimization, chat"},
            {"name": "viewer", "description": "Read-only dashboard and reports"},
        ]
    }
