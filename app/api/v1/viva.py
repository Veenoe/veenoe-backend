"""
This module defines the API endpoints for version 1 of the 'viva' resource.

The endpoints expose CRUD and workflow operations for viva sessions, including:
    - Starting a new viva
    - Concluding and scoring a viva
    - Fetching user history
    - Retrieving session details
    - Renaming a session
    - Deleting a session

Each route interacts with the VivaService layer, ensuring separation of concerns
between API transport logic and business logic.

AUTHENTICATION:
All endpoints require authentication. User identity is extracted from the JWT
token, not from request parameters. This ensures:
1. Users can only access their own data
2. User ID cannot be spoofed by clients
3. Consistent security model across all endpoints

SECURITY (First Principles):
1. Input validation at the API layer (fail fast)
2. Generic error messages to clients (no internal data leaks)
3. Full error logging server-side for debugging
"""

import logging
from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends, status, Path, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.schemas.viva import (
    VivaStartRequest,
    VivaStartResponse,
    ConcludeVivaRequest,
    ConcludeVivaResponse,
    HistoryResponse,
    RenameSessionRequest,
    VivaSessionDetailResponse,
)
from app.api.deps import get_viva_service, CurrentUser
from app.services.viva_service import VivaService

logger = logging.getLogger(__name__)

# Rate limiter instance (uses same key_func as main app)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

# ---------------------------------------------------------------------------
# Common Path Parameter Validation
# ---------------------------------------------------------------------------
# MongoDB ObjectId is 24 hex characters. Validate at API layer to fail fast.
SessionIdPath = Annotated[
    str,
    Path(
        min_length=24,
        max_length=24,
        pattern=r"^[a-fA-F0-9]{24}$",
        description="MongoDB ObjectId (24 hex characters)",
        examples=["507f1f77bcf86cd799439011"],
    ),
]


@router.post("/start", response_model=VivaStartResponse)
@limiter.limit("5/minute")  # Protect Gemini API quota
async def start_viva(
    request: Request,  # Required by SlowAPI
    viva_request: VivaStartRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Start a new viva session.

    AUTHENTICATION REQUIRED: The user_id is extracted from the JWT token,
    not from the request body.

    Args:
        request: FastAPI Request object (required by SlowAPI)
        viva_request: Session metadata (topic, class level, student name)
        service: Injected VivaService
        current_user: Authenticated user from JWT

    Returns:
        VivaStartResponse: Session ID and AI connection parameters
    """
    try:
        response_data = await service.start_new_viva_session(
            viva_request=viva_request,
            user_id=current_user.user_id,
        )
        return VivaStartResponse(**response_data)
    except Exception as e:
        # Log full error server-side for debugging
        logger.exception(
            "Error starting viva for user %s: %s",
            current_user.user_id,
            str(e),
        )
        # Return generic message to client (no internal details)
        raise HTTPException(
            status_code=500,
            detail="Failed to start session. Please try again.",
        )


@router.post("/conclude-viva", response_model=ConcludeVivaResponse)
async def conclude_viva(
    request: ConcludeVivaRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Conclude an active viva session and generate structured feedback.

    AUTHENTICATION REQUIRED. Only the session owner can conclude.
    """
    try:
        result = await service.conclude_viva_session(
            viva_session_id=request.viva_session_id,
            score=request.score,
            summary=request.summary,
            strong_points=request.strong_points,
            areas_of_improvement=request.areas_of_improvement,
            user_id=current_user.user_id,
        )
        return ConcludeVivaResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(
            "Error concluding viva %s for user %s",
            request.viva_session_id,
            current_user.user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to conclude session. Please try again.",
        )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Retrieve the complete viva history for the authenticated user.

    AUTHENTICATION REQUIRED. User ID comes from JWT, not URL parameter.
    This is more secure than /history/{user_id}.

    Returns:
        HistoryResponse: List of session summaries for the authenticated user
    """
    try:
        sessions = await service.get_user_history(current_user.user_id)
        return HistoryResponse(sessions=sessions)
    except Exception as e:
        logger.exception("Error fetching history for user %s", current_user.user_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch history. Please try again.",
        )


@router.get("/{session_id}", response_model=VivaSessionDetailResponse)
async def get_session_details(
    session_id: SessionIdPath,
    service: Annotated[VivaService, Depends(get_viva_service)],
):
    """
    Retrieve full details for a specific viva session.

    PUBLIC ENDPOINT - No authentication required.
    This allows users to share session URLs with others.
    """
    try:
        return await service.get_viva_session_details(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error fetching session details for %s", session_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch session details. Please try again.",
        )


@router.patch("/{session_id}/rename")
async def rename_session_endpoint(
    session_id: SessionIdPath,
    request: RenameSessionRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Rename an existing viva session.

    AUTHENTICATION REQUIRED. Only the session owner can rename.
    """
    try:
        return await service.rename_session(
            session_id=session_id,
            new_title=request.new_title,
            user_id=current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(
            "Error renaming session %s for user %s",
            session_id,
            current_user.user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to rename session. Please try again.",
        )


@router.delete("/{session_id}")
async def delete_session_endpoint(
    session_id: SessionIdPath,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Permanently delete a viva session.

    AUTHENTICATION REQUIRED. Only the session owner can delete.
    """
    try:
        return await service.delete_session(
            session_id=session_id,
            user_id=current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(
            "Error deleting session %s for user %s",
            session_id,
            current_user.user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to delete session. Please try again.",
        )
