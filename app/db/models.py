"""
This module defines the database models (collections) using Beanie and Pydantic.

These models represent the structure and schema of the data stored in MongoDB.
They serve as the single source of truth for how viva sessions and their
associated feedback are stored, validated, and retrieved from the database.
"""

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime


class VivaFeedback(BaseModel):
    """
    Structured feedback generated at the end of a viva session.

    This model encapsulates the evaluation results including the student's performance
    score, an overall summary, strengths, and improvement areas. It is embedded into
    the VivaSession document rather than stored as a separate collection.

    Attributes:
        score (int): Numeric score between 0 and 10 assessing performance.
        summary (str): High-level summary of the student's overall viva outcome.
        strong_points (List[str]): A list highlighting concepts the student excelled in.
        areas_of_improvement (List[str]): A list identifying concepts where improvement is needed.
    """
    score: int = Field(
        ...,
        ge=0,
        le=10,
        description="Score out of 10 representing the student's overall performance"
    )

    summary: str = Field(
        ...,
        description="Overall summary of the student's performance during the viva"
    )

    strong_points: List[str] = Field(
        default_factory=list,
        description="List of strong concepts demonstrated by the student"
    )

    areas_of_improvement: List[str] = Field(
        default_factory=list,
        description="List of concepts where the student needs improvement"
    )


class VivaSession(Document):
    """
    A Beanie Document representing a complete viva session.

    This model captures all metadata and outcomes associated with a viva session,
    including session details, timestamps, status, and optional structured feedback.
    It is stored as a top-level collection in MongoDB.

    Attributes:
        student_name (str): Name of the student participating in the viva.
        user_id (str): Clerk user ID of the educator; indexed for faster lookups.
        title (str): Title of the session (e.g., "Python Basics Viva").
        session_type (str): Either "viva" or "learn"; defaults to "viva".
        topic (str): Subject/topic of the session; indexed for improved query performance.
        class_level (int): Class or grade level of the student; indexed.
        started_at (datetime): UTC timestamp when the session began.
        ended_at (Optional[datetime]): UTC timestamp when the session ended.
        status (str): Current session state — "in_progress", "completed", or "abandoned".
        feedback (Optional[VivaFeedback]): Final structured evaluation once session is completed.
    """

    # Core session metadata
    student_name: str
    user_id: Indexed(str)  # Clerk user ID, indexed for efficient user-specific queries
    title: str  # Example: "Python Basics Viva"

    # Classification info
    session_type: str = "viva"  # Determines workflow; may be "viva" or "learn"
    topic: Indexed(str)  # Indexed for quicker topic-based retrievals
    class_level: Indexed(int)  # Indexed for level-based filtering

    # Timestamp tracking
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc),
        description="Timestamp (UTC) when the viva session was started"
    )

    ended_at: Optional[datetime.datetime] = Field(
        default=None,
        description="Timestamp (UTC) when the session ended, if applicable"
    )

    # Current session state
    status: str = Field(
        default="in_progress",
        description="Session status: 'in_progress', 'completed', or 'abandoned'"
    )

    # Final structured result from the viva evaluation
    feedback: Optional[VivaFeedback] = None

    class Settings:
        """
        Beanie internal model settings.

        Defines the MongoDB collection name where VivaSession documents
        are stored. This ensures consistency across environments and deployments.
        """
        name = "viva_sessions"  # Collection name in MongoDB