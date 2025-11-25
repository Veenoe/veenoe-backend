"""
This module defines the Pydantic schemas for the API.
These schemas act as the data contracts for API requests and responses.
They ensure data validation, serialization, and generate OpenAPI documentation.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# == Viva Start Schemas ==


class VivaStartRequest(BaseModel):
    """
    Schema for the request body when starting a new viva.
    """

    student_name: str = Field(..., example="John Doe")
    topic: str = Field(..., example="Python Programming")
    class_level: int = Field(
        ..., example=12, description="The student's grade or class level"
    )
    voice_name: Optional[str] = Field(
        default="Kore",
        example="Kore",
        description="Voice for AI responses. Options: Kore, Puck, Charon, Aoede, Fenrir, etc.",
    )
    enable_thinking: Optional[bool] = Field(
        default=True, description="Enable thinking capabilities for better reasoning"
    )
    thinking_budget: Optional[int] = Field(
        default=1024,
        ge=0,
        le=8192,
        description="Number of thinking tokens (0 to disable, max 8192)",
    )


class VivaStartResponse(BaseModel):
    """
    Schema for the response body after successfully starting a viva.
    """

    viva_session_id: str  # The unique ID for the newly created session
    ephemeral_token: str  # The secure, short-lived token for the client
    google_model: str  # The name of the Google AI model being used
    session_duration_minutes: int = Field(
        default=10, description="Maximum session duration in minutes"
    )
    voice_name: str  # The voice being used for this session


# == Get Next Question Schemas ==


class GetNextQuestionRequest(BaseModel):
    """
    Schema for requesting the next question.
    Called by frontend when AI invokes get_next_question function.
    """

    viva_session_id: str = Field(..., description="The viva session ID")
    topic: str = Field(..., example="Python Programming")
    class_level: int = Field(..., example=12)
    current_difficulty: int = Field(..., ge=1, le=5, example=3)


class GetNextQuestionResponse(BaseModel):
    """
    Schema for the next question response.
    """

    question_text: str
    difficulty: int
    question_id: str  # For tracking purposes


# == Evaluate Response Schemas ==


class EvaluateResponseRequest(BaseModel):
    """
    Schema for evaluating a student's response.
    Called by frontend when AI invokes evaluate_and_save_response function.
    """

    viva_session_id: str
    question_text: str
    question_id: Optional[str] = None
    difficulty: int = Field(..., ge=1, le=5)
    student_answer: str
    evaluation: str
    is_correct: bool


class EvaluateResponseResponse(BaseModel):
    """
    Schema for evaluation confirmation.
    """

    status: str = "success"
    message: str
    turn_id: int


# == Conclude Viva Schemas ==


class ConcludeVivaRequest(BaseModel):
    """
    Schema for concluding a viva session.
    Called by frontend when AI invokes conclude_viva function.
    """

    viva_session_id: str
    final_feedback: str


class ConcludeVivaResponse(BaseModel):
    """
    Schema for viva conclusion response.
    """

    status: str = "completed"
    message: str
    total_questions: int
    correct_answers: int
    final_feedback: str
