"""
This module contains the core business logic for the Viva application.
It orchestrates the process of a viva session, from starting it,
to handling function calls from the frontend, interfacing with the database,
and concluding the session.
"""

from app.db.models import VivaSession, VivaTurn, QuestionBank
from app.schemas.viva import VivaStartRequest
from app.services.gemini_service import create_ephemeral_token, MODEL_NAME
import datetime
from bson import ObjectId
from beanie.operators import NotIn
from typing import Optional


# --- Main Service Functions ---


async def start_new_viva_session(viva_request: VivaStartRequest) -> dict:
    """
    Orchestrates the start of a new viva session.

    1. Creates a new VivaSession document in the database.
    2. Calls the Gemini service to generate a secure ephemeral token.
    3. Returns the session ID, token, and model name to the client.

    Args:
        viva_request (VivaStartRequest): The request details from the client.

    Returns:
        dict: A dictionary containing session ID, token, and model name.
    """
    # 1. Create a new VivaSession in the database
    new_session = VivaSession(
        student_name=viva_request.student_name,
        topic=viva_request.topic,
        class_level=viva_request.class_level,
        started_at=datetime.datetime.now(tz=datetime.timezone.utc),
        turns=[],  # Initially empty, will be populated as questions are asked
        status="in_progress",
    )
    await new_session.insert()

    # 2. Generate an ephemeral token for this viva session
    token_data = await create_ephemeral_token(viva_request)

    # 3. Return the session details and token to the client
    return {
        "viva_session_id": str(new_session.id),
        "ephemeral_token": token_data["token"],
        "google_model": MODEL_NAME,
        "session_duration_minutes": token_data["session_duration_minutes"],
        "voice_name": token_data["voice_name"],
    }


async def get_next_question(
    viva_session_id: str, topic: str, class_level: int, difficulty: int
) -> dict:
    """
    Fetches the next question from the database.
    This is called by the frontend when the AI requests a question.

    Args:
        viva_session_id: The viva session ID
        topic: The subject topic
        class_level: Student's grade level
        difficulty: Desired difficulty (1-5)

    Returns:
        dict: Question text, difficulty, and question_id
    """
    # Verify session exists
    session = await VivaSession.get(ObjectId(viva_session_id))
    if not session:
        raise ValueError(f"Viva session {viva_session_id} not found")

    # Get already asked question IDs to avoid repetition
    asked_question_ids = []
    for turn in session.turns:
        if hasattr(turn, "question_id") and turn.question_id:
            asked_question_ids.append(ObjectId(turn.question_id))

    # Query the database for a question
    question = await QuestionBank.find_one(
        QuestionBank.topic == topic,
        QuestionBank.class_level == class_level,
        QuestionBank.difficulty == difficulty,
        NotIn(QuestionBank.id, asked_question_ids),
    )

    if not question:
        # Fallback: try any difficulty if no questions at target difficulty
        question = await QuestionBank.find_one(
            QuestionBank.topic == topic,
            QuestionBank.class_level == class_level,
            NotIn(QuestionBank.id, asked_question_ids),
        )

    if not question:
        raise ValueError(
            f"No questions found for topic='{topic}', class_level={class_level}"
        )

    return {
        "question_text": question.question_text,
        "difficulty": question.difficulty,
        "question_id": str(question.id),
    }


async def evaluate_and_save_response(
    viva_session_id: str,
    question_text: str,
    difficulty: int,
    student_answer: str,
    evaluation: str,
    is_correct: bool,
    question_id: Optional[str] = None,
) -> dict:
    """
    Saves the student's answer and AI's evaluation to the database.
    This is called by the frontend when the AI evaluates an answer.

    Args:
        viva_session_id: The viva session ID
        question_text: The question that was asked
        difficulty: Question difficulty
        student_answer: Student's transcribed answer
        evaluation: AI's evaluation
        is_correct: Whether answer was correct

    Returns:
        dict: Confirmation with turn_id
    """
    # Fetch the session
    session = await VivaSession.get(ObjectId(viva_session_id))
    if not session:
        raise ValueError(f"Viva session {viva_session_id} not found")

    # Create a new turn
    turn_id = len(session.turns) + 1
    new_turn = VivaTurn(
        turn_id=turn_id,
        question_text=question_text,
        difficulty=difficulty,
        question_id=question_id,
        student_answer_transcription=student_answer,
        ai_evaluation=evaluation,
        is_correct=is_correct,
        timestamp=datetime.datetime.now(tz=datetime.timezone.utc),
    )

    # Add the turn to the session
    session.turns.append(new_turn)
    await session.save()

    return {
        "status": "success",
        "message": "Response evaluated and saved",
        "turn_id": turn_id,
    }


async def conclude_viva_session(viva_session_id: str, final_feedback: str) -> dict:
    """
    Concludes the viva session and generates final statistics.
    This is called by the frontend when the AI concludes the viva.

    Args:
        viva_session_id: The viva session ID
        final_feedback: AI's final feedback

    Returns:
        dict: Final statistics and confirmation
    """
    # Fetch the session
    session = await VivaSession.get(ObjectId(viva_session_id))
    if not session:
        raise ValueError(f"Viva session {viva_session_id} not found")

    # Calculate statistics
    total_questions = len(session.turns)
    correct_answers = sum(1 for turn in session.turns if turn.is_correct)

    # Update session status
    session.status = "completed"
    session.ended_at = datetime.datetime.now(tz=datetime.timezone.utc)
    session.final_feedback = final_feedback
    await session.save()

    return {
        "status": "completed",
        "message": "Viva session concluded successfully",
        "total_questions": total_questions,
        "correct_answers": correct_answers,
        "final_feedback": final_feedback,
    }
