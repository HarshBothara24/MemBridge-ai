"""
TTS Service — gTTS-based text-to-speech.
Supports English and Hindi output.
"""

import logging
import uuid
import os
from gtts import gTTS

logger = logging.getLogger(__name__)

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "audio")


def generate_audio(text: str, language: str) -> str:
    """
    Convert text to speech and save as MP3.
    Returns the filename (not full path) for URL construction.

    Args:
        text: Text to synthesize
        language: "en", "hi", or "mixed" (mixed uses "hi")
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)

    # gTTS lang mapping
    lang_map = {"en": "en", "hi": "hi", "mixed": "hi"}
    gtts_lang = lang_map.get(language, "en")

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)

    try:
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tts.save(filepath)
        logger.info("Audio saved: %s (lang=%s)", filename, gtts_lang)
        return filename
    except Exception as e:
        logger.error("TTS generation failed: %s", e)
        raise
