"""
MemBridge AI — Lightweight Memory System
Handles fact extraction, memory storage/retrieval using a simple JSON file.
"""

import json
import re
import os
from typing import List, Dict, Any
from datetime import datetime

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")

# Max messages to keep in history per customer
MAX_HISTORY = 20


# ──────────────────────────────────────────────
# JSON helpers
# ──────────────────────────────────────────────
def _load_memory_store() -> dict:
    """Load the full memory store from disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_memory_store(store: dict) -> None:
    """Persist the full memory store to disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def _ensure_customer(store: dict, customer_id: str) -> dict:
    """Make sure a customer entry exists with the right shape."""
    if customer_id not in store:
        store[customer_id] = {"facts": [], "history": []}
    return store


# ──────────────────────────────────────────────
# Fact Extraction
# ──────────────────────────────────────────────
def extract_facts(message: str) -> List[Dict[str, str]]:
    """
    Extract structured facts from a user message using
    simple regex / keyword matching.

    Detects:
      • income amounts  (e.g. "my income is 50000", "I earn 85,000")
      • loan types      (home loan, personal loan, car loan, education loan, etc.)
      • co-applicant    (mentions of co-applicant, co applicant, joint applicant)
      • age             (e.g. "I am 30 years old")
      • credit score    (e.g. "credit score is 750")
      • employment type (salaried, self-employed, business owner)
    """
    facts: List[Dict[str, str]] = []
    lower = message.lower()

    # ── Income ──────────────────────────────────
    income_patterns = [
        r"(?:income|salary|earn|earning|make|making)\s*(?:is|of|around|about|approximately|roughly)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"(?:rs\.?|inr|₹)\s*([\d,]+)\s*(?:per\s*(?:month|annum|year))?",
        r"([\d,]+)\s*(?:per\s*(?:month|annum|year))",
    ]
    for pattern in income_patterns:
        match = re.search(pattern, lower)
        if match:
            raw = match.group(1).replace(",", "")
            if raw.isdigit() and int(raw) >= 1000:  # avoid tiny numbers
                facts.append({"type": "income", "value": raw})
            break  # one income per message is enough

    # ── Loan type ───────────────────────────────
    loan_types = [
        "home loan", "housing loan", "mortgage loan",
        "personal loan",
        "car loan", "auto loan", "vehicle loan",
        "education loan", "student loan",
        "business loan", "msme loan",
        "gold loan",
        "loan against property", "lap",
    ]
    for lt in loan_types:
        if lt in lower:
            # normalise similar names
            canonical = lt
            if lt in ("housing loan", "mortgage loan"):
                canonical = "home loan"
            elif lt in ("auto loan", "vehicle loan"):
                canonical = "car loan"
            elif lt == "student loan":
                canonical = "education loan"
            elif lt == "msme loan":
                canonical = "business loan"
            facts.append({"type": "loan_type", "value": canonical})
            break

    # ── Co-applicant ────────────────────────────
    co_patterns = [
        r"co[\s-]?applicant",
        r"joint\s*applicant",
        r"joint\s*account",
        r"spouse.*apply",
        r"apply.*spouse",
    ]
    for cp in co_patterns:
        if re.search(cp, lower):
            facts.append({"type": "co_applicant", "value": "yes"})
            break

    # ── Age ─────────────────────────────────────
    age_match = re.search(
        r"(?:i am|i'm|age\s*(?:is)?)\s*(\d{2})\s*(?:years?\s*old)?", lower
    )
    if age_match:
        facts.append({"type": "age", "value": age_match.group(1)})

    # ── Credit score ────────────────────────────
    score_match = re.search(
        r"(?:credit\s*score|cibil)\s*(?:is|of|around|about)?\s*(\d{3})", lower
    )
    if score_match:
        facts.append({"type": "credit_score", "value": score_match.group(1)})

    # ── Employment type ─────────────────────────
    emp_keywords = {
        "salaried": "salaried",
        "self-employed": "self-employed",
        "self employed": "self-employed",
        "business owner": "business owner",
        "freelancer": "freelancer",
        "freelance": "freelancer",
    }
    for keyword, canonical in emp_keywords.items():
        if keyword in lower:
            facts.append({"type": "employment", "value": canonical})
            break

    return facts


