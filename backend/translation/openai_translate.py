"""
backend/translation/openai_translate.py

Translates text between English and German using the MyMemory API.

Plain-English explanation:
- MyMemory (https://mymemory.translated.net) is a completely free translation
  service — no account, no API key, and no quota limits for normal use.
- We send a simple GET request with the text and language pair and get back
  the translated sentence.
- The function returns the translated string, or None if translation is not
  applicable (e.g. unsupported language).
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Languages we support for translation.
_SUPPORTED_LANGS = {"en", "de"}

# MyMemory public translation endpoint — no API key needed.
# Override with MYMEMORY_URL environment variable if needed (e.g. for testing).
_DEFAULT_MYMEMORY_URL = "https://api.mymemory.translated.net/get"

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
    Translate *text* from *source_lang* to *target_lang* using MyMemory.

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

    url = os.environ.get("MYMEMORY_URL", _DEFAULT_MYMEMORY_URL)
    params = {
        "q": text,
        "langpair": f"{source_lang}|{target_lang}",
    }

    client = _get_http_client()
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    # MyMemory returns a numeric responseStatus (200 = success).
    if data.get("responseStatus") != 200:
        logger.warning(
            "Translation service non-200 status %s: %s",
            data.get("responseStatus"),
            data.get("responseDetails"),
        )
        return None

    translated = data.get("responseData", {}).get("translatedText", "").strip()
    return translated if translated else None
