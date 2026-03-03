import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
def read_root():
    """Health-check endpoint – confirms the backend is up."""
    return {"status": "LinguaBridge running"}


@app.websocket("/ws/audio")
async def audio_stream(websocket: WebSocket):
    """
    Receives raw audio chunks from the browser over WebSocket.

    For each chunk it:
    - Counts the bytes received
    - Logs bytes/sec to the terminal (once per second) so you can
      see data flowing without opening DevTools
    - Sends back a small JSON acknowledgement so the browser can
      display a live "backend bytes received" counter

    No transcription or translation yet – this is pure transport.
    """
    await websocket.accept()
    logger.info("WebSocket connection opened")

    total_bytes = 0
    chunk_count = 0
    window_start = time.monotonic()
    window_bytes = 0

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

            # Acknowledge the chunk so the browser can show live stats
            await websocket.send_json({
                "type": "ack",
                "chunks_received": chunk_count,
                "bytes_received": total_bytes,
            })

    except WebSocketDisconnect:
        logger.info(
            "WebSocket closed — received %d bytes in %d chunks",
            total_bytes, chunk_count,
        )
