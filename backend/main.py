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
from backend.tts.elevenlabs_tts import generate_tts_audio

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

# ── Language detection constants ─────────────────────────────────────────────
# Minimum transcript length / word count required before we trust the detected
# language and switch.  Short utterances ("OK", "ja") can be ambiguous, so we
# keep the last confirmed language for those.
MIN_TEXT_LENGTH_FOR_LANG_CONFIRM = 8
MIN_WORDS_FOR_LANG_CONFIRM = 2


def normalize_language(lang_string: str) -> str:
    """
    Convert a Deepgram language code into a simple two-letter code.

    Why this function exists (plain English):
    Deepgram sometimes returns extended codes like "en-US" or "de-AT"
    instead of just "en" or "de".  We strip the regional suffix so
    the rest of the code only ever has to deal with "en", "de", or "unknown".

    Examples:
        en-US → en
        en-GB → en
        de-DE → de
        de-AT → de
        fr-FR → unknown  (unsupported language)
        ""    → unknown
    """
    if not lang_string:
        return "unknown"
    lang = lang_string.lower()
    if lang.startswith("de"):
        return "de"
    if lang.startswith("en"):
        return "en"
    return "unknown"


@app.get("/")
def read_root():
    """Health-check endpoint – confirms the backend is up."""
    return {"status": "LinguaBridge running"}


@app.websocket("/ws/audio")
async def audio_stream(websocket: WebSocket):
    """
    Receives raw audio chunks from the browser over WebSocket.

    What this endpoint does (step by step):
    1. Accepts the WebSocket connection from the browser.
    2. Opens a second WebSocket connection to Deepgram's cloud STT service
       with automatic language detection enabled.
    3. Every audio chunk the browser sends is forwarded to Deepgram.
    4. Deepgram replies with live transcripts (partial + final) including
       the detected language for each final chunk.
    5. The detected language is normalised to "en" or "de" and used to
       set the translation direction automatically (de→en or en→de).
    6. Transcripts and translations are sent back to the browser as JSON.
    """
    await websocket.accept()

    logger.info("WebSocket connection opened")

    # Per-connection language state.  Starts as "en" so the very first
    # utterance always produces a translation even if detection is uncertain.
    last_confirmed_language = "en"

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

    # Incrementing counter used to correlate tts_start headers with their
    # binary audio frames.  A list is used so the nested closure can mutate it.
    _tts_counter = [0]

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

        # Assign a simple incrementing ID so the frontend can match the
        # tts_start header to the binary audio frame that follows it.
        _tts_counter[0] += 1
        tts_id = _tts_counter[0]

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
            return

        # ── TTS: generate audio for the translated text and stream it back ──
        try:
            tts_result = await generate_tts_audio(translated, target_lang)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 402:
                logger.error(
                    "TTS failed (402 Payment Required) — the configured voice ID "
                    "requires a paid ElevenLabs plan. Remove ELEVENLABS_VOICE_ID_EN, "
                    "ELEVENLABS_VOICE_ID_DE, and ELEVENLABS_VOICE_ID from your .env "
                    "to use the free built-in default voice."
                )
            else:
                logger.error("TTS generation failed (HTTP %s): %s", status, exc)
            tts_result = None
        except Exception as exc:  # noqa: BLE001
            logger.error("TTS generation failed: %s", exc)
            tts_result = None

        if tts_result is not None:
            audio_bytes, mime_type = tts_result
            try:
                # Send a JSON header first so the browser knows what's coming.
                await websocket.send_json({
                    "type": "tts_start",
                    "audio_format": "mp3",
                    "mime": mime_type,
                    "target_lang": target_lang,
                    "id": tts_id,
                })
                # Then send the raw MP3 bytes as a binary WebSocket frame.
                await websocket.send_bytes(audio_bytes)
                logger.info(
                    "TTS sent (id=%d, lang=%s, %d bytes)",
                    tts_id, target_lang, len(audio_bytes),
                )
            except WebSocketDisconnect:
                logger.debug("Browser disconnected before TTS audio could be sent")

    async def forward_transcript(transcript: dict) -> None:
        """
        Send a Deepgram transcript event back to the browser.

        For final (is_final=True) transcripts we also:
        - Determine the confirmed language using Deepgram's detected language
          and a stability policy (short/unclear utterances keep the last known
          language rather than switching).
        - Kick off a background translation task so the WebSocket receive loop
          is never blocked.
        """
        nonlocal last_confirmed_language

        is_final = transcript.get("is_final", False)
        text = transcript.get("text", "").strip()
        source_lang = None

        if is_final and text:
            # Step 1: read and normalise the language Deepgram detected.
            detected_lang_raw = transcript.get("detected_language", "")
            normalized = normalize_language(detected_lang_raw)
            logger.info(
                "Deepgram detected language: %r → normalised: %r",
                detected_lang_raw, normalized,
            )

            # Step 2: apply the stability policy.
            # We only switch to the detected language if the utterance is long
            # enough to be reliable.  Short clips ("OK", "ja") stay on the
            # last confirmed language to avoid jittery direction changes.
            if normalized in ("de", "en"):
                word_count = len(text.split())
                if (len(text) >= MIN_TEXT_LENGTH_FOR_LANG_CONFIRM
                        or word_count >= MIN_WORDS_FOR_LANG_CONFIRM):
                    last_confirmed_language = normalized

            # Step 3: use the (possibly unchanged) confirmed language.
            source_lang = last_confirmed_language
            target_lang = "en" if source_lang == "de" else "de"

            # Enrich the transcript message with language metadata so the
            # frontend can display the detected language and direction.
            msg_to_send = {
                **transcript,
                "detected_lang": source_lang,
                "target_lang": target_lang,
            }
        else:
            msg_to_send = transcript

        try:
            await websocket.send_json(msg_to_send)
        except WebSocketDisconnect:
            logger.debug("Browser disconnected before transcript could be sent")
            return

        # Only translate finalised transcript chunks.
        if source_lang is None:
            return

        # Spawn translation in the background — does not block audio streaming.
        asyncio.create_task(_translate_and_send(text, source_lang))

    # Start the Deepgram streaming task in the background so it runs
    # concurrently with receiving audio from the browser.
    dg_task = asyncio.create_task(
        stream_to_deepgram(audio_queue, forward_transcript)
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
