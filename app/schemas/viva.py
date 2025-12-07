"""
This module defines the Pydantic schemas for the API.
These schemas act as the data contracts for API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
import datetime

# --- Shared Models ---
class VivaFeedback(BaseModel):
    score: int
    summary: str
    strong_points: List[str]
    areas_of_improvement: List[str]


# == Viva Start Schemas ==

class VivaStartRequest(BaseModel):
    student_name: str = Field(..., example="John Doe")
    user_id: str = Field(..., description="The Clerk User ID")
    topic: str = Field(..., example="Python Programming")
    class_level: int = Field(..., example=12)
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

# == Conclude Viva Schemas ==

class ConcludeVivaRequest(BaseModel):
    viva_session_id: str
    score: int = Field(..., ge=0, le=10)
    summary: str
    strong_points: List[str]
    areas_of_improvement: List[str]

class ConcludeVivaResponse(BaseModel):
    status: str = "completed"
    score: int
    final_feedback: str

# == History & Retrieval Schemas ==

class VivaSessionSummary(BaseModel):
    viva_session_id: str
    title: str
    topic: str
    class_level: int
    started_at: datetime.datetime
    session_type: str
    status: str

# NEW: Schema for fetching a single full session details
class VivaSessionDetailResponse(BaseModel):
    viva_session_id: str
    student_name: str
    title: str
    topic: str
    class_level: int
    started_at: datetime.datetime
    ended_at: Optional[datetime.datetime] = None
    status: str
    feedback: Optional[VivaFeedback] = None

class HistoryResponse(BaseModel):
    sessions: list[VivaSessionSummary]

class RenameSessionRequest(BaseModel):
    new_title: str