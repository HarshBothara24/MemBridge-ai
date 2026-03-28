"""
STT Service — Whisper-based multilingual speech-to-text.
Supports English, Hindi, and Hinglish.
"""

import logging
import whisper
import os
import shutil
import importlib
from subprocess import CalledProcessError, run

logger = logging.getLogger(__name__)

WHISPER_MODEL_NAME = "medium"

_model = None
_ffmpeg_checked = False
_whisper_loader_patched = False

def _get_model():
    global _model
    if _model is None:
        logger.info("Loading Whisper model: %s", WHISPER_MODEL_NAME)
        _model = whisper.load_model(WHISPER_MODEL_NAME)
    return _model


def _ensure_ffmpeg_available() -> str:
    """Resolve and configure an ffmpeg binary for Whisper on Windows/macOS/Linux."""
    global _ffmpeg_checked
    if _ffmpeg_checked:
        return "ok"

    ffmpeg_path = os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg")

    # Optional fallback: packaged ffmpeg binary from imageio-ffmpeg
    if not ffmpeg_path:
        try:
            imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None

    if not ffmpeg_path:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg and add it to PATH, or install imageio-ffmpeg "
            "and set FFMPEG_BINARY if needed."
        )

    _patch_whisper_audio_loader(ffmpeg_path)

    _ffmpeg_checked = True
    logger.info("Using ffmpeg binary: %s", ffmpeg_path)
    return ffmpeg_path


def _patch_whisper_audio_loader(ffmpeg_path: str) -> None:
    """Patch whisper.audio.load_audio to use an explicit ffmpeg binary path."""
    global _whisper_loader_patched
    if _whisper_loader_patched:
        return

    import whisper.audio as whisper_audio

    def _load_audio_with_resolved_ffmpeg(file: str, sr: int = whisper_audio.SAMPLE_RATE):
        cmd = [
            ffmpeg_path,
            "-nostdin",
            "-threads", "0",
            "-i", file,
            "-f", "s16le",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-ar", str(sr),
            "-",
        ]
        try:
            out = run(cmd, capture_output=True, check=True).stdout
        except CalledProcessError as e:
            raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e
        return whisper_audio.np.frombuffer(out, whisper_audio.np.int16).flatten().astype(whisper_audio.np.float32) / 32768.0

    whisper_audio.load_audio = _load_audio_with_resolved_ffmpeg
    _whisper_loader_patched = True


def transcribe(audio_path: str, language_hint: str = None) -> dict:
    """
    Transcribe audio file using Whisper.
    Returns: {"text": "...", "language": "en" or "hi"}
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        _ensure_ffmpeg_available()
        model = _get_model()

        # Single-pass STT for lower latency while preserving language detection.
        transcribe_kwargs = {
            "task": "transcribe",
            "fp16": False,
            "temperature": 0.0,
            "condition_on_previous_text": False,
        }
        if language_hint:
            transcribe_kwargs["language"] = language_hint

        result = model.transcribe(audio_path, **transcribe_kwargs)
        detected_lang = result.get("language", language_hint or "en")

        # Normalize to en/hi
        lang = "hi" if detected_lang in ("hi", "ur") else "en"
        text = result.get("text", "").strip()

        logger.info("Transcribed: '%s' (lang=%s)", text[:80], lang)
        return {"text": text, "language": lang}

    except Exception as e:
        logger.error("Transcription failed: %s", e)
        raise
