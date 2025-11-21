"""
This module defines the database models (collections) using Beanie and Pydantic.
These models represent the structure of the data stored in MongoDB.

- VivaTurn: A Pydantic model for a sub-document within VivaSession.
- VivaSession: A Beanie Document for a top-level viva session.
- QuestionBank: A Beanie Document for the collection of questions.
"""

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime


class VivaTurn(BaseModel):
    """
    A Pydantic model representing a single Question/Answer turn.
    This is intended to be used as an embedded document (a list) within
    the VivaSession document.
    """
    turn_id: int  # Sequential ID for the turn (1, 2, 3...)
    question_text: str  # The text of the question that was asked
    difficulty: int  # The difficulty of the question that was asked (1-5)
    question_id: Optional[str] = None  # ID of the question from QuestionBank
    student_answer_transcription: Optional[str] = (
        None  # The student's transcribed answer
    )
    ai_evaluation: Optional[str] = None  # The AI's evaluation/feedback
    is_correct: Optional[bool] = None  # Whether the answer was correct
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )


class VivaSession(Document):
    """
    A Beanie Document representing a complete viva session.
    This is a top-level collection in MongoDB.
    """
    student_name: str
    topic: Indexed(str)  # Indexed for faster queries
    class_level: Indexed(int)  # Indexed for faster queries
    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    ended_at: Optional[datetime.datetime] = None
    status: str = "in_progress"  # "in_progress", "completed", "abandoned"
    turns: List[VivaTurn] = []  # List of question-answer turns
    final_feedback: Optional[str] = None  # Overall feedback at the end

    class Settings:
        name = "viva_sessions"  # Collection name in MongoDB


class QuestionBank(Document):
    """
    A Beanie Document representing the bank of questions.
    This is a separate collection in MongoDB that stores all available questions.
    """
    topic: Indexed(str)  # e.g., "Python Programming"
    class_level: Indexed(int)  # e.g., 10, 11, 12
    difficulty: Indexed(int)  # 1 (easy) to 5 (hard)
    question_text: str
    expected_answer_keywords: Optional[List[str]] = (
        None  # Optional keywords for evaluation
    )
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    class Settings:
        name = "question_bank"  # Collection name in MongoDB
        indexes = [
            "topic",
            "class_level",
            "difficulty",
            [("topic", 1), ("class_level", 1), ("difficulty", 1)],  # Compound index
        ]