# ──────────────────────────────────────────────
# Memory Save
# ──────────────────────────────────────────────
def save_memory(customer_id: str, message: str, role: str = "user", facts: List[Dict[str, str]] | None = None) -> None:
    """
    Save a message and any extracted facts to the memory store.

    Args:
        customer_id: Unique identifier for the customer.
        message: The message text.
        role: 'user' or 'assistant'.
        facts: Pre-extracted facts (if None, will be extracted from message when role='user').
    """
    store = _load_memory_store()
    store = _ensure_customer(store, customer_id)

    entry = store[customer_id]

    # ── Save facts (deduplicated) ───────────────
    if role == "user":
        new_facts = facts if facts is not None else extract_facts(message)
        existing_types_values = {(f["type"], f["value"]) for f in entry["facts"]}
        for fact in new_facts:
            if (fact["type"], fact["value"]) not in existing_types_values:
                fact["timestamp"] = datetime.now().isoformat()
                entry["facts"].append(fact)
                existing_types_values.add((fact["type"], fact["value"]))

    # ── Save to history ─────────────────────────
    entry["history"].append({
        "role": role,
        "content": message,
        "timestamp": datetime.now().isoformat(),
    })

    # Trim history to keep it lightweight
    if len(entry["history"]) > MAX_HISTORY:
        entry["history"] = entry["history"][-MAX_HISTORY:]

    _save_memory_store(store)


# ──────────────────────────────────────────────
# Memory Retrieval
# ──────────────────────────────────────────────
def get_memory(customer_id: str) -> Dict[str, Any]:
    """
    Retrieve stored memory for a customer.

    Returns:
        {
            "facts": [...],
            "history": [last N messages]
        }
    """
    store = _load_memory_store()
    if customer_id not in store:
        return {"facts": [], "history": []}

    entry = store[customer_id]
    return {
        "facts": entry.get("facts", []),
        "history": entry.get("history", [])[-10:],  # return last 10 messages
    }


# ──────────────────────────────────────────────
# Prompt Builder
# ──────────────────────────────────────────────
def build_prompt(
    message: str,
    customer_id: str,
    semantic_results: List[Dict[str, Any]] | None = None,
) -> str:
    """
    Build an enhanced prompt that injects:
      • structured memory  (facts from JSON)
      • semantic memory    (similar past conversations from FAISS)
      • recent history     (last few messages)

    so the LLM can give contextual, personalised responses.
    """
    memory = get_memory(customer_id)

    # ── Format facts ────────────────────────────
    facts_text = ""
    if memory["facts"]:
        lines = []
        for f in memory["facts"]:
            lines.append(f"- {f['type']}: {f['value']}")
        facts_text = "\n".join(lines)

    # ── Format recent conversation ──────────────
    history_text = ""
    recent_contents: set = set()
    if memory["history"]:
        lines = []
        for msg in memory["history"][-6:]:  # last 6 messages for context
            role_label = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {msg['content']}")
            recent_contents.add(msg["content"].strip())
        history_text = "\n".join(lines)

    # ── Format semantic memory ──────────────────
    semantic_text = ""
    if semantic_results:
        # Deduplicate against recent history so we don't repeat
        unique = [
            r for r in semantic_results
            if r["text"].strip() not in recent_contents
        ]
        if unique:
            lines = []
            for r in unique:
                role_label = "User" if r["role"] == "user" else "Assistant"
                lines.append(f"- {role_label}: {r['text']}")
            semantic_text = "\n".join(lines)

    # ── Assemble prompt ─────────────────────────
    prompt_parts = [
        "You are a helpful, friendly banking assistant for MemBridge AI.",
        "You provide accurate information about loans, banking products, and financial advice.",
        "Respond naturally and conversationally. Do not sound like a database or a robot.",
    ]

    if facts_text:
        prompt_parts.append(
            f"\nUser's known facts:\n{facts_text}"
        )
        prompt_parts.append(
            "Use this information naturally in your responses when relevant. "
            "Do not list out the facts mechanically."
        )

    if semantic_text:
        prompt_parts.append(
            f"\nRelevant past conversations:\n{semantic_text}"
        )
        prompt_parts.append(
            "Use this context to give more informed, personalised answers."
        )

    if history_text:
        prompt_parts.append(
            f"\nRecent conversation history:\n{history_text}"
        )

    prompt_parts.append(f"\nUser: {message}")
    prompt_parts.append("Assistant:")

    return "\n".join(prompt_parts)
