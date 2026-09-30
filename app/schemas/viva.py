"""
This module defines the Pydantic schemas for the API.
These schemas act as the data contracts for API requests and responses.
"""

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated, List, Optional
import datetime

ReportPoint = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]


# --- Shared Models ---
class VivaFeedback(BaseModel):
    score: int
    summary: str
    strong_points: List[str]
    areas_of_improvement: List[str]
    next_steps: list[str] = Field(default_factory=list)
    coverage_note: str | None = None


# == Viva Start Schemas ==


class VivaStartRequest(BaseModel):
    """
    Request to start a new viva session.

    Note: user_id is NOT included here - it comes from the authenticated
    JWT token to prevent client-side spoofing.
    """

    student_name: str = Field(..., example="John Doe")
    topic: str = Field(..., example="Python Programming")
    class_level: str = Field(..., example="12")
    session_type: Optional[str] = Field(default="viva")
    voice_name: Optional[str] = Field(default="Kore")
    enable_thinking: Optional[bool] = Field(default=True)
    thinking_budget: Optional[int] = Field(default=1024)


class VivaStartResponse(BaseModel):
    viva_session_id: str
    ephemeral_token: str
    google_model: str
    session_duration_minutes: int
    voice_name: str
    vad_profile: Optional[str] = None


# == Conclude Viva Schemas ==


class ConcludeVivaRequest(BaseModel):
    viva_session_id: str
    score: int = Field(..., ge=0, le=10)
    summary: str = Field(..., min_length=1, max_length=2000)
    strong_points: list[ReportPoint] = Field(..., max_length=5)
    areas_of_improvement: list[ReportPoint] = Field(..., max_length=5)
    next_steps: list[ReportPoint] = Field(default_factory=list, max_length=3)
    coverage_note: ReportPoint | None = None


class ConcludeVivaResponse(BaseModel):
    status: str = "completed"
    score: int
    final_feedback: str


# == History & Retrieval Schemas ==


class VivaSessionSummary(BaseModel):
    viva_session_id: str
    title: str
    topic: str
    class_level: str
    started_at: datetime.datetime
    session_type: str
    status: str


# NEW: Schema for fetching a single full session details
class VivaSessionDetailResponse(BaseModel):
    viva_session_id: str
    student_name: str
    title: str
    topic: str
    class_level: str
    started_at: datetime.datetime
    ended_at: Optional[datetime.datetime] = None
    status: str
    feedback: Optional[VivaFeedback] = None


class HistoryResponse(BaseModel):
    sessions: list[VivaSessionSummary]


class RenameSessionRequest(BaseModel):
    """Request to rename a viva session."""

    new_title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="New title for the session (1-200 characters)",
    )
