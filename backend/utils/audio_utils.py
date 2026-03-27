"""
Audio Utils — download audio from a URL to a temp file.
"""

import logging
import uuid
import os
import requests

logger = logging.getLogger(__name__)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "temp")


def download_audio(url: str) -> str:
    """
    Download audio from a URL and save to a temp file.
    Returns the local file path.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(TEMP_DIR, filename)

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(response.content)
        logger.info("Downloaded audio to: %s", filepath)
        return filepath
    except Exception as e:
        logger.error("Failed to download audio from %s: %s", url, e)
        raise
