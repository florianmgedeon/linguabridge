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

Language detection is handled automatically by Deepgram (detect_language=true).
Detection is restricted to German ("de") and English ("en").
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
        that contains a non-empty transcript.  The dict includes a
        ``detected_language`` key with the raw language code returned by
        Deepgram (e.g. "en", "de-DE"), or an empty string if unavailable.
    """
    api_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not api_key:
        logger.error(
            "DEEPGRAM_API_KEY is not set — transcription will not work. "
            "Copy .env.example to .env and add your key."
        )
        return

    # Build the query string for the Deepgram WebSocket URL.
    # - model=nova-2          : Deepgram's best general-purpose model
    # - detect_language=true  : let Deepgram automatically detect the spoken language
    # - language=multi        : required when using detect_language; tells Deepgram
    #                           not to restrict to a single fixed language
    # NOTE: do NOT set encoding= for WebM/Opus — Deepgram reads the codec
    #       from the container header automatically.  Passing an invalid
    #       encoding value causes HTTP 400.
    # - interim_results  : send partial transcripts as the user speaks
    # - smart_format     : add punctuation and capitalisation automatically
    params = (
        f"?model=nova-2"
        f"&detect_language=true"
        f"&language=multi"
        f"&interim_results=true"
        f"&smart_format=true"
    )
    url = _DEEPGRAM_WS_URL + params
    headers = {"Authorization": f"Token {api_key}"}

    try:
        async with websockets.connect(url, additional_headers=headers) as dg_ws:
            logger.info("Deepgram WebSocket connected (detect_language=true)")

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

                    # Deepgram includes the detected language on the channel
                    # object when detect_language=true is active.
                    detected_language = msg.get("channel", {}).get("detected_language", "")

                    await on_transcript(
                        {
                            "type": "transcript",
                            "text": text,
                            "is_final": msg.get("is_final", False),
                            "speech_final": msg.get("speech_final", False),
                            "detected_language": detected_language,
                        }
                    )

            # Run sender and receiver concurrently until both finish.
            await asyncio.gather(_send_audio(), _receive_transcripts())
            logger.info("Deepgram WebSocket session ended")

    except websockets.exceptions.WebSocketException as exc:
        logger.error("Deepgram WebSocket error: %s", exc)
    except (OSError, TimeoutError) as exc:
        logger.error("Unexpected error in Deepgram stream: %s", exc)
