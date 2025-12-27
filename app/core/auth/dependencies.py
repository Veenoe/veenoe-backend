"""
FastAPI dependencies for authentication.

This module provides ready-to-use dependencies that can be added to
route handlers to require or optionally check authentication.

Usage:
    from app.core.auth import CurrentUser, OptionalUser

    @router.get("/protected")
    async def protected(user: CurrentUser):
        return {"user_id": user.user_id}

    @router.get("/public")
    async def public(user: OptionalUser):
        if user:
            return {"message": f"Hello {user.user_id}"}
        return {"message": "Hello guest"}
"""

import logging
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .clerk import AuthenticatedUser, get_auth_service

logger = logging.getLogger(__name__)

# Security scheme for OpenAPI docs (shows lock icon in Swagger UI)
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer_scheme)
    ],
) -> Optional[AuthenticatedUser]:
    """
    Get the current user if authenticated, None otherwise.

    Use this for routes that work for both authenticated and
    unauthenticated users (e.g., public content with personalization).

    Returns:
        AuthenticatedUser if valid token provided, None otherwise
    """
    if not credentials:
        return None

    auth_service = get_auth_service()
    user = auth_service.verify_token(credentials.credentials)

    if user:
        logger.debug("Authenticated: %s", user.user_id)

    return user


async def get_current_user(
    user: Annotated[Optional[AuthenticatedUser], Depends(get_current_user_optional)],
) -> AuthenticatedUser:
    """
    Require authentication for a route.

    Raises 401 Unauthorized if no valid token is provided.

    Returns:
        AuthenticatedUser (guaranteed non-None)

    Raises:
        HTTPException: 401 if not authenticated
    """
    if user is None:
        logger.debug("Auth required but no valid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "message": "Authentication required",
                "code": "AUTH_REQUIRED",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# Type aliases for clean route signatures
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
"""Required authenticated user. Route returns 401 if not authenticated."""

OptionalUser = Annotated[
    Optional[AuthenticatedUser], Depends(get_current_user_optional)
]
"""Optional authenticated user. None if not authenticated."""
