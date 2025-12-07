"""
This module contains the core business logic for the Viva application.
"""

from app.db.models import VivaSession, VivaFeedback
from app.schemas.viva import VivaStartRequest
from app.services.gemini_service import create_ephemeral_token, MODEL_NAME
import datetime
from bson import ObjectId
from typing import List, Optional

# --- Main Service Functions ---

async def start_new_viva_session(viva_request: VivaStartRequest) -> dict:
    new_session = VivaSession(
        student_name=viva_request.student_name,
        user_id=viva_request.user_id,
        title=viva_request.topic,
        session_type=viva_request.session_type or "viva",
        topic=viva_request.topic,
        class_level=viva_request.class_level,
        started_at=datetime.datetime.now(tz=datetime.timezone.utc),
        status="in_progress",
    )
    await new_session.insert()

    token_data = await create_ephemeral_token(viva_request)

    return {
        "viva_session_id": str(new_session.id),
        "ephemeral_token": token_data["token"],
        "google_model": MODEL_NAME,
        "session_duration_minutes": token_data["session_duration_minutes"],
        "voice_name": token_data["voice_name"],
    }

async def conclude_viva_session(
    viva_session_id: str, 
    score: int, 
    summary: str, 
    strong_points: List[str], 
    areas_of_improvement: List[str]
) -> dict:
    session = await VivaSession.get(ObjectId(viva_session_id))
    if not session:
        raise ValueError(f"Viva session {viva_session_id} not found")

    feedback_data = VivaFeedback(
        score=score,
        summary=summary,
        strong_points=strong_points,
        areas_of_improvement=areas_of_improvement
    )

    session.feedback = feedback_data
    session.status = "completed"
    session.ended_at = datetime.datetime.now(tz=datetime.timezone.utc)
    
    await session.save()

    return {
        "status": "completed",
        "score": score,
        "final_feedback": summary,
    }

# --- NEW FUNCTION HERE ---
async def get_viva_session_details(session_id: str) -> dict:
    """
    Fetches full details of a specific viva session.
    """
    session = await VivaSession.get(ObjectId(session_id))
    if not session:
        raise ValueError(f"Viva session {session_id} not found")
        
    return {
        "viva_session_id": str(session.id),
        "student_name": session.student_name,
        "title": session.title,
        "topic": session.topic,
        "class_level": session.class_level,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": session.status,
        "feedback": session.feedback # Pydantic will serialize this automatically
    }

async def get_user_history(user_id: str) -> list[dict]:
    sessions = (
        await VivaSession.find(VivaSession.user_id == user_id)
        .sort(-VivaSession.started_at)
        .to_list()
    )

    history = []
    for session in sessions:
        history.append(
            {
                "viva_session_id": str(session.id),
                "title": session.title,
                "topic": session.topic,
                "class_level": session.class_level,
                "started_at": session.started_at,
                "session_type": session.session_type,
                "status": session.status,
            }
        )

    return history

async def rename_session(session_id: str, new_title: str) -> dict:
    session = await VivaSession.get(ObjectId(session_id))
    if not session:
        raise ValueError(f"Viva session {session_id} not found")

    session.title = new_title
    await session.save()
    return {"status": "success", "message": "Session renamed successfully"}

async def delete_session(session_id: str) -> dict:
    session = await VivaSession.get(ObjectId(session_id))
    if not session:
        raise ValueError(f"Viva session {session_id} not found")

    await session.delete()
    return {"status": "success", "message": "Session deleted successfully"}