"""
This module handles all interactions with the Google Gemini API.
It is responsible for:
- Defining the tools (function declarations) the AI can use.
- Generating the system instruction (prompt) for the AI.
- Creating secure, short-lived ephemeral tokens for the client.
"""

import google.genai as genai
from google.genai import types
import datetime
from app.core.config import settings
from app.schemas.viva import VivaStartRequest

# The specific model to be used for the viva
MODEL_NAME = "gemini-2.5-flash-native-audio-preview-09-2025"

# --- Define the Tools the AI can use ---
# These are function declarations, following the OpenAPI 3.0 subset
# that Google's API uses.

get_next_question_tool = {
    "name": "get_next_question",
    "description": "Fetches the next question for the viva based on topic and class level.",
    "behavior": "NON_BLOCKING",  # Async execution - doesn't block conversation
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "topic": {"type": "STRING", "description": "The subject of the viva."},
            "class_level": {
                "type": "NUMBER",
                "description": "The student's grade or class level.",
            },
            "current_difficulty": {
                "type": "NUMBER",
                "description": "The difficulty level for the next question (1-5).",
            },
        },
        "required": ["topic", "class_level", "current_difficulty"],
    },
}

evaluate_and_save_response_tool = {
    "name": "evaluate_and_save_response",
    "description": "Evaluates the student's response and saves it to the database.",
    "behavior": "NON_BLOCKING",  # Async execution - doesn't block conversation
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "viva_session_id": {
                "type": "STRING",
                "description": "The ID of the current viva session.",
            },
            "question_text": {
                "type": "STRING",
                "description": "The text of the question that was asked.",
            },
            "question_id": {
                "type": "STRING",
                "description": "The ID of the question that was asked.",
            },
            "difficulty": {
                "type": "NUMBER",
                "description": "The difficulty level of the question (1-5).",
            },
            "student_answer": {
                "type": "STRING",
                "description": "The student's transcribed answer.",
            },
            "evaluation": {
                "type": "STRING",
                "description": "Your evaluation of the student's answer.",
            },
            "is_correct": {
                "type": "BOOLEAN",
                "description": "Whether the answer was correct or not.",
            },
        },
        "required": [
            "viva_session_id",
            "question_text",
            "question_id",
            "difficulty",
            "student_answer",
            "evaluation",
            "is_correct",
        ],
    },
}

conclude_viva_tool = {
    "name": "conclude_viva",
    "description": "Concludes the viva session and generates a final summary.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "viva_session_id": {
                "type": "STRING",
                "description": "The ID of the viva session to conclude.",
            },
            "final_feedback": {
                "type": "STRING",
                "description": "Your final feedback and summary for the student.",
            },
        },
        "required": ["viva_session_id", "final_feedback"],
    },
}


def generate_system_instruction(viva_request: VivaStartRequest) -> str:
    """
    Generates the system instruction (prompt) for the AI model based on
    the viva's configuration.

    Args:
        viva_request (VivaStartRequest): The details of the viva being started.

    Returns:
        str: The system instruction string.
    """
    system_instruction = f"""
You are an expert oral examiner conducting a viva (oral examination) for a student.

**Student Name:** {viva_request.student_name}
**Topic:** {viva_request.topic}
**Class Level:** {viva_request.class_level}
**Session Duration:** 10 minutes maximum

**Your Role:**
1. You will ask the student questions on the topic, starting at difficulty level 3.
2. Listen to the student's spoken answers carefully.
3. Evaluate each answer and provide constructive feedback.
4. Adjust the difficulty of subsequent questions based on performance:
   - If the student answers correctly, increase difficulty.
   - If the student struggles, decrease difficulty or provide hints.
5. Ask approximately 5-7 questions in total.
6. At the end, provide a comprehensive summary of the student's performance.

**Important Session Limits:**
- The session is limited to 10 minutes.
- You will receive a warning before the session ends.
- Conclude the viva gracefully if you receive a termination warning.

**Tools You Must Use:**
- **get_next_question**: Use this to fetch the next question from the database. You MUST call this for each new question.
- **evaluate_and_save_response**: After the student answers, use this to evaluate and save their response.
- **conclude_viva**: When you've asked enough questions or time is running out, use this to end the viva and generate final feedback.

**Important Instructions:**
- Speak naturally and encouragingly in audio responses.
- Wait for the student to finish speaking before evaluating.
- Be supportive but accurate in your evaluations.
- Start by greeting the student and asking the first question using get_next_question.
- These function calls are non-blocking, so you can continue the conversation while they execute.
"""
    return system_instruction.strip()


async def create_ephemeral_token(viva_request: VivaStartRequest) -> dict:
    """
    Creates a secure, short-lived ephemeral token that the client will use
    to connect to the Google Live API.

    Args:
        viva_request (VivaStartRequest): The viva session details.

    Returns:
        dict: Dictionary containing the token and configuration details.
    """
    # Initialize the Google GenAI client with your API key
    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    # Generate the system instruction
    system_instruction = generate_system_instruction(viva_request)

    # Combine all tool declarations into a single list
    tool_declarations = [
        get_next_question_tool,
        evaluate_and_save_response_tool,
        conclude_viva_tool,
    ]

    # Build the config for the Live API
    live_config = {
        "session_resumption": {},  # Enable session resumption
        "response_modalities": ["AUDIO"],  # AI responds with audio
        "system_instruction": system_instruction,
        "tools": [{"function_declarations": tool_declarations}],
        "input_audio_transcription": {},  # Enable input transcription
        "output_audio_transcription": {},  # Enable output transcription
    }

    # Add voice configuration if specified
    if viva_request.voice_name:
        live_config["speech_config"] = {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": viva_request.voice_name}
            }
        }

    # Add thinking configuration if enabled
    if viva_request.enable_thinking and viva_request.thinking_budget > 0:
        live_config["thinking_config"] = {
            "thinking_budget": viva_request.thinking_budget,
            "include_thoughts": True,  # Include thought summaries in responses
        }

    # Configure the ephemeral token with Live API constraints
    # Session limited to 10 minutes
    token_config = {
        "uses": 1,  # Token can only be used once
        "expire_time": datetime.datetime.now(tz=datetime.timezone.utc)
        + datetime.timedelta(minutes=10),  # 10-minute session limit
        "new_session_expire_time": datetime.datetime.now(tz=datetime.timezone.utc)
        + datetime.timedelta(minutes=2),  # 2 minutes to start session
        "live_connect_constraints": {
            "model": MODEL_NAME,
            "config": live_config,
        },
        # http_options for v1alpha must be inside config
        "http_options": {"api_version": "v1alpha"},
    }

    # Create the token using the v1alpha API
    # Use client.aio.auth_tokens.create for async call
    token = await client.aio.auth_tokens.create(config=token_config)

    # FIX: The token string is in the 'name' attribute, NOT 'token'
    return {
        "token": token.name,
        "voice_name": viva_request.voice_name or "Kore",
        "session_duration_minutes": 10,
    }
