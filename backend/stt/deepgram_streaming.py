"""
backend/stt/deepgram_streaming.py

Manages a single Deepgram Streaming STT WebSocket session.

How it works (plain English):
1. The browser sends raw audio chunks to our FastAPI backend.
2. This module opens its own WebSocket connection to Deepgram's cloud servers.
3. Every audio chunk we receive from the browser gets forwarded to Deepgram.
4. Deepgram listens and sends back JSON messages with recognised words — both
   "interim" (partial, may still change) and "final" (the speaker finished a
   chunk of speech).
5. We call a callback function for each message so the FastAPI handler can
   forward it back to the browser.

Supported languages: "en" (English) or "de" (German).
"""

import asyncio
import json
import logging
import os

import websockets

logger = logging.getLogger(__name__)

# Deepgram's live-transcription endpoint
_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


async def stream_to_deepgram(
    audio_queue: asyncio.Queue,
    on_transcript,
    language: str = "en",
) -> None:
    """
    Open a WebSocket to Deepgram, relay audio chunks, and invoke
    *on_transcript* for each transcript event received.

    Parameters
    ----------
    audio_queue : asyncio.Queue
        Audio bytes are put here by the FastAPI handler.
        Put ``None`` to signal that the stream has ended.
    on_transcript : async callable
        Called with a single dict argument for every Deepgram Results message
        that contains a non-empty transcript.
    language : str
        BCP-47 language code accepted by Deepgram.  We only use "en" or "de".
    """
    api_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not api_key:
        logger.error(
            "DEEPGRAM_API_KEY is not set — transcription will not work. "
            "Copy .env.example to .env and add your key."
        )
        return

    # Build the query string for the Deepgram WebSocket URL.
    # - model=nova-2     : Deepgram's best general-purpose model
    # - language         : "en" or "de"
    # - encoding=webm    : audio comes from browser MediaRecorder (WebM/Opus)
    # - interim_results  : send partial transcripts as the user speaks
    # - smart_format     : add punctuation and capitalisation automatically
    params = (
        f"?model=nova-2"
        f"&language={language}"
        f"&encoding=webm"
        f"&interim_results=true"
        f"&smart_format=true"
    )
    url = _DEEPGRAM_WS_URL + params
    headers = {"Authorization": f"Token {api_key}"}

    try:
        async with websockets.connect(url, additional_headers=headers) as dg_ws:
            logger.info("Deepgram WebSocket connected (language=%s)", language)

            async def _send_audio() -> None:
                """Pull audio chunks from the queue and forward them to Deepgram."""
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        # None is our sentinel value — tell Deepgram we are done.
                        await dg_ws.send(json.dumps({"type": "CloseStream"}))
                        break
                    await dg_ws.send(chunk)

            async def _receive_transcripts() -> None:
                """
                Listen for messages from Deepgram and call on_transcript
                whenever we get actual words back.
                """
                async for raw in dg_ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Deepgram sent non-JSON message: %r", raw)
                        continue

                    # We only care about "Results" messages.
                    if msg.get("type") != "Results":
                        continue

                    alternatives = (
                        msg.get("channel", {})
                        .get("alternatives", [{}])
                    )
                    text = alternatives[0].get("transcript", "") if alternatives else ""

                    # Skip empty transcripts (silence / noise).
                    if not text:
                        continue

                    await on_transcript(
                        {
                            "type": "transcript",
                            "text": text,
                            "is_final": msg.get("is_final", False),
                            "speech_final": msg.get("speech_final", False),
                            "language": language,
                        }
                    )

            # Run sender and receiver concurrently until both finish.
            await asyncio.gather(_send_audio(), _receive_transcripts())
            logger.info("Deepgram WebSocket session ended (language=%s)", language)

    except websockets.exceptions.WebSocketException as exc:
        logger.error("Deepgram WebSocket error: %s", exc)
    except (OSError, TimeoutError) as exc:
        logger.error("Unexpected error in Deepgram stream: %s", exc)
