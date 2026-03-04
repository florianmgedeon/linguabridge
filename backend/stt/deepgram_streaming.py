"""
backend/stt/deepgram_streaming.py

Manages two parallel Deepgram Streaming STT WebSocket sessions —
one for German (language=de) and one for English (language=en).

Why two connections, not language=multi?
-----------------------------------------
Deepgram's ``language=multi`` (code-switching) mode uses a single
multilingual acoustic model.  In practice this model transcribes German
speech as garbled English phonemes and labels it ``detected_language: en``.
Running dedicated language-specific models in parallel and comparing their
confidence scores solves both problems at once:
  - German speech is transcribed correctly by the German model.
  - English speech is transcribed correctly by the English model.
  - Whichever model is more confident wins, giving reliable language detection
    without any unsupported Deepgram API parameter.

How it works:
1. Audio chunks are broadcast from the caller's queue to two sub-queues.
2. Two Deepgram WebSocket connections run concurrently (language=de / en).
3. Interim results (is_final=False) are forwarded from whichever language
   won the last utterance, so the user sees a responsive partial transcript.
4. When an utterance ends (speech_final=True) we wait up to _RACE_TIMEOUT
   seconds for both connections to return their final result, then forward
   the one with higher confidence.  The winner's language is remembered for
   the next interim display.
5. on_transcript is called exactly once per utterance.
"""

import asyncio
import json
import logging
import os

import websockets

logger = logging.getLogger(__name__)

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"

# How long (seconds) to wait for the second connection's speech_final result
# before using whichever one arrived first.
_RACE_TIMEOUT = 0.4


