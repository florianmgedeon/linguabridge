import asyncio
import logging
import os
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.stt.deepgram_streaming import stream_to_deepgram
from backend.translation.openai_translate import translate_text

# Load environment variables from .env (if it exists).
# This is how we keep the Deepgram API key off of GitHub.
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS is intentionally open for local development and GitHub Codespaces.
# Restrict to specific origins before deploying to a public server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Languages the caller may request.  Any other value falls back to English.
_ALLOWED_LANGUAGES = {"en", "de"}


@app.get("/")
def read_root():
    """Health-check endpoint – confirms the backend is up."""
    return {"status": "LinguaBridge running"}


@app.websocket("/ws/audio")
async def audio_stream(websocket: WebSocket, lang: str = "en"):
    """
    Receives raw audio chunks from the browser over WebSocket.

    What this endpoint does (step by step):
    1. Accepts the WebSocket connection from the browser.
    2. Opens a second WebSocket connection to Deepgram's cloud STT service.
    3. Every audio chunk the browser sends is forwarded to Deepgram.
    4. Deepgram replies with live transcripts (partial + final).
    5. Those transcripts are sent back to the browser as JSON messages.

    Query parameters
    ----------------
    lang : str  ("en" or "de", default "en")
        The language the user is speaking.  Passed directly to Deepgram.
    """
    await websocket.accept()

    # Sanitise the language code so we only pass known values to Deepgram.
    language = lang if lang in _ALLOWED_LANGUAGES else "en"
    logger.info("WebSocket connection opened (language=%s)", language)

    # Fail fast and visibly if the API key is not configured.
    # The browser will show this message in the transcript panel.
    if not os.environ.get("DEEPGRAM_API_KEY"):
        logger.error(
            "DEEPGRAM_API_KEY is not set. "
            "Copy .env.example to .env and add your key, then restart the server."
        )
        await websocket.send_json({
            "type": "error",
            "message": (
                "⚠️ DEEPGRAM_API_KEY is not set on the server. "
                "Create a .env file in the project root with "
                "DEEPGRAM_API_KEY=your_key_here and restart the backend."
            ),
        })
        await websocket.close()
        return

    total_bytes = 0
    chunk_count = 0
    window_start = time.monotonic()
    window_bytes = 0

    # A queue that bridges the browser-receive loop and the Deepgram-send loop.
    # The main loop puts audio bytes here; stream_to_deepgram reads from it.
    audio_queue: asyncio.Queue = asyncio.Queue()

    async def _translate_and_send(text: str, source_lang: str) -> None:
        """
        Translate *text* and send the result back to the browser.

        This runs as a background task so it never blocks the main
        audio-receive loop — the user keeps seeing interim transcripts
        while we wait for OpenAI to respond.
        """
        target_lang = "de" if source_lang == "en" else "en"
        start = time.monotonic()
        try:
            translated = await translate_text(text, source_lang, target_lang)
            logger.info(
                "Translation (%.3fs): [%s→%s] %r → %r",
                time.monotonic() - start,
                source_lang,
                target_lang,
                text,
                translated,
            )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                if status == 403:
                    user_msg = "Translation service: access denied — check server logs"
                elif status == 429:
                    user_msg = "Translation rate limit reached — try again in a moment"
                else:
                    user_msg = f"Translation service error (HTTP {status}) — check server logs"
                logger.error("Translation service HTTP error %s: %s", status, exc)
            elif isinstance(exc, httpx.TimeoutException):
                user_msg = "Translation timed out — try again in a moment"
                logger.error("Translation service timeout: %s", exc)
            else:
                user_msg = "Translation failed"
                logger.error("Translation error: %s", exc)
            try:
                await websocket.send_json({"type": "translation_error", "message": user_msg})
            except Exception:  # noqa: BLE001
                pass
            return

        # translate_text returns None for unsupported languages or empty results.
        if not translated:
            return

        try:
            await websocket.send_json({
                "type": "translation",
                "original": text,
                "translated": translated,
                "source_lang": source_lang,
                "target_lang": target_lang,
            })
        except WebSocketDisconnect:
            logger.debug("Browser disconnected before translation could be sent")

    async def forward_transcript(transcript: dict) -> None:
        """
        Send a Deepgram transcript event back to the browser.

        For final (is_final=True) transcripts we also kick off a background
        translation task so the WebSocket receive loop is never blocked.
        """
        try:
            await websocket.send_json(transcript)
        except WebSocketDisconnect:
            logger.debug("Browser disconnected before transcript could be sent")
            return

        # Only translate finalised transcript chunks.
        if not transcript.get("is_final"):
            return

        text = transcript.get("text", "").strip()
        if not text:
            return

        # Determine the source language from the sanitised query-parameter value.
        # `language` is already validated as "en" or "de" earlier in audio_stream.
        source_lang = language

        # Spawn translation in the background — does not block audio streaming.
        asyncio.create_task(_translate_and_send(text, source_lang))

    # Start the Deepgram streaming task in the background so it runs
    # concurrently with receiving audio from the browser.
    dg_task = asyncio.create_task(
        stream_to_deepgram(audio_queue, forward_transcript, language=language)
    )

    try:
        while True:
            data = await websocket.receive_bytes()
            chunk_len = len(data)
            total_bytes += chunk_len
            chunk_count += 1
            window_bytes += chunk_len

            # Log throughput once per second
            now = time.monotonic()
            elapsed = now - window_start
            if elapsed >= 1.0:
                bps = window_bytes / elapsed
                logger.info(
                    "Audio stream: %.0f bytes/sec | total %d bytes | %d chunks",
                    bps, total_bytes, chunk_count,
                )
                window_bytes = 0
                window_start = now

            # Forward the audio chunk to Deepgram via the queue.
            await audio_queue.put(data)

    except WebSocketDisconnect:
        logger.info(
            "WebSocket closed — received %d bytes in %d chunks",
            total_bytes, chunk_count,
        )
    finally:
        # Signal the Deepgram task to close gracefully, then wait for it.
        await audio_queue.put(None)
        await dg_task
