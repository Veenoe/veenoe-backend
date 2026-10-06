"""Backend-owned Live policies and constrained credential setup.

Resumption state is intentionally excluded from token constraints so each browser
connection can supply its latest in-memory checkpoint without changing audio policy.
"""

import datetime
from dataclasses import dataclass
from google.genai import types


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
        """Serialize the shared VAD and interruption policy into the SDK schema."""
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
    session_duration_minutes: int = 5
    response_modalities: tuple[str, ...] = ("AUDIO",)
    session_resumption: bool = True
    input_audio_transcription: bool = True
    output_audio_transcription: bool = True
    response_fallback_voice_name: str = "Kore"
    vad_profile: GeminiVadProfile = GeminiVadProfile()

    @property
    def token_ttl_minutes(self) -> int:
        """Allow connection setup and conclusion grace beyond the viva duration."""
        # One minute to connect plus the existing two-minute conclusion grace.
        return self.session_duration_minutes + 3


def build_live_token_config(
    config: GeminiLiveConfig,
    system_instruction: str,
    tool_declarations: list[dict],
    voice_name: str | None,
    now: datetime.datetime,
) -> tuple[dict, str]:
    """Build locked setup and lifetimes, returning the effective voice for the UI."""
    live_config = {
        "response_modalities": list(config.response_modalities),
        "system_instruction": system_instruction,
        "tools": [{"function_declarations": tool_declarations}],
        # Policy is locked below; only the resumption handle is client-owned.
        "realtime_input_config": config.vad_profile.realtime_input_config(),
    }
    # The SDK automatically masks every populated constraint. Resumption
    # must therefore be supplied by the client, including its initial {}.
    if config.input_audio_transcription:
        live_config["input_audio_transcription"] = {}
    if config.output_audio_transcription:
        live_config["output_audio_transcription"] = {}
    if config.session_duration_minutes == 15:
        live_config["context_window_compression"] = {"sliding_window": {}}

    # The token owns the effective voice, including the fallback.
    effective_voice = voice_name or config.response_fallback_voice_name
    live_config["speech_config"] = {
        "voice_config": {"prebuilt_voice_config": {"voice_name": effective_voice}}
    }

    expires_at = now + datetime.timedelta(minutes=config.token_ttl_minutes)
    new_session_expires_at = now + datetime.timedelta(minutes=1)
    # An unmasked setup would ignore the client's resumption handle.
    # Lock complete policy objects, including absent optional settings,
    # while leaving sessionResumption available on each connection.
    token_config = {
        "uses": config.token_uses,
        "expire_time": expires_at,
        "new_session_expire_time": new_session_expires_at,
        "lock_additional_fields": [
            "model",
            "generationConfig",
            "systemInstruction",
            "tools",
            "realtimeInputConfig",
            "inputAudioTranscription",
            "outputAudioTranscription",
            "contextWindowCompression",
            "historyConfig",
            "proactivity",
        ],
        "live_connect_constraints": {
            "model": config.model,
            "config": live_config,
        },
    }
    return token_config, effective_voice
