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
"""

from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends, status
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

router = APIRouter()


@router.post("/start", response_model=VivaStartResponse)
async def start_viva(
    request: VivaStartRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Start a new viva session.

    AUTHENTICATION REQUIRED: The user_id is extracted from the JWT token,
    not from the request body.

    Args:
        request: Session metadata (topic, class level, student name)
        service: Injected VivaService
        current_user: Authenticated user from JWT

    Returns:
        VivaStartResponse: Session ID and AI connection parameters
    """
    try:
        response_data = await service.start_new_viva_session(
            viva_request=request,
            authenticated_user_id=current_user.user_id,
        )
        return VivaStartResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting viva: {str(e)}")


@router.post("/conclude-viva", response_model=ConcludeVivaResponse)
async def conclude_viva(
    request: ConcludeVivaRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Conclude an active viva session and generate structured feedback.

    AUTHENTICATION REQUIRED.
    """
    try:
        result = await service.conclude_viva_session(
            viva_session_id=request.viva_session_id,
            score=request.score,
            summary=request.summary,
            strong_points=request.strong_points,
            areas_of_improvement=request.areas_of_improvement,
        )
        return ConcludeVivaResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error concluding viva: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Error fetching history: {str(e)}")


@router.get("/{session_id}", response_model=VivaSessionDetailResponse)
async def get_session_details(
    session_id: str,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Retrieve full details for a specific viva session.

    AUTHENTICATION REQUIRED.
    TODO: Add ownership validation to ensure user can only view their sessions.
    """
    try:
        return await service.get_viva_session_details(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching session details: {str(e)}"
        )


@router.patch("/{session_id}/rename")
async def rename_session_endpoint(
    session_id: str,
    request: RenameSessionRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Rename an existing viva session.

    AUTHENTICATION REQUIRED.
    TODO: Add ownership validation.
    """
    try:
        return await service.rename_session(session_id, request.new_title)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming session: {str(e)}")


@router.delete("/{session_id}")
async def delete_session_endpoint(
    session_id: str,
    service: Annotated[VivaService, Depends(get_viva_service)],
    current_user: CurrentUser,
):
    """
    Permanently delete a viva session.

    AUTHENTICATION REQUIRED.
    TODO: Add ownership validation.
    """
    try:
        return await service.delete_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")
