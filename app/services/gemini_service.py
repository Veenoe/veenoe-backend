"""
This module handles all interactions with the Google Gemini API.
It is responsible for:
- Defining the tools (function declarations) the AI can use.
- Generating the system instruction (prompt) for the AI.
- Creating secure, short-lived ephemeral tokens for the client.
"""

import logging
import google.genai as genai
import datetime
from app.core.config import settings
from app.schemas.viva import VivaStartRequest

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# The specific model to be used for the viva
MODEL_NAME = "gemini-2.5-flash-native-audio-preview-09-2025"

# --- Define the Tools the AI can use ---

conclude_viva_tool = {
    "name": "conclude_viva",
    "description": "Call this tool to END the viva session. You MUST provide a score, summary, strengths, and areas for improvement.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "viva_session_id": {
                "type": "STRING",
                "description": "The ID of the current viva session.",
            },
            "score": {
                "type": "INTEGER",
                "description": "A final score out of 10 based on technical accuracy and communication.",
            },
            "summary": {
                "type": "STRING",
                "description": "A polite closing statement and brief summary of performance.",
            },
            "strong_points": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of 2-3 specific topics or concepts the student understood well.",
            },
            "areas_of_improvement": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of 2-3 specific topics or concepts the student needs to study further.",
            },
        },
        "required": [
            "viva_session_id",
            "score",
            "summary",
            "strong_points",
            "areas_of_improvement",
        ],
    },
}


def generate_system_instruction(viva_request: VivaStartRequest) -> str:
    """
    Generates the system instruction (prompt) for the AI model based on
    the viva's configuration.
    """
    logger.debug(
        f"Generating system instruction for student: {viva_request.student_name}, topic: {viva_request.topic}"
    )

    system_instruction = f"""
You are an expert oral examiner conducting a Viva (oral exam) for a student.

**Student Name:** {viva_request.student_name}
**Topic:** {viva_request.topic}
**Class Level:** {viva_request.class_level}
**Session Duration:** 5 minutes maximum

**Your Role & Protocol:**
1.  **Welcome**: Start by welcoming the student and stating the topic clearly.
2.  **Questioning**: Ask **one question at a time**.
    -   Generate questions dynamically based on the topic and class level.
    -   Keep questions conversational but academically rigorous.
    -   Start with fundamental concepts. If answered correctly, increase difficulty.
    -   If the student struggles, provide a small hint or ask a simpler follow-up.
3.  **Evaluation (Internal)**: You must mentally track their performance.
    -   Start with a baseline score of 10/10.
    -   Deduct points for factual errors, inability to explain concepts, or requiring too many hints.
    -   Note down specific strengths and weaknesses as you go.
4.  **Conclusion**: After asking 5-7 questions OR if the user indicates they want to stop (e.g., "End viva"), you MUST conclude the session in **two steps**:
    a.  **First, speak your conclusion out loud.** Thank the student for their time, give a brief verbal summary of how they did (e.g., "You demonstrated a solid understanding of X and Y. I'd suggest reviewing Z for next time."), and say a warm goodbye.
    b.  **Then, immediately after you finish speaking, call the `conclude_viva` tool** with the final score and detailed written feedback.

**Strict Rules:**
-   **DO NOT** provide a running score after every question.
-   **DO NOT** say "Correct" or "Incorrect" robotically. Respond naturally (e.g., "That's a great point, but have you considered...").
-   When using `conclude_viva`, ensure the `strong_points` and `areas_of_improvement` are specific to the topics discussed, not generic advice.
-   **CRITICAL:** You MUST speak your concluding remarks BEFORE calling the `conclude_viva` tool. Do not call the tool silently.
"""
    return system_instruction.strip()


async def create_ephemeral_token(viva_request: VivaStartRequest) -> dict:
    """
    Creates a secure, short-lived ephemeral token that the client will use
    to connect to the Google Live API.
    """
    logger.info(
        f"Starting ephemeral token creation for viva session. Student: {viva_request.student_name}"
    )

    try:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)

        system_instruction = generate_system_instruction(viva_request)

        # We only need the conclude tool now, as we aren't saving turns individually
        tool_declarations = [conclude_viva_tool]

        live_config = {
            "session_resumption": {},
            "response_modalities": ["AUDIO"],
            "system_instruction": system_instruction,
            "tools": [{"function_declarations": tool_declarations}],
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }

        if viva_request.voice_name:
            live_config["speech_config"] = {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": viva_request.voice_name}
                }
            }

        token_config = {
            "uses": 1,
            "expire_time": datetime.datetime.now(tz=datetime.timezone.utc)
            + datetime.timedelta(minutes=15),
            "live_connect_constraints": {
                "model": MODEL_NAME,
                "config": live_config,
            },
            "http_options": {"api_version": "v1alpha"},
        }

        token = await client.aio.auth_tokens.create(config=token_config)

        return {
            "token": token.name,
            "voice_name": viva_request.voice_name or "Kore",
            "session_duration_minutes": 5,
        }

    except Exception as e:
        logger.error(f"Failed to create ephemeral token: {str(e)}", exc_info=True)
        raise
