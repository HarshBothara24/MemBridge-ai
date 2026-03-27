"""
MemBridge AI — Context Builder
Transforms raw structured memory into natural language context for LLM prompts.
NEVER exposes raw database values — always builds human-readable narratives.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from temporal import humanize_timestamp, format_fact_temporal, _format_currency, compute_recency_label

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Language Detection (simple heuristic)
# ──────────────────────────────────────────────
HINDI_INDICATORS = [
    r"\b(?:mera|meri|mere|hai|hain|ka|ki|ke|ko|se|ye|wo|kya|kaise|kitna|kitni)\b",
    r"\b(?:chahiye|chahte|chahti|milega|milegi|batao|bataye|bataiye)\b",
    r"\b(?:haan|nahi|nah|ji|aur|lekin|par|toh|bhi)\b",
    r"\b(?:lena|dena|karna|hona|paisa|rupee|rupaye)\b",
    r"\b(?:ghar|makaan|kaam|naukri|tankhah|amdani)\b",
]


def detect_language(message: str) -> str:
    """
    Detect if the message is primarily Hindi (Romanized) or English.
    Returns 'hi' or 'en'.
    """
    lower = message.lower()
    hindi_score = 0
    for pattern in HINDI_INDICATORS:
        hindi_score += len(re.findall(pattern, lower))

    word_count = len(lower.split())
    if word_count == 0:
        return "en"

    # If more than 30% of signal is Hindi, treat as Hindi
    ratio = hindi_score / max(word_count, 1)
    return "hi" if ratio > 0.3 else "en"


# ──────────────────────────────────────────────
# Context Builder
# ──────────────────────────────────────────────
def build_memory_context(
    facts: List[Dict[str, Any]],
    lang: str = "en",
) -> str:
    """
    Build a natural language context paragraph from structured facts.

    Args:
        facts: List of fact dicts from memory_engine.
        lang: Detected language ('en' or 'hi').

    Returns:
        A natural language paragraph describing what is known about the user.
        NEVER returns raw key=value pairs.
    """
    if not facts:
        if lang == "hi":
            return "Abhi tak koi jaankari nahi hai."
        return "No information available about this customer yet."

    # Rank by importance and limit to 5
    ranked_facts = sorted(facts, key=lambda f: f.get("importance_score", 0.0), reverse=True)[:5]

    sentences = []
    for fact in ranked_facts:
        key = fact.get("key", "")
        value = str(fact.get("value", "")).strip('"')
        timestamp = fact.get("updated_at") or fact.get("created_at")

        sentence = format_fact_temporal(key, value, timestamp, lang)
        sentences.append(sentence)

    # Join into a coherent paragraph
    if lang == "hi":
        connector = ". "
    else:
        connector = ". "

    return connector.join(sentences) + "."


def build_recall_suggestions(
    facts: List[Dict[str, Any]],
    intent: str,
    lang: str = "en",
) -> List[str]:
    """
    Generate memory recall suggestions based on current context.

    Example:
        "You mentioned a co-applicant last Tuesday — include their income?"
    """
    suggestions = []

    fact_keys = {f["key"] for f in facts}

    if lang == "hi":
        return _suggestions_hi(facts, fact_keys, intent)
    return _suggestions_en(facts, fact_keys, intent)


def _suggestions_en(
    facts: List[Dict[str, Any]],
    fact_keys: set,
    intent: str,
) -> List[str]:
    suggestions = []

    # Proactive Suggestion Rule: Co-applicant present
    if "co_applicant" in fact_keys:
        co_fact = next((f for f in facts if f["key"] == "co_applicant"), None)
        if co_fact and str(co_fact.get("value", "")).lower() not in ["no", "none", "false"]:
            suggestions.append("Since you have a co-applicant, you might qualify for improved loan eligibility. Shall we check?")
            
    # Co-applicant exists but no co-applicant income
    if "co_applicant" in fact_keys and "co_applicant_income" not in fact_keys:
        co_fact = next((f for f in facts if f["key"] == "co_applicant"), None)
        if co_fact and str(co_fact.get("value", "")).lower() not in ["no", "none", "false"]:
            time_str = compute_recency_label(co_fact.get("updated_at", ""), "en")
            suggestions.append(
                f"You mentioned a co-applicant {time_str} — would you like to include their income?"
            )

    # Income exists but no employment type
    if "income" in fact_keys and "employment" not in fact_keys:
        suggestions.append("What is your employment type? (Salaried / Self-employed / Business)")

    # Loan type exists but no loan amount
    if "loan_type" in fact_keys and "loan_amount" not in fact_keys:
        loan_fact = next((f for f in facts if f["key"] == "loan_type"), None)
        if loan_fact:
            suggestions.append(
                f"How much {loan_fact['value']} amount are you looking for?"
            )

    # Has income but no credit score (for eligibility check)
    if intent == "loan_eligibility" and "credit_score" not in fact_keys:
        suggestions.append("Sharing your credit score can help assess eligibility more accurately.")

    return suggestions[:3]  # max 3 suggestions


def _suggestions_hi(
    facts: List[Dict[str, Any]],
    fact_keys: set,
    intent: str,
) -> List[str]:
    suggestions = []

    if "co_applicant" in fact_keys and "co_applicant_income" not in fact_keys:
        co_fact = next((f for f in facts if f["key"] == "co_applicant"), None)
        if co_fact:
            time_str = humanize_timestamp(co_fact.get("updated_at", ""), "hi")
            suggestions.append(
                f"Aapne {time_str} co-applicant ke baare mein bataya tha — unki income include karein?"
            )

    if "income" in fact_keys and "employment" not in fact_keys:
        suggestions.append("Aapki employment type kya hai? (Salaried / Self-employed / Business)")

    if "loan_type" in fact_keys and "loan_amount" not in fact_keys:
        loan_fact = next((f for f in facts if f["key"] == "loan_type"), None)
        if loan_fact:
            suggestions.append(f"Aapko kitne ka {loan_fact['value']} chahiye?")

    if intent == "loan_eligibility" and "credit_score" not in fact_keys:
        suggestions.append("Credit score share karne se eligibility better assess ho sakti hai.")

    return suggestions[:3]


# ──────────────────────────────────────────────
# Full Prompt Builder
# ──────────────────────────────────────────────
def build_full_prompt(
    message: str,
    memory_context: str,
    history: List[Dict[str, Any]],
    lang: str = "en",
) -> str:
    """
    Build the complete LLM prompt with memory context, history, and language instruction.
    """
    parts = []

    # System instruction
    if lang == "hi":
        parts.append(
            "IMPORTANT: You MUST respond ONLY in Hindi (Devanagari script or Romanized Hindi). "
            "Do NOT respond in English under any circumstances. "
            "Tum ek helpful banking assistant ho MemBridge AI ke liye. "
            "Hamesha SIRF Hindi mein seedha aur concise jawaab do — English bilkul mat use karo. "
            "Agar loan calculation poochi jaye toh seedha numbers do — EMI, interest rate, total amount. "
            "Ek hi baar jawaab do, repeat mat karo. 3-4 sentences mein khatam karo. "
            "Jab bhi tum memory use karo, user ko lightly batao ki tumne wo yaad kyu rakha hai. "
            "Database ya robot jaisa mat bolo. Baar baar same baat mat dohrao."
        )
    else:
        parts.append(
            "You are a helpful, senior banking assistant for MemBridge AI. "
            "Always respond concisely in 3-5 sentences maximum. Never repeat yourself. "
            "If asked about loans or EMI, present the pre-calculated numbers directly — do not recalculate. "
            "When using facts from memory, briefly explain why you considered them. "
            "Do not hedge or loop — give one clear, direct answer and stop."
        )

    # Memory context
    if memory_context and memory_context.strip():
        if lang == "hi":
            parts.append(f"\nIs customer ke baare mein jo aapko pata hai:\n{memory_context}")
            parts.append("Is jaankari ko naturally conversation mein blend karo. Mechanical lists mat dena.")
        else:
            parts.append(f"\nWhat you securely know about this customer across sessions:\n{memory_context}")
            parts.append("Use this contextual memory naturally. Do not say 'According to my memory', just smoothly incorporate it.")

    # Recent history
    if history:
        lines = []
        for msg in history[-6:]:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {msg['content']}")
        history_text = "\n".join(lines)
        if lang == "hi":
            parts.append(f"\nHaal ki baatcheet:\n{history_text}")
        else:
            parts.append(f"\nRecent conversation:\n{history_text}")

    parts.append(f"\nUser: {message}")
    parts.append("Assistant:")

    return "\n".join(parts)
