"""
Authentication module for the Veenoe backend.

This module provides Clerk-based authentication using the official SDK.
All public interfaces are exported from this file for clean imports.

Usage:
    from app.core.auth import CurrentUser, OptionalUser, AuthenticatedUser

    @router.get("/protected")
    async def protected(user: CurrentUser):
        # user is guaranteed to be AuthenticatedUser
        return {"user_id": user.user_id}

Swapping Providers:
    To use a different auth provider (Firebase, Auth0, etc.):
    1. Create a new service implementing the verify_token method
    2. Update get_auth_service() in clerk.py
    3. No changes needed to routes - they use the same dependencies
"""

from .clerk import (
    AuthenticatedUser,
    AuthProvider,
    ClerkAuthService,
    get_auth_service,
)

from .dependencies import (
    CurrentUser,
    OptionalUser,
    get_current_user,
    get_current_user_optional,
)

__all__ = [
    # Data classes
    "AuthenticatedUser",
    # Protocols/Interfaces
    "AuthProvider",
    # Service
    "ClerkAuthService",
    "get_auth_service",
    # FastAPI Dependencies
    "CurrentUser",
    "OptionalUser",
    "get_current_user",
    "get_current_user_optional",
]
