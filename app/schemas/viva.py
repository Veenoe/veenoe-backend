"""
This module defines the Pydantic schemas for the API.
These schemas act as the data contracts for API requests and responses.
"""

from pydantic import BaseModel, Field, StringConstraints, ConfigDict, model_validator
from typing import Annotated, List, Optional
import datetime
from app.domain import curriculum as curriculum_domain

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


CurriculumId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
CurriculumLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class SelectedTopic(curriculum_domain.SelectedTopic):
    """One chosen catalog or custom topic; IDs identify choices, names guide questions."""

    model_config = ConfigDict(extra="forbid")
    id: CurriculumId
    name: CurriculumLabel

    @model_validator(mode="after")
    def valid_custom_topic(self):
        """Enforce the UI text limit for custom topics, identified by their reserved ID prefix."""
        if self.id.startswith("custom-topic-") and (
            len(self.name) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in self.name)
        ):
            raise ValueError(
                "Custom topics must be a single line of at most 100 characters"
            )
        return self


class SelectedChapter(curriculum_domain.SelectedChapter):
    """A chapter and its focus topics; an empty list selects the whole chapter."""

    model_config = ConfigDict(extra="forbid")
    id: CurriculumId
    name: CurriculumLabel
    # No chosen topics means the entire chapter, rather than an empty assessment.
    topics: list[SelectedTopic] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_topics(self):
        """Reject repeated IDs and case-insensitive custom duplicates; cap custom topics at 20."""
        if len({topic.id for topic in self.topics}) != len(self.topics):
            raise ValueError("Topic IDs must be unique within a chapter")
        custom = [
            topic.name.casefold()
            for topic in self.topics
            if topic.id.startswith("custom-topic-")
        ]
        if len(custom) > 20 or len(set(custom)) != len(custom):
            raise ValueError(
                "Custom topics must be unique, with at most 20 per chapter"
            )
        return self


class CurriculumSelectionRequest(curriculum_domain.CurriculumSelection):
    """Validate request shape without coupling the API to the webapp's catalog.

    Names and optional revision metadata are supplied by the client. They record
    the requested scope, not a server-verified syllabus or textbook edition.
    """

    model_config = ConfigDict(extra="forbid")
    catalog_id: CurriculumId | None = None
    catalog_version: CurriculumId | None = None
    class_level: int = Field(ge=5, le=12, strict=True)
    subject_id: CurriculumId
    subject_name: CurriculumLabel
    chapters: list[SelectedChapter] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_chapters(self):
        """Keep chapter identities unambiguous when reading or validating a selection."""
        if len({chapter.id for chapter in self.chapters}) != len(self.chapters):
            raise ValueError("Chapter IDs must be unique")
        return self


class VivaStartRequest(BaseModel):
    """
    Request to start a new viva session.

    Note: user_id is NOT included here - it comes from the authenticated
    JWT token to prevent client-side spoofing.
    """

    student_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] = Field(..., example="John Doe")
    topic: str = Field(..., example="Python Programming")
    class_level: str = Field(..., example="12")
    session_type: Optional[str] = Field(default="viva")
    voice_name: Optional[str] = Field(default="Kore")
    enable_thinking: Optional[bool] = Field(default=True)
    thinking_budget: Optional[int] = Field(default=1024)
    curriculum_selection: CurriculumSelectionRequest | None = None

    @model_validator(mode="after")
    def validate_selection_class(self):
        """Require one chapter and one consistent class so the examiner gets a single scope."""
        # Stored selections can contain more chapters; each new viva accepts one.
        if (
            isinstance(self.curriculum_selection, CurriculumSelectionRequest)
            and len(self.curriculum_selection.chapters) != 1
        ):
            raise ValueError("Select exactly one chapter for a viva")
        if self.curriculum_selection and self.class_level != str(
            self.curriculum_selection.class_level
        ):
            raise ValueError("Class level must match the curriculum selection")
        if self.curriculum_selection:
            # Keep history titles aligned with the same client-supplied scope
            # used by the prompt, instead of a competing free-text topic.
            chapter = self.curriculum_selection.chapters[0]
            self.topic = chapter.name + (
                ": " + ", ".join(t.name for t in chapter.topics)
                if chapter.topics
                else ""
            )
        return self


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
