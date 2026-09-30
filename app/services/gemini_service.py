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
import time
from dataclasses import dataclass
import google.genai as genai
from google.genai import types
from app.core.config import settings
from app.schemas.viva import VivaStartRequest
from app.services.assessment_prompt import build_assessment_instruction
from app.interfaces.llm_client import LLMClient

# Configure module-level logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeminiVadProfile:
    """Single backend-owned server VAD policy for a Live token."""

    name: str = "balanced-v1"
    start_sensitivity: types.StartSensitivity = (
        types.StartSensitivity.START_SENSITIVITY_HIGH
    )
    end_sensitivity: types.EndSensitivity = types.EndSensitivity.END_SENSITIVITY_LOW
    prefix_padding_ms: int = 40
    silence_duration_ms: int = 700
    activity_handling: types.ActivityHandling = (
        types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    )

    def realtime_input_config(self) -> types.RealtimeInputConfig:
        return types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                start_of_speech_sensitivity=self.start_sensitivity,
                end_of_speech_sensitivity=self.end_sensitivity,
                prefix_padding_ms=self.prefix_padding_ms,
                silence_duration_ms=self.silence_duration_ms,
            ),
            activity_handling=self.activity_handling,
        )


@dataclass(frozen=True)
class GeminiLiveConfig:
    """Backend-owned settings for the existing Gemini Live contract."""

    model: str = "gemini-3.8-live"
    api_version: str = "v1beta"
    token_uses: int = 1
    token_ttl_minutes: int = 15
    response_modalities: tuple[str, ...] = ("AUDIO",)
    session_resumption: bool = True
    input_audio_transcription: bool = True
    output_audio_transcription: bool = True
    response_fallback_voice_name: str = "Kore"
    vad_profile: GeminiVadProfile = GeminiVadProfile()


class GeminiTokenCreationError(RuntimeError):
    """Sanitized failure raised when Gemini rejects token creation."""


