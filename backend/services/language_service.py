"""
Language Service — detect language from transcribed text.
Reuses existing heuristic from context_builder, adds "mixed" detection.
"""

import re

HINDI_PATTERNS = [
    r"\b(?:mera|meri|mere|hai|hain|ka|ki|ke|ko|se|ye|wo|kya|kaise|kitna|kitni)\b",
    r"\b(?:chahiye|chahte|chahti|milega|milegi|batao|bataye|bataiye)\b",
    r"\b(?:haan|nahi|nah|ji|aur|lekin|par|toh|bhi)\b",
    r"\b(?:lena|dena|karna|hona|paisa|rupee|rupaye)\b",
    r"\b(?:ghar|makaan|kaam|naukri|tankhah|amdani|namaste|main|aap)\b",
]

ENGLISH_PATTERNS = [
    r"\b(?:the|is|are|was|were|have|has|had|will|would|can|could)\b",
    r"\b(?:what|how|when|where|who|why|which|please|thank|hello|hi)\b",
    r"\b(?:my|your|their|our|this|that|these|those|and|but|or)\b",
]


def detect_language(text: str) -> str:
    """
    Detect language from text.
    Returns: "en", "hi", or "mixed"
    """
    if not text or not text.strip():
        return "en"

    lower = text.lower()
    words = lower.split()
    word_count = max(len(words), 1)

    hindi_score = sum(len(re.findall(p, lower)) for p in HINDI_PATTERNS)
    english_score = sum(len(re.findall(p, lower)) for p in ENGLISH_PATTERNS)

    hindi_ratio = hindi_score / word_count
    english_ratio = english_score / word_count

    if hindi_ratio > 0.3 and english_ratio > 0.2:
        return "mixed"
    if hindi_ratio > 0.3:
        return "hi"
    return "en"
