"""
Clerk authentication service using the official clerk-backend-api SDK.

This module provides authentication by verifying JWT tokens against Clerk's
backend API. It follows the official SDK pattern from the documentation:
https://github.com/clerk/clerk-sdk-python

Design Decisions:
1. Uses official SDK's `authenticate_request` method
2. Converts FastAPI Request to httpx.Request for SDK compatibility
3. Extracts user identity from JWT payload's `sub` claim
4. Single source of truth - never trust client-provided user_id
"""

import logging
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import httpx
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AuthenticatedUser:
    """
    Represents a verified, authenticated user from the JWT token.

    This is the single source of truth for user identity in the application.
    Never construct this manually - only from verified JWT tokens.

    Attributes:
        user_id: The Clerk user ID (from JWT 'sub' claim)
        email: User's email address (if available in token)
        session_id: Clerk session ID (if available)
    """

    user_id: str
    email: Optional[str] = None
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth Provider Protocol (Interface for swapping providers)
# ---------------------------------------------------------------------------
@runtime_checkable
class AuthProvider(Protocol):
    """
    Protocol defining the interface for authentication providers.

    This allows swapping Clerk for Firebase, Auth0, or custom auth
    without changing route handlers.
    """

    def verify_token(self, token: str) -> Optional[AuthenticatedUser]:
        """Verify a token and return user info, or None if invalid."""
        ...


# ---------------------------------------------------------------------------
# Clerk Auth Service Implementation
# ---------------------------------------------------------------------------
class ClerkAuthService:
    """
    Clerk authentication service using the official Python SDK.

    This service:
    1. Verifies JWT tokens using Clerk's JWKS
    2. Extracts user identity from the token's `sub` claim
    3. Caches nothing - each request is independently verified

    Usage:
        service = ClerkAuthService()
        user = service.verify_token(jwt_token)
        if user:
            print(f"Authenticated: {user.user_id}")
    """

    def __init__(self) -> None:
        """Initialize with Clerk secret key from settings."""
        self._secret_key = settings.CLERK_SECRET_KEY
        logger.info("ClerkAuthService initialized with official SDK")

    def verify_token(self, token: str) -> Optional[AuthenticatedUser]:
        """
        Verify a JWT token and extract user identity.

        Uses the official Clerk SDK's authenticate_request method.
        This validates the token's signature, expiration, and claims.

        Args:
            token: Raw JWT token string (without 'Bearer ' prefix)

        Returns:
            AuthenticatedUser if valid, None if invalid/expired
        """
        try:
            # Build httpx.Request for the SDK (it expects this format)
            request = httpx.Request(
                method="GET",
                url="https://api.example.com/",  # URL not used, just for request structure
                headers={"Authorization": f"Bearer {token}"},
            )

            # Use official SDK to authenticate
            request_state = authenticate_request(
                request,
                AuthenticateRequestOptions(
                    secret_key=self._secret_key,
                ),
            )

            if not request_state.is_signed_in:
                reason = getattr(request_state, "reason", "Unknown")
                logger.debug("Token verification failed: %s", reason)
                return None

            # Extract user data from payload
            payload = request_state.payload or {}
            user_id = payload.get("sub")

            if not user_id:
                logger.warning("Token valid but missing 'sub' claim")
                return None

            logger.debug("Authenticated user: %s", user_id)

            return AuthenticatedUser(
                user_id=user_id,
                email=payload.get("email"),
                session_id=payload.get("sid"),
            )

        except Exception as e:
            logger.debug("Token verification error: %s", str(e))
            return None


# ---------------------------------------------------------------------------
# Singleton Accessor (Thread-Safe)
# ---------------------------------------------------------------------------
from functools import lru_cache


@lru_cache(maxsize=1)
def get_auth_service() -> ClerkAuthService:
    """
    Get the singleton ClerkAuthService instance.

    Uses lru_cache for thread-safe lazy initialization.
    """
    return ClerkAuthService()
