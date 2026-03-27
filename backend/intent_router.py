"""
MemBridge AI — Intent Router
Keyword-based intent classification to determine which memory facts to retrieve.
No LLM call needed — fast and deterministic.
"""

import re
from typing import List, Tuple

# ──────────────────────────────────────────────
# Intent → Memory Key Mapping
# ──────────────────────────────────────────────
INTENT_MEMORY_MAP = {
    "loan_eligibility": ["income", "employment", "credit_score", "age", "co_applicant", "loan_type"],
    "document_check":   ["documents", "pan", "aadhaar", "passport", "income_proof"],
    "loan_application": ["income", "loan_type", "co_applicant", "employment", "property", "credit_score", "age"],
    "account_info":     ["income", "age", "employment", "co_applicant"],
    "co_applicant":     ["co_applicant", "co_applicant_income", "co_applicant_name"],
    "property":         ["property", "property_location", "property_value"],
    "repayment":        ["income", "loan_type", "loan_amount", "emi"],
    "general":          [],  # fetch ALL active facts
}

# ──────────────────────────────────────────────
# Intent Detection Patterns
# ──────────────────────────────────────────────
INTENT_PATTERNS = [
    # (intent_name, pattern_list)
    ("loan_eligibility", [
        r"(?:am\s+i|can\s+i|do\s+i)\s+(?:eligible|qualify)",
        r"eligib(?:le|ility)",
        r"loan.*(?:milega|mil\s+sakta|qualify)",
        r"kitna\s+loan",
        r"how\s+much.*loan",
        r"loan\s+amount",
    ]),
    ("document_check", [
        r"document",
        r"paper",
        r"dastawez",
        r"kagaz",
        r"pan\s*card",
        r"aadhaar",
        r"aadhar",
        r"passport",
        r"income\s+proof",
        r"salary\s+slip",
        r"itr",
        r"what.*(?:need|require|submit)",
    ]),
    ("loan_application", [
        r"apply.*loan",
        r"loan.*apply",
        r"loan\s+(?:lena|chahiye|chahte)",
        r"(?:want|need|looking\s+for).*loan",
        r"loan\s+application",
        r"(?:start|begin|initiate).*(?:loan|application)",
    ]),
    ("co_applicant", [
        r"co[\s-]?applicant",
        r"joint\s*applicant",
        r"(?:wife|husband|spouse|brother|sister|parent).*(?:apply|loan|income)",
        r"(?:apply|loan|income).*(?:wife|husband|spouse|brother|sister|parent)",
    ]),
    ("property", [
        r"property",
        r"(?:flat|house|apartment|plot|land)",
        r"(?:ghar|makaan|zameen)",
        r"real\s+estate",
    ]),
    ("repayment", [
        r"emi",
        r"repay",
        r"installment",
        r"monthly\s+pay",
        r"(?:kist|qist)",
        r"tenure",
    ]),
    ("account_info", [
        r"(?:my|mera|meri)\s+(?:account|profile|detail)",
        r"(?:remember|yaad|recall).*(?:me|mujhe|about\s+me)",
        r"what.*(?:know|remember).*(?:about\s+me|mere\s+baare)",
    ]),
]


def classify_intent(message: str) -> Tuple[str, List[str]]:
    """
    Classify the intent of a user message.

    Returns:
        (intent_name, list_of_memory_keys_to_fetch)
    """
    lower = message.lower().strip()

    for intent_name, patterns in INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lower):
                memory_keys = INTENT_MEMORY_MAP.get(intent_name, [])
                return intent_name, memory_keys

    # Default: general intent → fetch all active facts
    return "general", []


def get_memory_keys_for_intent(intent: str) -> List[str]:
    """Get the memory keys associated with an intent."""
    return INTENT_MEMORY_MAP.get(intent, [])
