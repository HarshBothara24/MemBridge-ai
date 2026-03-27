"""
STT Service — Whisper-based multilingual speech-to-text.
Supports English, Hindi, and Hinglish.
"""

import logging
import whisper
import os

logger = logging.getLogger(__name__)

_model = whisper.load_model("small")

def _get_model():
    global _model
    if _model is None:
        logger.info("Loading Whisper model...")
        _model = whisper.load_model("base")
    return _model


def transcribe(audio_path: str, language_hint: str = None) -> dict:
    """
    Transcribe audio file using Whisper.
    Returns: {"text": "...", "language": "en" or "hi"}
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        model = _get_model()

        # First pass: detect language if no hint given
        if not language_hint:
            detect_result = model.transcribe(audio_path, task="transcribe")
            detected_lang = detect_result.get("language", "en")
        else:
            detected_lang = language_hint

        # Normalize to en/hi
        lang = "hi" if detected_lang in ("hi", "ur") else "en"

        # Second pass: transcribe with language forced for better accuracy
        result = model.transcribe(audio_path, task="transcribe", language=lang)
        text = result.get("text", "").strip()

        logger.info("Transcribed: '%s' (lang=%s)", text[:80], lang)
        return {"text": text, "language": lang}

    except Exception as e:
        logger.error("Transcription failed: %s", e)
        raise
