"""
This module handles all interactions with the Google Gemini API.
It is responsible for:
- Defining the tools (function declarations) the AI can use.
- Generating the system instruction (prompt) for the AI.
- Creating secure, short-lived ephemeral tokens for the client.
"""

import logging
import google.genai as genai
from google.genai import types
import datetime
from app.core.config import settings
from app.schemas.viva import VivaStartRequest

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# The specific model to be used for the viva
MODEL_NAME = "gemini-2.5-flash-native-audio-preview-09-2025"

# --- Define the Tools the AI can use ---
# Only conclude_viva is needed now.

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
            "score": {
                "type": "INTEGER",
                "description": "Final score out of 10.",
            },
        },
        "required": ["viva_session_id", "final_feedback", "score"],
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
    logger.debug(
        f"Generating system instruction for student: {viva_request.student_name}, topic: {viva_request.topic}"
    )

    system_instruction = f"""
You are an expert oral examiner conducting a viva (oral examination) for a student.

**Student Name:** {viva_request.student_name}
**Topic:** {viva_request.topic}
**Class Level:** {viva_request.class_level}
**Session Duration:** 5 minutes maximum

**Your Role:**
1.  **Welcome**: Start by welcoming the student and stating the topic.
2.  **Questioning**: Ask **one question at a time**. Wait for the student's answer.
    -   Generate questions dynamically based on the topic and the student's responses.
    -   Start with easier questions and increase difficulty if they answer correctly.
    -   If they struggle, provide a hint or ask a simpler follow-up.
3.  **Evaluation**: Internally evaluate their answers. Do not explicitly state 'Correct' or 'Incorrect' after every answer, but guide the conversation naturally.
4.  **Conclusion**: After asking 5-7 questions or if the time is up, conclude the session.
    -   Use the `conclude_viva` tool to submit the final score (out of 10) and detailed feedback.
    -   Say a polite goodbye to the student.

**Important Session Limits:**
- The session is limited to 5 minutes.
- You will receive a warning before the session ends.
- Conclude the viva gracefully if you receive a termination warning.

**Tools You Must Use:**
- **conclude_viva**: When you've asked enough questions or time is running out, use this to end the viva and generate final feedback.

**Important Instructions:**
- Speak naturally and encouragingly in audio responses.
- Wait for the student to finish speaking before evaluating.
- Be supportive but accurate in your evaluations.
- Do NOT ask multiple questions at once. Keep your responses concise.
"""
    logger.debug("System instruction generated successfully.")
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
    logger.info(
        f"Starting ephemeral token creation for viva session. Student: {viva_request.student_name}"
    )

    try:
        # Initialize the Google GenAI client with your API key
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        logger.debug("Google GenAI client initialized.")

        # Generate the system instruction
        system_instruction = generate_system_instruction(viva_request)

        # Combine all tool declarations into a single list
        tool_declarations = [
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
            logger.debug(f"Configuring voice: {viva_request.voice_name}")
            live_config["speech_config"] = {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": viva_request.voice_name}
                }
            }

        # Add thinking configuration if enabled
        if viva_request.enable_thinking and viva_request.thinking_budget > 0:
            logger.debug(f"Configuring thinking budget: {viva_request.thinking_budget}")
            live_config["thinking_config"] = {
                "thinking_budget": viva_request.thinking_budget,
                "include_thoughts": False,  # Do not include thought summaries in responses
            }

        # Configure the ephemeral token with Live API constraints
        # Session limited to 5 minutes
        token_config = {
            "uses": 1,  # Token can only be used once
            "expire_time": datetime.datetime.now(tz=datetime.timezone.utc)
            + datetime.timedelta(minutes=5),  # 5-minute session limit
            "new_session_expire_time": datetime.datetime.now(tz=datetime.timezone.utc)
            + datetime.timedelta(minutes=2),  # 2 minutes to start session
            "live_connect_constraints": {
                "model": MODEL_NAME,
                "config": live_config,
            },
            # http_options for v1alpha must be inside config
            "http_options": {"api_version": "v1alpha"},
        }

        logger.debug("Requesting ephemeral token from Google API...")

        # Create the token using the v1alpha API
        # Use client.aio.auth_tokens.create for async call
        token = await client.aio.auth_tokens.create(config=token_config)

        logger.info(f"Ephemeral token created successfully. Token name: {token.name}")

        # FIX: The token string is in the 'name' attribute, NOT 'token'
        return {
            "token": token.name,
            "voice_name": viva_request.voice_name or "Kore",
            "session_duration_minutes": 5,
        }

    except Exception as e:
        logger.error(f"Failed to create ephemeral token: {str(e)}", exc_info=True)
        raise
