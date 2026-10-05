"""Session domain values, independent of the persistence provider."""

import datetime
from typing import Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field

from app.domain.curriculum import CurriculumSelection

SESSION_ID_PATTERN = r"^[0-9]{20}-[a-f0-9]{32}$"


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def new_session_id(created_at: datetime.datetime) -> str:
    """Order history by UTC creation time without paying for a secondary index.

    The random suffix avoids collisions between workers at the same instant;
    equal timestamps have arbitrary suffix order. Clients must treat IDs as opaque.
    """
    return (
        f"{created_at.astimezone(datetime.timezone.utc):%Y%m%d%H%M%S%f}-{uuid4().hex}"
    )


class VivaFeedback(BaseModel):
    score: int = Field(ge=0, le=10)
    summary: str
    strong_points: list[str] = Field(default_factory=list)
    areas_of_improvement: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    coverage_note: str | None = None


class VivaSession(BaseModel):
    """Persisted session aggregate; expires_at ends activity, not data retention."""

    id: str = Field(default_factory=lambda: new_session_id(utc_now()))
    user_id: str
    student_name: str
    title: str
    topic: str
    class_level: str
    session_type: str = "viva"
    curriculum_selection: CurriculumSelection | None = Field(
        default=None,
        validation_alias=AliasChoices("curriculum_selection", "curriculum_context"),
    )
    started_at: datetime.datetime = Field(default_factory=utc_now)
    updated_at: datetime.datetime = Field(default_factory=utc_now)
    ended_at: datetime.datetime | None = None
    expires_at: datetime.datetime | None = None
    status: Literal["in_progress", "completed", "abandoned"] = "in_progress"
    feedback: VivaFeedback | None = None
    transcript: str | None = None
    revision: int = 0
