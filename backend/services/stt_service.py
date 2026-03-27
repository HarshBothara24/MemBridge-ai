"""
STT Service — Whisper-based multilingual speech-to-text.
Supports English, Hindi, and Hinglish.
"""

import logging
import whisper
import os

logger = logging.getLogger(__name__)

_model = None

def _get_model():
    global _model
    if _model is None:
        logger.info("Loading Whisper model...")
        _model = whisper.load_model("base")
    return _model


def transcribe(audio_path: str) -> dict:
    """
    Transcribe audio file using Whisper.
    Returns: {"text": "...", "language": "en" or "hi"}
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        model = _get_model()
        result = model.transcribe(audio_path, task="transcribe")
        text = result.get("text", "").strip()
        detected_lang = result.get("language", "en")

        # Normalize to en/hi
        lang = "hi" if detected_lang in ("hi", "ur") else "en"

        logger.info("Transcribed: '%s' (lang=%s)", text[:80], lang)
        return {"text": text, "language": lang}

    except Exception as e:
        logger.error("Transcription failed: %s", e)
        raise
