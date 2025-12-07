"""
This module contains the core business logic for the Viva application.

It follows dependency injection principles by accepting an LLMClient
implementation at runtime, making the service decoupled, testable,
and easy to extend when adding new LLM or model providers.
"""

import datetime
from bson import ObjectId
from typing import List

from app.db.models import VivaSession, VivaFeedback
from app.schemas.viva import VivaStartRequest
from app.interfaces.llm_client import LLMClient


class VivaService:
    """
    Service class encapsulating all business logic associated with viva sessions.

    Responsibilities:
    - Start new viva sessions.
    - Persist and conclude sessions with AI-generated feedback.
    - Retrieve session metadata and history.
    - Provide controlled operations such as renaming or deleting sessions.

    This service acts as an intermediary between the presentation/API layer,
    the LLMClient, and the database models. No direct AI or DB logic leaks
    outside this class, maintaining clean architectural boundaries.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Initialize VivaService with a dependency-injected LLM client.

        Args:
            llm_client (LLMClient): A concrete implementation of the
                LLMClient protocol responsible for model interactions.
        """
        self.llm_client = llm_client

    # ----------------------------------------------------------------------
    # Start New Session
    # ----------------------------------------------------------------------
    async def start_new_viva_session(self, viva_request: VivaStartRequest) -> dict:
        """
        Create and persist a new viva session, then request an ephemeral
        AI token to begin the interactive viva process.

        This method:
        - Creates a new VivaSession in the database.
        - Requests an ephemeral token from the LLM client.
        - Returns the session ID and AI connection parameters.

        Args:
            viva_request (VivaStartRequest): Input details such as student name,
                topic, class level, session type, and voice preference.

        Returns:
            dict: Metadata required by the client to join the live AI session.
        """
        # Create session record
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

        # Request ephemeral token from LLM provider
        token_data = await self.llm_client.create_ephemeral_token(viva_request)

        return {
            "viva_session_id": str(new_session.id),
            "ephemeral_token": token_data["token"],
            # Model name is now returned dynamically (no direct import dependency)
            "google_model": token_data.get("model_name", "unknown-model"),
            "session_duration_minutes": token_data["session_duration_minutes"],
            "voice_name": token_data["voice_name"],
        }

    # ----------------------------------------------------------------------
    # Conclude Session
    # ----------------------------------------------------------------------
    async def conclude_viva_session(
        self,
        viva_session_id: str,
        score: int,
        summary: str,
        strong_points: List[str],
        areas_of_improvement: List[str],
    ) -> dict:
        """
        Finalize a viva session by attaching AI-generated feedback,
        updating session status, and marking the ending timestamp.

        Args:
            viva_session_id (str): ID of the viva session to conclude.
            score (int): Final evaluation score assigned by the AI.
            summary (str): Summary feedback and narrative evaluation.
            strong_points (List[str]): Topics the student performed well in.
            areas_of_improvement (List[str]): Topics needing improvement.

        Returns:
            dict: Minimal response confirming completion and including score.

        Raises:
            ValueError: If the session does not exist.
        """
        session = await VivaSession.get(ObjectId(viva_session_id))
        if not session:
            raise ValueError(f"Viva session {viva_session_id} not found")

        # Construct feedback object
        feedback_data = VivaFeedback(
            score=score,
            summary=summary,
            strong_points=strong_points,
            areas_of_improvement=areas_of_improvement,
        )

        # Update session state
        session.feedback = feedback_data
        session.status = "completed"
        session.ended_at = datetime.datetime.now(tz=datetime.timezone.utc)

        await session.save()

        return {
            "status": "completed",
            "score": score,
            "final_feedback": summary,
        }

    # ----------------------------------------------------------------------
    # Get Session Details
    # ----------------------------------------------------------------------
    async def get_viva_session_details(self, session_id: str) -> dict:
        """
        Retrieve complete metadata for a specific viva session.

        Args:
            session_id (str): The unique ID of the session.

        Returns:
            dict: Fully serialized session data including timestamps,
                class info, and feedback (if available).

        Raises:
            ValueError: If no session matches the provided ID.
        """
        session = await VivaSession.get(ObjectId(session_id))
        if not session:
            raise ValueError(f"Viva session {session_id} not found")

        # Pydantic model handles feedback serialization automatically.
        return {
            "viva_session_id": str(session.id),
            "student_name": session.student_name,
            "title": session.title,
            "topic": session.topic,
            "class_level": session.class_level,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "status": session.status,
            "feedback": session.feedback,
        }

    # ----------------------------------------------------------------------
    # User History
    # ----------------------------------------------------------------------
    async def get_user_history(self, user_id: str) -> list[dict]:
        """
        Retrieve the viva session history for a specific user.

        Sessions are sorted by most recent first.

        Args:
            user_id (str): ID of the user whose sessions are being queried.

        Returns:
            list[dict]: A list of lightweight session summaries.
        """
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

    # ----------------------------------------------------------------------
    # Rename Session
    # ----------------------------------------------------------------------
    async def rename_session(self, session_id: str, new_title: str) -> dict:
        """
        Update the title of an existing viva session.

        Args:
            session_id (str): ID of the session to rename.
            new_title (str): New title to assign.

        Returns:
            dict: Operation status and confirmation message.

        Raises:
            ValueError: If the session does not exist.
        """
        session = await VivaSession.get(ObjectId(session_id))
        if not session:
            raise ValueError(f"Viva session {session_id} not found")

        session.title = new_title
        await session.save()

        return {"status": "success", "message": "Session renamed successfully"}

    # ----------------------------------------------------------------------
    # Delete Session
    # ----------------------------------------------------------------------
    async def delete_session(self, session_id: str) -> dict:
        """
        Permanently delete a viva session from the system.

        Args:
            session_id (str): ID of the session to delete.

        Returns:
            dict: Operation status and confirmation message.

        Raises:
            ValueError: If the session does not exist.
        """
        session = await VivaSession.get(ObjectId(session_id))
        if not session:
            raise ValueError(f"Viva session {session_id} not found")

        await session.delete()
        return {"status": "success", "message": "Session deleted successfully"}