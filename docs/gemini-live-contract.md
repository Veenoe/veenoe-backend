# Gemini Live contract

## Tested contract

- Date: 2026-09-26
- Model: `gemini-3.8-live`
- Live API version: `v1beta`
- JavaScript SDK: `@google/genai` 2.24.0
- Python SDK: `google-genai` 2.25.0

## Architecture

The backend provisions a constrained ephemeral token. The browser receives the token and connects directly to Gemini Live. The permanent Google API key stays backend-only.

## Compatibility decisions

- `conclude_viva` is `BLOCKING` because Gemini 3.8 Live defaults to non-blocking function calls. This preserves the required order: Gemini speaks the final summary, then invokes the tool. Veenoe's client sends the result to its own backend and finishes after audio playback; it does not send a Gemini function response.
- Text input uses a structured `user` content turn with `turnComplete: true`.
- Existing Puck client voice and Kore fallback response metadata remain unchanged.
- AUDIO responses, input/output transcription, and session resumption stay in the backend token constraints.

## Verification

- Backend Gemini service tests: 4 passed. Full backend suite: 24 passed; 6 packaging tests require the Lambda ZIP artifact.
- Webapp tests: 17 passed; TypeScript and production build passed. Repository lint still reports existing errors outside modified files.
- Developer manually verified: start viva → token → direct Live connection → voice conversation → `conclude_viva` → session completion.
