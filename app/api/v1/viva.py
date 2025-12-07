"""
This module defines the API endpoints for version 1 of the 'viva' resource.
"""

from fastapi import APIRouter, HTTPException
from app.schemas.viva import (
    VivaStartRequest,
    VivaStartResponse,
    ConcludeVivaRequest,
    ConcludeVivaResponse,
    HistoryResponse,
    RenameSessionRequest,
    VivaSessionDetailResponse, # Import the new schema
)
from app.services.viva_service import (
    start_new_viva_session,
    conclude_viva_session,
    get_user_history,
    rename_session,
    delete_session,
    get_viva_session_details, # Import the new service function
)

router = APIRouter()


@router.post("/start", response_model=VivaStartResponse)
async def start_viva(request: VivaStartRequest):
    try:
        response_data = await start_new_viva_session(request)
        return VivaStartResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting viva: {str(e)}")


@router.post("/conclude-viva", response_model=ConcludeVivaResponse)
async def conclude_viva(request: ConcludeVivaRequest):
    try:
        result = await conclude_viva_session(
            viva_session_id=request.viva_session_id,
            score=request.score,
            summary=request.summary,
            strong_points=request.strong_points,
            areas_of_improvement=request.areas_of_improvement
        )
        return ConcludeVivaResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error concluding viva: {str(e)}")


@router.get("/history/{user_id}", response_model=HistoryResponse)
async def get_history(user_id: str):
    try:
        sessions = await get_user_history(user_id)
        return HistoryResponse(sessions=sessions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching history: {str(e)}")


# --- NEW ENDPOINT TO FIX 405 ERROR ---
@router.get("/{session_id}", response_model=VivaSessionDetailResponse)
async def get_session_details(session_id: str):
    """
    Get full details for a specific session (used for the results page).
    """
    try:
        return await get_viva_session_details(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching session details: {str(e)}")


@router.patch("/{session_id}/rename")
async def rename_session_endpoint(session_id: str, request: RenameSessionRequest):
    try:
        return await rename_session(session_id, request.new_title)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming session: {str(e)}")


@router.delete("/{session_id}")
async def delete_session_endpoint(session_id: str):
    try:
        return await delete_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")