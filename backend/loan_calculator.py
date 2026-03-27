"""
Loan Calculator — deterministic math, no LLM involved.
Intercepts loan/interest queries and returns pre-computed results
to inject into the LLM prompt as ground truth.
"""

import re
from typing import Optional, Dict, Any

# Standard bank interest rates by loan type (annual %)
DEFAULT_RATES = {
    "home":     8.5,
    "personal": 12.0,
    "car":      9.0,
    "business": 13.5,
    "education": 9.5,
    "default":  11.0,
}

AMOUNT_PATTERNS = [
    (r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", lambda m: float(m.group(1)) * 100_000),
    (r"(\d+(?:\.\d+)?)\s*(?:crore|cr)", lambda m: float(m.group(1)) * 10_000_000),
    (r"₹\s*(\d[\d,]*)", lambda m: float(m.group(1).replace(",", ""))),
    (r"rs\.?\s*(\d[\d,]*)", lambda m: float(m.group(1).replace(",", ""))),
    (r"\b(\d{4,})\b", lambda m: float(m.group(1))),
]

TENURE_PATTERNS = [
    (r"(\d+)\s*(?:year|yr|saal)", lambda m: int(m.group(1))),
    (r"(\d+)\s*(?:month|mahine|mahina)", lambda m: int(m.group(1)) // 12 or 1),
]

LOAN_TYPE_KEYWORDS = {
    "home": ["home", "house", "ghar", "makaan", "property", "flat"],
    "personal": ["personal", "vyaktigat"],
    "car": ["car", "vehicle", "gaadi"],
    "business": ["business", "vyapar"],
    "education": ["education", "study", "padhai"],
}


def _extract_amount(text: str) -> Optional[float]:
    lower = text.lower()
    for pattern, converter in AMOUNT_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            return converter(m)
    return None


def _extract_tenure(text: str) -> int:
    lower = text.lower()
    for pattern, converter in TENURE_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            return converter(m)
    return 5  # default 5 years


def _detect_loan_type(text: str) -> str:
    lower = text.lower()
    for loan_type, keywords in LOAN_TYPE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return loan_type
    return "default"


def calculate_emi(principal: float, annual_rate: float, tenure_years: int) -> Dict[str, Any]:
    """Standard EMI formula: P * r * (1+r)^n / ((1+r)^n - 1)"""
    r = annual_rate / 12 / 100
    n = tenure_years * 12
    if r == 0:
        emi = principal / n
    else:
        emi = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    total_payment = emi * n
    total_interest = total_payment - principal
    return {
        "principal": principal,
        "annual_rate": annual_rate,
        "tenure_years": tenure_years,
        "emi": round(emi, 2),
        "total_payment": round(total_payment, 2),
        "total_interest": round(total_interest, 2),
    }


def _fmt(amount: float) -> str:
    """Format number as Indian currency string."""
    if amount >= 100_000:
        return f"₹{amount/100_000:.2f} lakh"
    return f"₹{amount:,.0f}"


INTEREST_KEYWORDS = [
    r"interest", r"byaj", r"rate", r"emi", r"installment", r"kist",
    r"repay", r"monthly.*pay", r"loan.*detail", r"loan.*calculat",
]

LOAN_QUERY_KEYWORDS = [
    r"loan", r"borrow", r"lena\s+hai", r"chahiye",
]


def is_loan_calculation_query(message: str) -> bool:
    lower = message.lower()
    has_interest = any(re.search(p, lower) for p in INTEREST_KEYWORDS)
    has_loan = any(re.search(p, lower) for p in LOAN_QUERY_KEYWORDS)
    has_amount = _extract_amount(lower) is not None
    return (has_interest or has_amount) and has_loan


def get_calculation_context(message: str, memory_facts: list, lang: str = "en") -> Optional[str]:
    """
    If the message is a loan calculation query, compute the answer and return
    a context string to inject into the LLM prompt as ground truth.
    Returns None if not a calculation query.
    """
    if not is_loan_calculation_query(message):
        return None

    # Try to get amount from message first, then memory
    amount = _extract_amount(message)
    if amount is None:
        for f in memory_facts:
            if f.get("key") == "loan_amount":
                amount = _extract_amount(str(f["value"]))
                if amount:
                    break

    if amount is None:
        return None

    tenure = _extract_tenure(message)
    loan_type = _detect_loan_type(message)

    # Check memory for loan type
    for f in memory_facts:
        if f.get("key") == "loan_type":
            detected = _detect_loan_type(str(f["value"]))
            if detected != "default":
                loan_type = detected
                break

    rate = DEFAULT_RATES[loan_type]
    result = calculate_emi(amount, rate, tenure)

    if lang == "hi":
        return (
            f"[CALCULATED LOAN DETAILS — USE THESE EXACT NUMBERS]\n"
            f"Loan Amount: {_fmt(result['principal'])}\n"
            f"Loan Type: {loan_type.title()}\n"
            f"Interest Rate: {result['annual_rate']}% per annum\n"
            f"Tenure: {result['tenure_years']} years\n"
            f"Monthly EMI: {_fmt(result['emi'])}\n"
            f"Total Interest: {_fmt(result['total_interest'])}\n"
            f"Total Repayment: {_fmt(result['total_payment'])}\n"
            f"In-hee numbers ko use karo. Koi aur calculation mat karo."
        )
    else:
        return (
            f"[CALCULATED LOAN DETAILS — USE THESE EXACT NUMBERS]\n"
            f"Loan Amount: {_fmt(result['principal'])}\n"
            f"Loan Type: {loan_type.title()}\n"
            f"Interest Rate: {result['annual_rate']}% per annum\n"
            f"Tenure: {result['tenure_years']} years\n"
            f"Monthly EMI: {_fmt(result['emi'])}\n"
            f"Total Interest: {_fmt(result['total_interest'])}\n"
            f"Total Repayment: {_fmt(result['total_payment'])}\n"
            f"Use ONLY these numbers. Do not recalculate."
        )