async def stream_to_deepgram(
    audio_queue: asyncio.Queue,
    on_transcript,
) -> None:
    """
    Open two parallel Deepgram WebSocket connections and invoke
    *on_transcript* with the higher-confidence result per utterance.

    Parameters
    ----------
    audio_queue : asyncio.Queue
        Audio bytes from the FastAPI handler.  Put ``None`` to end the stream.
    on_transcript : async callable
        Called with a single dict for every utterance.  The dict always has
        ``detected_language`` set to either ``"de"`` or ``"en"``.
    """
    api_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not api_key:
        logger.error(
            "DEEPGRAM_API_KEY is not set — transcription will not work. "
            "Copy .env.example to .env and add your key."
        )
        return

    # One sub-queue per language connection.
    de_queue: asyncio.Queue = asyncio.Queue()
    en_queue: asyncio.Queue = asyncio.Queue()

    # Which language's interim results to show while the user is speaking.
    # Updated (via nonlocal) to the winner after every speech_final race.
    preferred_lang: str = "de"

    # Coordination state for the speech_final confidence race.
    # _pending is either None or a dict describing the first speech_final
    # that has arrived but not yet been matched with the other connection.
    _pending: dict | None = None
    _pending_lock = asyncio.Lock()

    # ── Audio broadcaster ────────────────────────────────────────────────────

    async def _broadcast() -> None:
        """Fan out every audio chunk (and the closing None) to both sub-queues."""
        while True:
            chunk = await audio_queue.get()
            await de_queue.put(chunk)
            await en_queue.put(chunk)
            if chunk is None:
                break

    # ── Per-language connection ──────────────────────────────────────────────

    def _build_url(lang: str) -> str:
        # NOTE: do NOT set encoding= for WebM/Opus — Deepgram reads the codec
        # from the container header automatically.
        return (
            f"{_DEEPGRAM_WS_URL}?model=nova-2"
            f"&language={lang}"
            f"&interim_results=true"
            f"&smart_format=true"
        )

    async def _handle_speech_final(
        lang: str, text: str, confidence: float
    ) -> None:
        """
        Coordinate with the parallel connection to pick the better transcript.

        The first connection to call this stores its result behind the lock and
        waits _RACE_TIMEOUT seconds for the other.  The second connection (if it
        arrives in time) compares confidence scores and fires on_transcript with
        the winner.  If only one result arrives within the timeout, it wins by
        default.
        """
        nonlocal preferred_lang, _pending

        winner_lang: str | None = None
        winner_text: str | None = None
        other_confidence: float = 0.0
        event: asyncio.Event | None = None

        async with _pending_lock:
            if _pending is None:
                # First to arrive — record our result.
                event = asyncio.Event()
                _pending = {
                    "lang": lang,
                    "text": text,
                    "confidence": confidence,
                    "event": event,
                }
            else:
                # Second to arrive — pick winner and clear state.
                first = _pending
                _pending = None
                other_confidence = first["confidence"]
                if confidence > other_confidence:
                    winner_lang, winner_text = lang, text
                elif confidence < other_confidence:
                    winner_lang, winner_text = first["lang"], first["text"]
                else:
                    # Equal confidence: prefer "de" (primary user language).
                    winner_lang = "de" if "de" in (lang, first["lang"]) else lang
                    winner_text = text if winner_lang == lang else first["text"]
                first["event"].set()  # unblock the waiting first-arrival path

        if winner_lang is not None:
            # We are the second connection; fire on_transcript now.
            preferred_lang = winner_lang
            logger.info(
                "Language winner: %s (confidence %.3f vs %.3f)",
                winner_lang, confidence, other_confidence,
            )
            await on_transcript({
                "type": "transcript",
                "text": winner_text,
                "is_final": True,
                "speech_final": True,
                "detected_language": winner_lang,
            })
            return

        # We are the first connection — wait for the other or time out.
        assert event is not None
        try:
            await asyncio.wait_for(event.wait(), timeout=_RACE_TIMEOUT)
            # The second connection set the event and already called on_transcript.
        except asyncio.CancelledError:
            # Task cancelled during shutdown — propagate after clearing pending.
            async with _pending_lock:
                if _pending is not None and _pending.get("event") is event:
                    _pending = None
            raise
        except asyncio.TimeoutError:
            # The other connection didn't respond in time.  Check whether it
            # slipped in just after our timeout but before we re-acquired the lock.
            async with _pending_lock:
                if _pending is None:
                    return  # other side handled it
                _pending = None
            preferred_lang = lang
            logger.info(
                "Language winner (timeout, no second result): %s (confidence %.3f)",
                lang, confidence,
            )
            await on_transcript({
                "type": "transcript",
                "text": text,
                "is_final": True,
                "speech_final": True,
                "detected_language": lang,
            })

    async def _run(lang: str, queue: asyncio.Queue) -> None:
        """Open one Deepgram connection for *lang* and process its results."""
        url = _build_url(lang)
        headers = {"Authorization": f"Token {api_key}"}

        try:
            async with websockets.connect(
                url, additional_headers=headers
            ) as dg_ws:
                logger.info("Deepgram connected (language=%s)", lang)

                async def _send() -> None:
                    while True:
                        chunk = await queue.get()
                        if chunk is None:
                            await dg_ws.send(json.dumps({"type": "CloseStream"}))
                            break
                        await dg_ws.send(chunk)

                async def _recv() -> None:
                    async for raw in dg_ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            logger.warning(
                                "[%s] Non-JSON from Deepgram: %r", lang, raw
                            )
                            continue

                        if msg.get("type") != "Results":
                            continue

                        channel = msg.get("channel", {})
                        alts = channel.get("alternatives", [{}])
                        text = alts[0].get("transcript", "") if alts else ""
                        if not text:
                            continue

                        confidence = alts[0].get("confidence", 0.0) if alts else 0.0
                        is_final = msg.get("is_final", False)
                        speech_final = msg.get("speech_final", False)

                        if speech_final:
                            # Coordinate with the other connection.
                            await _handle_speech_final(lang, text, confidence)
                        elif preferred_lang == lang:
                            # Only forward non-final events from the preferred
                            # language to avoid duplicates in the UI.
                            await on_transcript({
                                "type": "transcript",
                                "text": text,
                                "is_final": is_final,
                                "speech_final": False,
                                "detected_language": lang,
                            })

                await asyncio.gather(_send(), _recv())
                logger.info("Deepgram session ended (language=%s)", lang)

        except websockets.exceptions.WebSocketException as exc:
            logger.error("Deepgram WebSocket error (%s): %s", lang, exc)
        except (OSError, TimeoutError) as exc:
            logger.error("Deepgram stream error (%s): %s", lang, exc)

    await asyncio.gather(
        _broadcast(),
        _run("de", de_queue),
        _run("en", en_queue),
    )
