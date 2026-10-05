"""Verify constrained token creation and real Live resumption without session writes.

Uses the backend's configured Google credential and model. Only technical stage
names are printed; provider payloads, transcripts and credentials remain private.
Run from the backend root with DYNAMODB_TABLE_NAME set, as required by Settings.
"""

import asyncio
import sys

from google import genai
from google.genai import types

from app.schemas.viva import VivaStartRequest
from app.services.gemini_service import GeminiService


async def smoke() -> None:
    """Require provider setup acknowledgments and reuse one credential to resume."""
    token = await GeminiService().create_ephemeral_token(
        VivaStartRequest(student_name="Smoke Test", topic="Plants", class_level="7")
    )
    print("ephemeral_token_created", flush=True)
    client = genai.Client(
        api_key=token["token"],
        http_options={"api_version": token["google_api_version"]},
    )
    try:
        async with asyncio.timeout(30):
            handle = None
            turn_complete = False
            async with client.aio.live.connect(
                model=token["model_name"],
                config=types.LiveConnectConfig(session_resumption={}),
            ) as session:
                if session.setup_complete is None:
                    raise RuntimeError("Live setup was not acknowledged")
                print("live_connected", flush=True)
                await session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[
                            types.Part(text="Application control: Begin the viva now.")
                        ],
                    ),
                    turn_complete=True,
                )
                while not (handle and turn_complete):
                    async for message in session.receive():
                        if (
                            message.server_content
                            and message.server_content.turn_complete
                        ):
                            turn_complete = True
                            print("opening_turn_complete", flush=True)
                        update = message.session_resumption_update
                        if update and update.resumable and update.new_handle:
                            handle = update.new_handle
                        if handle and turn_complete:
                            break
            print("checkpoint_received", flush=True)
            async with client.aio.live.connect(
                model=token["model_name"],
                config=types.LiveConnectConfig(session_resumption={"handle": handle}),
            ) as resumed:
                if resumed.setup_complete is None:
                    raise RuntimeError("Live resumption was not acknowledged")
                print("live_resumed", flush=True)
    finally:
        await client.aio.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(smoke())
    except Exception as error:
        # Error messages and tracebacks may embed auth URLs or provider payloads.
        print(f"smoke_failed error_type={type(error).__name__}", file=sys.stderr)
        sys.exit(1)
