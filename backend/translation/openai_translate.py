"""
backend/translation/openai_translate.py

Translates text between English and German using the OpenAI Chat Completions API.

Plain-English explanation:
- We send the text to OpenAI's GPT model together with instructions that say
  "you are a professional translator — only return the translated sentence".
- The function returns the translated string, or None if translation is not
  applicable (e.g. unsupported language).
"""

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Human-readable names used in the translation prompt.
_LANG_NAMES = {"en": "English", "de": "German"}

# A single shared async client — created once and reused for all requests.
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Return (and lazily create) the shared AsyncOpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


async def translate_text(text: str, source_lang: str, target_lang: str) -> str | None:
    """
    Translate *text* from *source_lang* to *target_lang* using OpenAI.

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
    if source_lang not in _LANG_NAMES or target_lang not in _LANG_NAMES:
        return None

    source_name = _LANG_NAMES[source_lang]
    target_name = _LANG_NAMES[target_lang]

    client = _get_client()
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional translator. Translate naturally and "
                    "conversationally. Only return the translated sentence. "
                    "Do not add explanations."
                ),
            },
            {
                "role": "user",
                "content": f"Translate from {source_name} to {target_name}:\n\n{text}",
            },
        ],
        temperature=0.2,
        max_tokens=200,
    )

    translated = response.choices[0].message.content.strip() if response.choices else ""
    return translated if translated else None
