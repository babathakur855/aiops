from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt_handler import decode_token
from auth.models import Role, TokenData, ROLE_PERMISSIONS

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenData:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(*roles: Role):
    """Dependency factory — require one of the given roles."""
    async def dependency(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in roles and current_user.role != Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' does not have access. Required: {[r.value for r in roles]}",
            )
        return current_user
    return dependency


def has_permission(role: Role, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms or any(
        p.endswith(":*") and permission.startswith(p[:-1]) for p in perms
    )


# Convenience role guards
require_admin = require_roles(Role.ADMIN)
require_sre = require_roles(Role.ADMIN, Role.SRE)
require_finops = require_roles(Role.ADMIN, Role.FINOPS)
require_any = require_roles(Role.ADMIN, Role.SRE, Role.FINOPS, Role.VIEWER)
