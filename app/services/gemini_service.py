"""
Service module responsible for managing all interactions with the Google Gemini API.

This includes:
- Defining the tool declarations exposed to the AI model.
- Generating dynamic system instructions for viva sessions.
- Creating short-lived ephemeral tokens for secure real-time communication.

This module follows FastAPI service-layer best practices and acts as the
Gemini-specific implementation of the LLMClient interface.
"""

import logging
import datetime
import google.genai as genai
from app.core.config import settings
from app.schemas.viva import VivaStartRequest
from app.interfaces.llm_client import LLMClient

# Configure module-level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeminiService:
    """
    Service class implementing the LLMClient protocol using Google Gemini.

    This class encapsulates:
    - System prompt generation for viva sessions.
    - Declarative tool definitions used by the model.
    - Creation of ephemeral tokens enabling clients to connect via Gemini Live API.

    The class is stateless except for the API key reference, making it
    safe for concurrent instantiation and aligned with dependency-injection
    patterns commonly used in FastAPI applications.
    """

    # The Gemini model used for Viva interactions.
    MODEL_NAME = "gemini-2.5-flash-native-audio-preview-09-2025"

    # ----------------------------------------------------------------------
    # Tool Declaration: conclude_viva
    # ----------------------------------------------------------------------
    # This tool is exposed to the AI and must be called at the end of
    # the viva session with detailed evaluation metadata.
    _CONCLUDE_VIVA_TOOL = {
        "name": "conclude_viva",
        "description": (
            "Call this tool to END the viva session. You MUST provide a score, "
            "summary, strengths, and areas for improvement."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "score": {
                    "type": "INTEGER",
                    "description": (
                        "Final score out of 10 based on technical accuracy "
                        "and communication."
                    ),
                },
                "summary": {
                    "type": "STRING",
                    "description": "A polite closing statement and final performance summary.",
                },
                "strong_points": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": (
                        "List of 2–3 specific concepts the student demonstrated strong understanding of."
                    ),
                },
                "areas_of_improvement": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": (
                        "List of 2–3 specific topics the student needs to improve."
                    ),
                },
            },
            "required": [
                "score",
                "summary",
                "strong_points",
                "areas_of_improvement",
            ],
        },
    }

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(self) -> None:
        """
        Initialize the GeminiService.

        Loads the Google API key from application settings and prepares
        the service instance for model interactions.
        """
        self._api_key = settings.GOOGLE_API_KEY
        logger.debug("GeminiService initialized with configured API key.")

    # ------------------------------------------------------------------
    # System Instruction Builder
    # ------------------------------------------------------------------
    def generate_system_instruction(self, viva_request: VivaStartRequest) -> str:
        """
        Generate and return the system instruction (prompt) that guides
        the AI's behavior during the viva session.

        Parameters
        ----------
        viva_request : VivaStartRequest
            Object containing student name, topic, class level, and optional voice preference.

        Returns
        -------
        str
            A fully structured prompt for the Gemini model defining
            viva protocol, evaluation rules, and concluding behavior.
        """
        logger.debug(
            f"Generating system instruction for viva session → "
            f"Student: {viva_request.student_name}, Topic: {viva_request.topic}"
        )

        # Construct structured system instructions fed directly to Gemini.
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

    # ------------------------------------------------------------------
    # Ephemeral Token Creation
    # ------------------------------------------------------------------
    async def create_ephemeral_token(self, viva_request: VivaStartRequest) -> dict:
        """
        Create a secure, short-lived ephemeral token allowing the
        client to connect to the Google Gemini Live API.

        This token:
        - Is valid for exactly one usage.
        - Expires in 15 minutes.
        - Includes the system instruction and tool declarations.
        - Configures audio input/output and optional voice settings.

        Parameters
        ----------
        viva_request : VivaStartRequest
            Contains viva metadata required to personalize the system prompt.

        Returns
        -------
        dict
            A structured response containing:
            - token: str (ephemeral token ID)
            - voice_name: str (selected or default voice)
            - session_duration_minutes: int
            - model_name: str (Gemini model used)

        Raises
        ------
        Exception
            If token creation fails, the exception is logged and re-raised.
        """
        logger.info(
            f"Starting ephemeral token creation for viva session. "
            f"Student: {viva_request.student_name}"
        )

        try:
            # A new client is created per request to maintain async safety.
            client = genai.Client(api_key=self._api_key)

            # Build system instructions and tool declarations.
            system_instruction = self.generate_system_instruction(viva_request)
            tool_declarations = [self._CONCLUDE_VIVA_TOOL]

            # Base configuration passed to the Gemini Live API.
            live_config = {
                "session_resumption": {},
                "response_modalities": ["AUDIO"],
                "system_instruction": system_instruction,
                "tools": [{"function_declarations": tool_declarations}],
                "input_audio_transcription": {},
                "output_audio_transcription": {},
            }

            # Optionally configure a specific voice.
            if viva_request.voice_name:
                live_config["speech_config"] = {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": viva_request.voice_name}
                    }
                }

            # Token configuration: one-time use, expires in 15 minutes.
            token_config = {
                "uses": 1,
                "expire_time": (
                    datetime.datetime.now(tz=datetime.timezone.utc)
                    + datetime.timedelta(minutes=15)
                ),
                "live_connect_constraints": {
                    "model": self.MODEL_NAME,
                    "config": live_config,
                },
                "http_options": {"api_version": "v1alpha"},
            }

            # Create ephemeral token asynchronously.
            token = await client.aio.auth_tokens.create(config=token_config)

            return {
                "token": token.name,
                "voice_name": viva_request.voice_name or "Kore",
                "session_duration_minutes": 5,
                "model_name": self.MODEL_NAME,
            }

        except Exception as e:
            logger.error(
                f"Failed to create ephemeral token: {str(e)}",
                exc_info=True,
            )
            raise