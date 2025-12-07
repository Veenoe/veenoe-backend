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
"""

from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends
from app.schemas.viva import (
    VivaStartRequest,
    VivaStartResponse,
    ConcludeVivaRequest,
    ConcludeVivaResponse,
    HistoryResponse,
    RenameSessionRequest,
    VivaSessionDetailResponse,
)
from app.api.deps import get_viva_service
from app.services.viva_service import VivaService

router = APIRouter()


@router.post("/start", response_model=VivaStartResponse)
async def start_viva(
    request: VivaStartRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
):
    """
    Start a new viva session.

    This endpoint initializes a new viva session for a student based on the provided
    request parameters. It delegates the creation logic to the VivaService.

    Args:
        request (VivaStartRequest):
            Contains session metadata such as topic, class level, and student name.
        service (VivaService):
            Injected service responsible for viva session lifecycle operations.

    Returns:
        VivaStartResponse: The newly created viva session details including session ID
                           and ephemeral token (if applicable).

    Raises:
        HTTPException (500): If any unexpected error occurs during session creation.
    """
    try:
        response_data = await service.start_new_viva_session(request)
        return VivaStartResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting viva: {str(e)}")


@router.post("/conclude-viva", response_model=ConcludeVivaResponse)
async def conclude_viva(
    request: ConcludeVivaRequest,
    service: Annotated[VivaService, Depends(get_viva_service)],
):
    """
    Conclude an active viva session and generate structured feedback.

    This endpoint finalizes the viva by storing the student's score, summary,
    strong points, and improvement areas. Upon completion, the service updates the
    session status to "completed" and attaches the generated feedback.

    Args:
        request (ConcludeVivaRequest):
            Includes score, summary, strengths, and improvement areas.
        service (VivaService):
            The viva service handling session conclusion logic.

    Returns:
        ConcludeVivaResponse: Contains updated session information and stored feedback.

    Raises:
        HTTPException (500): For unexpected errors during conclusion.
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


@router.get("/history/{user_id}", response_model=HistoryResponse)
async def get_history(
    user_id: str,
    service: Annotated[VivaService, Depends(get_viva_service)],
):
    """
    Retrieve the complete viva history for a given user.

    This endpoint returns all viva sessions associated with the provided user ID.
    Results are typically displayed in the user's dashboard or activity history.

    Args:
        user_id (str):
            The Clerk user identifier used to query sessions.
        service (VivaService):
            The service responsible for fetching session history.

    Returns:
        HistoryResponse: A list of session summaries for the user.

    Raises:
        HTTPException (500): If there is an unexpected failure retrieving history.
    """
    try:
        sessions = await service.get_user_history(user_id)
        return HistoryResponse(sessions=sessions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching history: {str(e)}")


@router.get("/{session_id}", response_model=VivaSessionDetailResponse)
async def get_session_details(
    session_id: str,
    service: Annotated[VivaService, Depends(get_viva_service)],
):
    """
    Retrieve full details for a specific viva session.

    This endpoint is used primarily for the results or analytics page, allowing
    the client to display complete session metadata and feedback.

    Args:
        session_id (str):
            Unique ID of the viva session to fetch.
        service (VivaService):
            The service providing session retrieval logic.

    Returns:
        VivaSessionDetailResponse: Comprehensive session details.

    Raises:
        HTTPException (404): If the session does not exist.
        HTTPException (500): For unexpected errors during lookup.
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
):
    """
    Rename an existing viva session.

    Args:
        session_id (str):
            The session to rename.
        request (RenameSessionRequest):
            Contains the new session title.
        service (VivaService):
            Service handling session updates.

    Returns:
        dict: Updated session metadata after renaming.

    Raises:
        HTTPException (404): If the session does not exist.
        HTTPException (500): If renaming fails unexpectedly.
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
):
    """
    Permanently delete a viva session.

    Args:
        session_id (str):
            ID of the session to delete.
        service (VivaService):
            Service responsible for deletion operations.

    Returns:
        dict: Confirmation message or deletion metadata.

    Raises:
        HTTPException (404): If the session is not found.
        HTTPException (500): For any other failure during deletion.
    """
    try:
        return await service.delete_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")