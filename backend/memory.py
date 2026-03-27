"""
MemBridge AI — Enhanced Fact Extraction (Regex)
Fast, deterministic fact extraction using pattern matching.
Used as first-pass before LLM extraction for speed.
Output format: {key, value, confidence}
"""

import re
from typing import List, Dict, Any


def extract_facts(message: str) -> List[Dict[str, Any]]:
    """
    Extract structured facts from a user message using regex / keyword matching.
    Returns list of {key, value, confidence} dicts.
    """
    facts: List[Dict[str, Any]] = []
    lower = message.lower()

    # ── Income ──────────────────────────────────
    income_patterns = [
        r"(?:income|salary|earn|earning|make|making|amdani|tankhah|kamai)\s*(?:is|of|around|about|approximately|roughly|hai)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"(?:rs\.?|inr|₹)\s*([\d,]+)\s*(?:per\s*(?:month|annum|year|mahina|saal))?",
        r"([\d,]+)\s*(?:per\s*(?:month|annum|year|mahina|saal))",
        r"([\d,]+)\s*(?:rupees?|rupaye?)\s*(?:per\s*(?:month|mahina))?",
    ]
    for pattern in income_patterns:
        match = re.search(pattern, lower)
        if match:
            raw = match.group(1).replace(",", "")
            if raw.isdigit() and int(raw) >= 1000:
                facts.append({"type": "financial", "key": "income", "value": raw, "confidence": 0.9})
            break

    # ── Loan type ───────────────────────────────
    loan_types = {
        "home loan": "home loan", "housing loan": "home loan", "mortgage loan": "home loan",
        "ghar ka loan": "home loan",
        "personal loan": "personal loan",
        "car loan": "car loan", "auto loan": "car loan", "vehicle loan": "car loan",
        "gaadi ka loan": "car loan",
        "education loan": "education loan", "student loan": "education loan",
        "padhai ka loan": "education loan",
        "business loan": "business loan", "msme loan": "business loan",
        "vyapar loan": "business loan",
        "gold loan": "gold loan", "sone ka loan": "gold loan",
        "loan against property": "loan against property", "lap": "loan against property",
    }
    for keyword, canonical in loan_types.items():
        if keyword in lower:
            facts.append({"type": "financial", "key": "loan_type", "value": canonical, "confidence": 0.9})
            break

    # ── Co-applicant ────────────────────────────
    co_patterns = [
        r"co[\s-]?applicant",
        r"joint\s*applicant",
        r"joint\s*account",
        r"(?:wife|husband|spouse|brother|sister|parent|bhai|behen|pati|patni).*(?:apply|loan|saath|together)",
        r"(?:apply|loan|saath|together).*(?:wife|husband|spouse|brother|sister|parent|bhai|behen)",
    ]
    for cp in co_patterns:
        if re.search(cp, lower):
            facts.append({"type": "profile", "key": "co_applicant", "value": "yes", "confidence": 0.85})
            break

    # ── Age ─────────────────────────────────────
    age_match = re.search(
        r"(?:i am|i'm|age\s*(?:is)?|meri\s*(?:umar|age))\s*(\d{2})\s*(?:years?\s*old|saal)?", lower
    )
    if age_match:
        facts.append({"type": "profile", "key": "age", "value": age_match.group(1), "confidence": 0.9})

    # ── Credit score ────────────────────────────
    score_match = re.search(
        r"(?:credit\s*score|cibil)\s*(?:is|of|around|about|hai)?\s*(\d{3})", lower
    )
    if score_match:
        facts.append({"type": "financial", "key": "credit_score", "value": score_match.group(1), "confidence": 0.9})

    # ── Employment type ─────────────────────────
    emp_keywords = {
        "salaried": "salaried",
        "self-employed": "self-employed",
        "self employed": "self-employed",
        "business owner": "business owner",
        "freelancer": "freelancer",
        "freelance": "freelancer",
        "naukri": "salaried",
        "job": "salaried",
        "apna kaam": "self-employed",
        "vyapar": "business owner",
    }
    for keyword, canonical in emp_keywords.items():
        if keyword in lower:
            facts.append({"type": "profile", "key": "employment", "value": canonical, "confidence": 0.85})
            break

    # ── Loan amount ─────────────────────────────
    amount_patterns = [
        r"(?:loan|amount|chahiye|need|want)\s*(?:of|ka|ki)?\s*(?:rs\.?|inr|₹)?\s*([\d,]+)",
        r"(?:rs\.?|inr|₹)\s*([\d,]+)\s*(?:ka\s*)?(?:loan|amount)",
        r"([\d,]+)\s*(?:ka\s*)?(?:loan)\b",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, lower)
        if match:
            raw = match.group(1).replace(",", "")
            if raw.isdigit() and int(raw) >= 10000:
                # Don't add if same as income
                if not any(f["key"] == "income" and f["value"] == raw for f in facts):
                    facts.append({"type": "financial", "key": "loan_amount", "value": raw, "confidence": 0.85})
            break

    # ── Documents ───────────────────────────────
    doc_keywords = [
        r"\bpan\s*(?:card)?\b",
        r"\baadhaa?r\b",
        r"\bpassport\b",
        r"\bitr\b",
        r"\bsalary\s*slip\b",
        r"\bbank\s*statement\b",
        r"\bincome\s*proof\b",
        r"\b(?:document|dastawez|kagaz)\b",
    ]
    for dk in doc_keywords:
        if re.search(dk, lower):
            facts.append({"type": "event", "key": "documents", "value": "mentioned", "confidence": 0.7})
            break

    # ── Property ────────────────────────────────
    property_patterns = [
        r"(?:flat|house|apartment|plot|land|villa|ghar|makaan|zameen)\s+(?:in|at|near)\s+(\w+(?:\s+\w+)?)",
    ]
    for pp in property_patterns:
        match = re.search(pp, lower)
        if match:
            facts.append({"type": "financial", "key": "property_location", "value": match.group(1).title(), "confidence": 0.75})
            break

    return facts
