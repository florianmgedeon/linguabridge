"""
backend/tts/elevenlabs_tts.py

Generates speech audio from text using the ElevenLabs Text-to-Speech API
(non-streaming — the full audio file is returned in a single HTTP response).

Plain-English explanation:
- ElevenLabs (https://elevenlabs.io) is a cloud service that turns written
  text into spoken audio.  We send a sentence and get back an MP3 file.
- "Non-streaming" means we wait for the whole audio file before sending it
  to the browser — simpler than streaming but adds a small delay.
- We pick a voice based on the target language (EN or DE) using env vars.
  If no voice is configured, a built-in default voice is used.

Environment variables (all optional except ELEVENLABS_API_KEY):
  ELEVENLABS_API_KEY       — your secret key from https://elevenlabs.io
  ELEVENLABS_VOICE_ID_EN   — ElevenLabs voice ID to use for English output
  ELEVENLABS_VOICE_ID_DE   — ElevenLabs voice ID to use for German output
  ELEVENLABS_VOICE_ID      — fallback voice ID used when the language-specific
                              one is not set
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# A stable default voice (ElevenLabs built-in "Rachel" — English, neutral).
# This is used only when no voice ID is provided via environment variables.
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

# ElevenLabs TTS REST endpoint — {voice_id} is substituted at call time.
_TTS_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Shared async HTTP client — created once and reused across requests so that
# we do not open a new TCP connection for every TTS call.
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return (and lazily create) the shared async HTTP client."""
    global _http_client
    if _http_client is None:
        # 30-second timeout — ElevenLabs can take a moment for longer texts.
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def _pick_voice(lang: str) -> str:
    """
    Return the best ElevenLabs voice ID for *lang*.

    Priority order:
    1. Language-specific env var  (ELEVENLABS_VOICE_ID_EN / _DE)
    2. Generic fallback env var   (ELEVENLABS_VOICE_ID)
    3. Hard-coded default constant (_DEFAULT_VOICE_ID)
    """
    if lang == "en":
        voice = os.environ.get("ELEVENLABS_VOICE_ID_EN")
    elif lang == "de":
        voice = os.environ.get("ELEVENLABS_VOICE_ID_DE")
    else:
        voice = None

    return voice or os.environ.get("ELEVENLABS_VOICE_ID") or _DEFAULT_VOICE_ID


async def generate_tts_audio(text: str, lang: str) -> tuple[bytes, str] | None:
    """
    Convert *text* to speech audio using ElevenLabs (non-streaming).

    Parameters
    ----------
    text : str
        The sentence to speak.  Whitespace is stripped automatically.
    lang : str
        Target language code — ``"en"`` or ``"de"``.  Used to pick the voice.

    Returns
    -------
    tuple[bytes, str] | None
        ``(audio_bytes, mime_type)`` on success — the raw MP3 bytes and the
        string ``"audio/mpeg"``.
        ``None`` if *text* is empty or ``ELEVENLABS_API_KEY`` is not set.

    Raises
    ------
    httpx.HTTPStatusError
        If ElevenLabs returns a non-2xx response (e.g. bad API key, quota
        exceeded).  The caller is responsible for handling this.
    """
    text = text.strip()
    if not text:
        return None

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        logger.warning(
            "ELEVENLABS_API_KEY is not set — skipping TTS. "
            "Add the key to your .env file to enable speech output."
        )
        return None

    voice_id = _pick_voice(lang)
    url = _TTS_URL_TEMPLATE.format(voice_id=voice_id)

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    # eleven_multilingual_v2 supports both English and German natively.
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
    }

    client = _get_http_client()
    logger.debug("Calling ElevenLabs TTS (voice=%s, lang=%s): %r", voice_id, lang, text)
    response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.content, "audio/mpeg"
