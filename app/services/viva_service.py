"""Session lifecycle and assessment rules, independent of DynamoDB expressions."""

import datetime
from typing import List

from app.db.models import VivaFeedback, VivaSession, new_session_id, utc_now
from app.db.session_repository import SessionConflict, SessionRepository
from app.domain.curriculum import CurriculumSelection
from app.interfaces.llm_client import LLMClient
from app.schemas.viva import VivaStartRequest

SESSION_EXPIRY_GRACE = datetime.timedelta(minutes=2)


class VivaService:
    """Apply session business rules without exposing storage expressions to routes."""

    def __init__(self, llm_client: LLMClient, repository: SessionRepository) -> None:
        self.llm_client = llm_client
        self.repository = repository

    async def start_new_viva_session(
        self, viva_request: VivaStartRequest, user_id: str
    ) -> dict:
        # A failed token request must not leave a session that was never usable.
        token_data = await self.llm_client.create_ephemeral_token(viva_request)
        now = utc_now()
        session = VivaSession(
            id=new_session_id(now),
            user_id=user_id,
            student_name=viva_request.student_name,
            title=viva_request.topic,
            topic=viva_request.topic,
            class_level=viva_request.class_level,
            session_type=viva_request.session_type or "viva",
            curriculum_selection=(
                CurriculumSelection.model_validate(
                    viva_request.curriculum_selection.model_dump()
                )
                if viva_request.curriculum_selection
                else None
            ),
            started_at=now,
            updated_at=now,
            expires_at=now
            + datetime.timedelta(minutes=token_data["session_duration_minutes"])
            + SESSION_EXPIRY_GRACE,
        )
        await self.repository.create_session(session)
        return {
            "viva_session_id": session.id,
            "ephemeral_token": token_data["token"],
            "google_model": token_data.get("model_name", "unknown-model"),
            "session_duration_minutes": token_data["session_duration_minutes"],
            "voice_name": token_data["voice_name"],
            "vad_profile": token_data.get("vad_profile"),
        }

    async def _reconcile_expired_session(self, session: VivaSession) -> VivaSession:
        """Expire only records being read, avoiding a scheduled table scan.

        The grace period allows final browser delivery after the provider's session
        duration. A concurrent completion wins over our stale expiry attempt.
        History is retained; DynamoDB TTL would delete it, not update its status.
        """
        now = utc_now()
        if (
            session.status == "in_progress"
            and session.expires_at
            and session.expires_at <= now
        ):
            session.status = "abandoned"
            session.ended_at = now
            try:
                await self.repository.update_session(session)
            except SessionConflict:
                return await self.repository.get_session_for_user(
                    session.user_id, session.id
                )
        return session

    async def _get_session_with_ownership_check(
        self, session_id: str, user_id: str
    ) -> VivaSession:
        session = await self.repository.get_session_for_user(user_id, session_id)
        return await self._reconcile_expired_session(session)

    @staticmethod
    def _completion_response(session: VivaSession) -> dict:
        if session.status != "completed" or session.feedback is None:
            raise SessionConflict("Session is no longer active")
        return {
            "status": "completed",
            "score": session.feedback.score,
            "final_feedback": session.feedback.summary,
        }

    async def conclude_viva_session(
        self,
        viva_session_id: str,
        score: int,
        summary: str,
        strong_points: List[str],
        areas_of_improvement: List[str],
        user_id: str,
        next_steps: List[str] | None = None,
        coverage_note: str | None = None,
        transcript: str | None = None,
    ) -> dict:
        """Persist the first successful completion and return it on duplicate delivery.

        A late completion cannot revive abandonment or expiry. On a write race,
        re-read the winning state rather than overwrite its assessment.
        """
        session = await self._get_session_with_ownership_check(viva_session_id, user_id)
        if session.status != "in_progress":
            return self._completion_response(session)
        session.feedback = VivaFeedback(
            score=score,
            summary=summary,
            strong_points=strong_points,
            areas_of_improvement=areas_of_improvement,
            next_steps=next_steps or [],
            coverage_note=coverage_note,
        )
        session.transcript = transcript
        session.status = "completed"
        session.ended_at = utc_now()
        try:
            await self.repository.update_session(session)
        except SessionConflict:
            # A concurrent completion keeps its original assessment; an abandon
            # or expiry winner cannot be revived by a late browser request.
            session = await self.repository.get_session_for_user(
                user_id, viva_session_id
            )
        return self._completion_response(session)

    async def abandon_viva_session(self, session_id: str, user_id: str) -> dict:
        session = await self._get_session_with_ownership_check(session_id, user_id)
        if session.status == "in_progress":
            session.status = "abandoned"
            session.ended_at = utc_now()
            try:
                await self.repository.update_session(session)
            except SessionConflict:
                session = await self.repository.get_session_for_user(
                    user_id, session_id
                )
        return {"status": session.status}

    async def get_viva_session_details(self, session_id: str, user_id: str) -> dict:
        session = await self._get_session_with_ownership_check(session_id, user_id)
        return {
            "viva_session_id": session.id,
            **session.model_dump(
                include={
                    "student_name",
                    "title",
                    "topic",
                    "class_level",
                    "started_at",
                    "ended_at",
                    "status",
                    "feedback",
                    "transcript",
                }
            ),
        }

    async def get_user_history(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> dict:
        sessions, next_cursor = await self.repository.list_sessions_for_user(
            user_id, limit, cursor
        )
        history = []
        for session in sessions:
            session = await self._reconcile_expired_session(session)
            history.append(
                {
                    "viva_session_id": session.id,
                    **session.model_dump(
                        include={
                            "title",
                            "topic",
                            "class_level",
                            "started_at",
                            "session_type",
                            "status",
                        }
                    ),
                }
            )
        return {"sessions": history, "next_cursor": next_cursor}

    async def rename_session(
        self, session_id: str, new_title: str, user_id: str
    ) -> dict:
        session = await self._get_session_with_ownership_check(session_id, user_id)
        session.title = new_title
        await self.repository.update_session(session)
        return {"status": "success", "message": "Session renamed successfully"}

    async def delete_session(self, session_id: str, user_id: str) -> dict:
        session = await self.repository.get_session_for_user(user_id, session_id)
        await self.repository.delete_session(session)
        return {"status": "success", "message": "Session deleted successfully"}
