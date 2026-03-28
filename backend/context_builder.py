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
        if lang in ("hi", "mixed"):
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

    if lang in ("hi", "mixed"):
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
    SYSTEM_PROMPT = """You are a professional Indian banking assistant with deep expertise in:
- Home loans, personal loans, and business loans
- EMI calculation, interest rates, tenure planning
- Eligibility criteria (income, credit score, liabilities)
- Banking documents (PAN, Aadhaar, salary slips, ITR, bank statements)
- Co-applicant rules and joint applications
- Property valuation and loan-to-value ratios
- RBI guidelines and standard banking practices in India

Your responsibilities:
1. ALWAYS use available memory context about the user
2. Provide accurate and practical financial guidance
3. Ask follow-up questions when required information is missing
4. Use simple, clear language (avoid jargon unless necessary)
5. Be confident and professional like a real bank officer
6. NEVER hallucinate unknown financial values or policies

Memory Usage Rules:
- If past data exists, reference it naturally:
  Example: "You mentioned your income is ₹8 lakh..."
- If data is missing, ask clearly:
  Example: "Could you share your credit score?"

Tone:
- Professional but friendly
- Concise and helpful
- Context-aware

Language:
- Match user's language (English / Hindi / mixed)

IMPORTANT:
- Do NOT behave like a generic chatbot
- Do NOT say "based on the provided context"
- Speak like a human banking agent"""

    if lang in ("hi", "mixed"):
        parts.append(
            SYSTEM_PROMPT + "\n\nUser prefers Hindi — respond primarily in Hindi (Devanagari or Roman), but use English when it improves clarity or is user-initiated."
        )
    else:
        parts.append(SYSTEM_PROMPT)

    # Memory context
    if memory_context and memory_context.strip():
        if lang in ("hi", "mixed"):
            parts.append(f"\nCUSTOMER CONTEXT (Use naturally, bilingual):\n{memory_context}\n")
            parts.append("↳ Blend this into your response naturally; avoid mechanical retrieval. Code-switch if needed.")
        else:
            parts.append(f"\nCUSTOMER CONTEXT (Reference only):\n{memory_context}\n")
            parts.append("↳ Weave this naturally into your response; avoid mechanical retrieval.")

    # Recent history
    if history:
        lines = []
        for msg in history[-6:]:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {msg['content']}")
        history_text = "\n".join(lines)
        if lang in ("hi", "mixed"):
            parts.append(f"\nHAAL KI BAATCHEET (tone and continuity):\n{history_text}")
        else:
            parts.append(f"\nCONVERSATION HISTORY (For continuity and tone):\n{history_text}")

    parts.append(f"\nUser: {message}")
    parts.append("Assistant:")

    return "\n".join(parts)
