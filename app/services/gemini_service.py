"""Provision constrained Live credentials and the assessment prompt for browser vivas.

Audio is streamed directly by the client; this service never owns a Live socket.
Provider clients are request-scoped and failures expose only sanitized diagnostics.
"""

import logging
import datetime
import time
from dataclasses import replace
import google.genai as genai
from app.core.config import settings
from app.schemas.viva import VivaStartRequest
from app.services.assessment_prompt import build_assessment_instruction
from app.services.gemini_live_config import (
    GeminiLiveConfig,
    build_live_token_config,
)

logger = logging.getLogger(__name__)


class GeminiTokenCreationError(RuntimeError):
    """Sanitized failure raised when Gemini rejects token creation."""


GEMINI_LIVE_CONFIG = GeminiLiveConfig()


class GeminiService:
    """Mint credentials using a settings snapshot and the backend-owned assessment policy."""

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
                    "type": "ARRAY",
                    "maxItems": 3,
                    "items": {"type": "STRING", "minLength": 1, "maxLength": 600},
                    "description": (
                        "Up to three prioritized, class-appropriate practice actions tied to "
                        "session evidence. Each says what to practise and how to check progress. "
                        "Use simple available materials; parents can prompt without giving answers. "
                        "Empty when there is insufficient evidence for advice."
                    ),
                },
                "coverage_note": {
                    "type": "STRING",
                    "minLength": 1,
                    "maxLength": 600,
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

    def __init__(self) -> None:
        """
        Initialize the GeminiService.

        Loads the Google API key from application settings and prepares
        the service instance for model interactions.
        """
        self._api_key = settings.GOOGLE_API_KEY
        self._config = replace(
            GEMINI_LIVE_CONFIG,
            model=settings.GEMINI_LIVE_MODEL,
            session_duration_minutes=settings.VIVA_SESSION_DURATION_MINUTES,
        )

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
        return build_assessment_instruction(
            viva_request, self._config.session_duration_minutes
        )

    async def create_ephemeral_token(self, viva_request: VivaStartRequest) -> dict:
        """
        Create a secure, short-lived ephemeral token allowing the
        client to connect to the Google Gemini Live API.

        This token:
        - Starts one new session; the same credential can resume that session.
        - Covers the configured duration and a bounded conclusion grace period.
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
            - API version, credential deadlines, and resumption capability

        Raises
        ------
        GeminiTokenCreationError
            Provider failures are sanitized; credentials and raw payloads are never logged.
        """
        started_at = time.perf_counter()
        config = self._config
        logger.info(
            "event=gemini_ephemeral_token_attempt model=%s api_version=%s token_uses=%d token_ttl_minutes=%d vad_profile=%s",
            config.model,
            config.api_version,
            config.token_uses,
            config.token_ttl_minutes,
            config.vad_profile.name,
        )

        client = None
        try:
            # A new client is created per request to maintain async safety.
            client = genai.Client(
                api_key=self._api_key,
                http_options={"api_version": config.api_version},
            )

            system_instruction = self.generate_system_instruction(viva_request)
            tool_declarations = [self._CONCLUDE_VIVA_TOOL]

            token_config, effective_voice = build_live_token_config(
                config,
                system_instruction,
                tool_declarations,
                viva_request.voice_name,
                datetime.datetime.now(tz=datetime.timezone.utc),
            )
            expires_at = token_config["expire_time"]
            new_session_expires_at = token_config["new_session_expire_time"]

            token = await client.aio.auth_tokens.create(config=token_config)
            if not isinstance(token.name, str) or not token.name.strip():
                raise GeminiTokenCreationError("Gemini returned an empty credential")

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
                "session_duration_minutes": config.session_duration_minutes,
                "model_name": config.model,
                "vad_profile": config.vad_profile.name,
                "google_api_version": config.api_version,
                "token_expires_at": expires_at,
                "new_session_expires_at": new_session_expires_at,
                "session_resumption_enabled": config.session_resumption,
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
        finally:
            if client is not None:
                try:
                    await client.aio.aclose()
                except Exception:
                    logger.warning("event=gemini_client_cleanup_failed")
