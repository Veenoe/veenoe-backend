"""
This module defines the database models (collections) using Beanie and Pydantic.
These models represent the structure of the data stored in MongoDB.
"""

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime


class VivaFeedback(BaseModel):
    """
    Structured feedback generated at the end of a viva session.
    """
    score: int = Field(..., ge=0, le=10, description="Score out of 10")
    summary: str = Field(..., description="Overall summary of the student's performance")
    strong_points: List[str] = Field(default_factory=list, description="List of strong concepts")
    areas_of_improvement: List[str] = Field(default_factory=list, description="List of areas needing improvement")


class VivaSession(Document):
    """
    A Beanie Document representing a complete viva session.
    This is a top-level collection in MongoDB.
    """
    student_name: str
    user_id: Indexed(str)  # User ID from Clerk
    title: str  # Session title (e.g., "Python Basics Viva")
    session_type: str = "viva"  # "viva" or "learn"
    topic: Indexed(str)  # Indexed for faster queries
    class_level: Indexed(int)  # Indexed for faster queries
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    ended_at: Optional[datetime.datetime] = None
    status: str = "in_progress"  # "in_progress", "completed", "abandoned"
    
    # We store the final structured result here
    feedback: Optional[VivaFeedback] = None

    class Settings:
        name = "viva_sessions"  # Collection name in MongoDB