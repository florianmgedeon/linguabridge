"""
backend/translation/openai_translate.py

Translates text between English and German using the LibreTranslate API.

Plain-English explanation:
- We send the text to a LibreTranslate server (free, no quota, no API key required).
- The function returns the translated string, or None if translation is not
  applicable (e.g. unsupported language).
- The server URL defaults to the public instance (https://libretranslate.com)
  but can be overridden with the LIBRETRANSLATE_URL environment variable if
  you want to run your own self-hosted instance.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Languages we support for translation.
_SUPPORTED_LANGS = {"en", "de"}

# Public LibreTranslate endpoint (no API key needed for basic usage).
_DEFAULT_URL = "https://libretranslate.com"

# Shared async HTTP client — created once and reused for all requests to avoid
# the overhead of opening a new TCP connection on every translation call.
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return (and lazily create) the shared async HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def translate_text(text: str, source_lang: str, target_lang: str) -> str | None:
    """
    Translate *text* from *source_lang* to *target_lang* using LibreTranslate.

    Parameters
    ----------
    text : str
        The sentence to translate.
    source_lang : str
        BCP-47 language code of the source — must be "en" or "de".
    target_lang : str
        BCP-47 language code of the target — must be "en" or "de".

    Returns
    -------
    str | None
        The translated string, or None if translation is not supported
        (unknown source language).  Returns the original text unchanged if
        source and target are the same language.
    """
    # Nothing to do if source and target are the same.
    if source_lang == target_lang:
        return text

    # We only support English ↔ German.
    if source_lang not in _SUPPORTED_LANGS or target_lang not in _SUPPORTED_LANGS:
        return None

    base_url = os.environ.get("LIBRETRANSLATE_URL", _DEFAULT_URL).rstrip("/")
    api_key = os.environ.get("LIBRETRANSLATE_API_KEY", "")

    payload: dict = {
        "q": text,
        "source": source_lang,
        "target": target_lang,
        "format": "text",
    }
    if api_key:
        payload["api_key"] = api_key

    client = _get_http_client()
    response = await client.post(f"{base_url}/translate", json=payload)
    response.raise_for_status()
    data = response.json()

    translated = data.get("translatedText", "").strip()
    return translated if translated else None
