"""
This module defines the API endpoints for version 1 of the 'viva' resource.
It handles the HTTP layer, delegating all business logic to the viva_service.
"""

from fastapi import APIRouter, HTTPException, Body
from app.schemas.viva import (
    VivaStartRequest,
    VivaStartResponse,
    GetNextQuestionRequest,
    GetNextQuestionResponse,
    EvaluateResponseRequest,
    EvaluateResponseResponse,
    ConcludeVivaRequest,
    ConcludeVivaResponse,
)
from app.services.viva_service import (
    start_new_viva_session,
    get_next_question,
    evaluate_and_save_response,
    conclude_viva_session,
)

# Create a router for these specific endpoints
router = APIRouter()


@router.post("/start", response_model=VivaStartResponse)
async def start_viva(request: VivaStartRequest):
    """
    Starts a new viva session.

    This endpoint:
    1. Receives student details (name, topic, class).
    2. Calls the service layer to create a new VivaSession in the database.
    3. Calls the service layer to generate a secure ephemeral token from Google.
    4. Returns the session ID and the token to the client.

    Args:
        request (VivaStartRequest): The request body containing student details.

    Returns:
        VivaStartResponse: Session ID, ephemeral token, and model name.
    """
    try:
        response_data = await start_new_viva_session(request)
        return VivaStartResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting viva: {str(e)}")


@router.post("/get-next-question", response_model=GetNextQuestionResponse)
async def get_question(request: GetNextQuestionRequest):
    """
    Fetches the next question for the viva.

    This endpoint is called by the FRONTEND when the AI (via Live API)
    requests a new question using the get_next_question function.

    Args:
        request (GetNextQuestionRequest): Contains viva_session_id, topic,
                                          class_level, and current_difficulty.

    Returns:
        GetNextQuestionResponse: The question text and difficulty.
    """
    try:
        result = await get_next_question(
            viva_session_id=request.viva_session_id,
            topic=request.topic,
            class_level=request.class_level,
            difficulty=request.current_difficulty,
        )
        return GetNextQuestionResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching question: {str(e)}"
        )


@router.post("/evaluate-response", response_model=EvaluateResponseResponse)
async def evaluate_response(request: EvaluateResponseRequest):
    """
    Evaluates and saves the student's response.

    This endpoint is called by the FRONTEND when the AI (via Live API)
    wants to evaluate a student's answer using the evaluate_and_save_response function.

    Args:
        request (EvaluateResponseRequest): Contains all evaluation details.

    Returns:
        EvaluateResponseResponse: Confirmation of saved evaluation.
    """
    try:
        result = await evaluate_and_save_response(
            viva_session_id=request.viva_session_id,
            question_text=request.question_text,
            difficulty=request.difficulty,
            student_answer=request.student_answer,
            evaluation=request.evaluation,
            is_correct=request.is_correct,
            question_id=request.question_id,
        )
        return EvaluateResponseResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error evaluating response: {str(e)}"
        )


@router.post("/conclude-viva", response_model=ConcludeVivaResponse)
async def conclude_viva(request: ConcludeVivaRequest):
    """
    Concludes the viva session and generates final summary.

    This endpoint is called by the FRONTEND when the AI (via Live API)
    wants to end the viva using the conclude_viva function.

    Args:
        request (ConcludeVivaRequest): Contains viva_session_id and final_feedback.

    Returns:
        ConcludeVivaResponse: Confirmation and final summary.
    """
    try:
        result = await conclude_viva_session(
            viva_session_id=request.viva_session_id,
            final_feedback=request.final_feedback,
        )
        return ConcludeVivaResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error concluding viva: {str(e)}")