GEMINI_LIVE_CONFIG = GeminiLiveConfig()


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
    MODEL_NAME = GEMINI_LIVE_CONFIG.model

    # ----------------------------------------------------------------------
    # Tool Declaration: conclude_viva
    # ----------------------------------------------------------------------
    # This tool is exposed to the AI and must be called at the end of
    # the viva session with detailed evaluation metadata.
    _CONCLUDE_VIVA_TOOL = {
        "name": "conclude_viva",
        # 3.8 defaults to non-blocking calls; conclusion must follow spoken closing.
        "behavior": "BLOCKING",
        "description": (
            "Call this tool to END the viva session. You MUST provide a score, "
            "summary, strengths, development areas and session evidence AFTER the spoken closing."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "next_steps": {
                    "type": "ARRAY", "maxItems": 3,
                    "items": {"type": "STRING", "minLength": 1, "maxLength": 600},
                    "description": (
                        "Up to three prioritized, class-appropriate practice actions tied to "
                        "session evidence. Each says what to practise and how to check progress. "
                        "Use simple available materials; parents can prompt without giving answers. "
                        "Empty when there is insufficient evidence for advice."
                    ),
                },
                "coverage_note": {
                    "type": "STRING", "minLength": 1, "maxLength": 600,
                    "description": (
                        "Brief scope and limits: topic/concepts explored, important skills not "
                        "tested, and that this is one short session rather than overall mastery."
                    ),
                },
                "score": {
                    "type": "INTEGER",
                    "minimum": 0,
                    "maximum": 10,
                    "description": (
                        "Final score out of 10 based on technical accuracy "
                        "and explanation; secondary compatibility field, never speaking fluency."
                    ),
                },
                "summary": {
                    "type": "STRING",
                    "minLength": 1,
                    "maxLength": 2000,
                    "description": (
                        "Parent-readable summary of topic coverage and demonstrated reasoning. "
                        "Distinguish independent answers from meaningful hints, mention observed "
                        "misconceptions/corrections and coverage gaps. One short session only; "
                        "never infer fixed ability. This is the written report, not the spoken goodbye."
                    ),
                },
                "strong_points": {
                    "type": "ARRAY",
                    "maxItems": 5,
                    "items": {"type": "STRING", "minLength": 1, "maxLength": 600},
                    "description": (
                        "Up to five specific concepts or reasoning behaviors demonstrated, "
                        "with concise session evidence and any meaningful assistance; "
                        "empty if none observed."
                    ),
                },
                "areas_of_improvement": {
                    "type": "ARRAY",
                    "maxItems": 5,
                    "items": {"type": "STRING", "minLength": 1, "maxLength": 600},
                    "description": (
                        "Up to five specific learning gaps demonstrated in the answers. "
                        "Describe what remains unclear, recognizing later corrections; "
                        "never penalize untested skills; "
                        "empty if insufficient evidence."
                    ),
                },
            },
            "required": [
                "score",
                "summary",
                "strong_points",
                "areas_of_improvement",
                "next_steps",
                "coverage_note",
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
        return build_assessment_instruction(viva_request)

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
        started_at = time.perf_counter()
        config = GEMINI_LIVE_CONFIG
        logger.info(
            "event=gemini_ephemeral_token_attempt model=%s api_version=%s token_uses=%d token_ttl_minutes=%d vad_profile=%s",
            config.model,
            config.api_version,
            config.token_uses,
            config.token_ttl_minutes,
            config.vad_profile.name,
        )

        try:
            # A new client is created per request to maintain async safety.
            client = genai.Client(
                api_key=self._api_key,
                http_options={"api_version": config.api_version},
            )

            # Build system instructions and tool declarations.
            system_instruction = self.generate_system_instruction(viva_request)
            tool_declarations = [self._CONCLUDE_VIVA_TOOL]

            # Base configuration passed to the Gemini Live API.
            live_config = {
                "response_modalities": list(config.response_modalities),
                "system_instruction": system_instruction,
                "tools": [{"function_declarations": tool_declarations}],
                # No field mask: this token setup is authoritative, including VAD.
                "realtime_input_config": config.vad_profile.realtime_input_config(),
            }
            if config.session_resumption:
                live_config["session_resumption"] = {}
            if config.input_audio_transcription:
                live_config["input_audio_transcription"] = {}
            if config.output_audio_transcription:
                live_config["output_audio_transcription"] = {}

            # The token owns the effective voice, including the fallback.
            effective_voice = (
                viva_request.voice_name or config.response_fallback_voice_name
            )
            live_config["speech_config"] = {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": effective_voice}
                }
            }

            # Token configuration: one-time use, expires in 15 minutes.
            token_config = {
                "uses": config.token_uses,
                "expire_time": (
                    datetime.datetime.now(tz=datetime.timezone.utc)
                    + datetime.timedelta(minutes=config.token_ttl_minutes)
                ),
                "live_connect_constraints": {
                    "model": config.model,
                    "config": live_config,
                },
            }

            # Create ephemeral token asynchronously.
            token = await client.aio.auth_tokens.create(config=token_config)

            duration_ms = round((time.perf_counter() - started_at) * 1000)
            logger.info(
                "event=gemini_ephemeral_token_created duration_ms=%d model=%s api_version=%s token_uses=%d token_ttl_minutes=%d vad_profile=%s",
                duration_ms,
                config.model,
                config.api_version,
                config.token_uses,
                config.token_ttl_minutes,
                config.vad_profile.name,
            )

            return {
                "token": token.name,
                "voice_name": effective_voice,
                "session_duration_minutes": 5,
                "model_name": self.MODEL_NAME,
                "vad_profile": config.vad_profile.name,
            }

        except Exception as e:
            logger.error(
                "event=gemini_ephemeral_token_failed error_type=%s duration_ms=%d model=%s api_version=%s vad_profile=%s",
                type(e).__name__,
                round((time.perf_counter() - started_at) * 1000),
                config.model,
                config.api_version,
                config.vad_profile.name,
            )
            raise GeminiTokenCreationError(
                "Gemini ephemeral token creation failed"
            ) from None
