import asyncio
import logging
import time

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.stt.deepgram_streaming import stream_to_deepgram

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

    total_bytes = 0
    chunk_count = 0
    window_start = time.monotonic()
    window_bytes = 0

    # A queue that bridges the browser-receive loop and the Deepgram-send loop.
    # The main loop puts audio bytes here; stream_to_deepgram reads from it.
    audio_queue: asyncio.Queue = asyncio.Queue()

    async def forward_transcript(transcript: dict) -> None:
        """Send a Deepgram transcript event back to the browser."""
        try:
            await websocket.send_json(transcript)
        except WebSocketDisconnect:
            logger.debug("Browser disconnected before transcript could be sent")

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
