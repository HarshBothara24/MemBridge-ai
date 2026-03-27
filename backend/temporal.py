"""
MemBridge AI — Temporal Reasoning
Convert raw timestamps into natural, human-readable relative time strings.
Supports both English and Hindi output.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))

def _now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)

# ──────────────────────────────────────────────
# Day names
# ──────────────────────────────────────────────
DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_NAMES_HI = ["Somvaar", "Mangalvaar", "Budhvaar", "Guruvaar", "Shukravaar", "Shanivaar", "Ravivaar"]

MONTH_NAMES_EN = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def humanize_timestamp(
    timestamp: datetime | str,
    lang: str = "en",
    reference: Optional[datetime] = None,
) -> str:
    """
    Convert a timestamp to a natural language relative time string.

    Args:
        timestamp: The timestamp to convert (datetime or ISO string).
        lang: Language code — 'en' or 'hi'.
        reference: Reference time (defaults to now).

    Returns:
        Human-readable string like "yesterday", "last Tuesday", "2 weeks ago".
    """
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp  # return as-is if unparseable

    now = reference or _now_ist()
    delta = now - timestamp
    days = delta.days
    seconds = delta.total_seconds()

    if lang == "hi":
        return _humanize_hi(timestamp, now, days, seconds)
    return _humanize_en(timestamp, now, days, seconds)


def _humanize_en(ts: datetime, now: datetime, days: int, seconds: float) -> str:
    """English temporal reasoning."""
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = int(seconds // 60)
        return f"{mins} minute{'s' if mins > 1 else ''} ago"
    if days == 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 7:
        day_name = DAY_NAMES_EN[ts.weekday()]
        return f"last {day_name}"
    if days < 14:
        return "last week"
    if days < 30:
        weeks = days // 7
        return f"{weeks} weeks ago"
    if days < 60:
        return "last month"
    if days < 365:
        return f"on {MONTH_NAMES_EN[ts.month]} {ts.day}"
    return f"on {MONTH_NAMES_EN[ts.month]} {ts.day}, {ts.year}"


def _humanize_hi(ts: datetime, now: datetime, days: int, seconds: float) -> str:
    """Hindi temporal reasoning."""
    if seconds < 60:
        return "abhi abhi"
    if seconds < 3600:
        mins = int(seconds // 60)
        return f"{mins} minute pehle"
    if days == 0:
        return "aaj"
    if days == 1:
        return "kal"
    if days == 2:
        return "parso"
    if days < 7:
        day_name = DAY_NAMES_HI[ts.weekday()]
        return f"pichle {day_name}"
    if days < 14:
        return "pichle hafte"
    if days < 30:
        weeks = days // 7
        return f"{weeks} hafte pehle"
    if days < 60:
        return "pichle mahine"
    return f"{ts.day} {MONTH_NAMES_EN[ts.month]} ko"


def format_fact_temporal(
    key: str,
    value: str,
    timestamp: datetime | str,
    lang: str = "en",
) -> str:
    """
    Create a natural language sentence for a fact with temporal context.

    Example (en): "You mentioned an income of ₹40,000 yesterday"
    Example (hi): "Aapne kal ₹40,000 income bataya tha"
    """
    time_str = humanize_timestamp(timestamp, lang)

    if lang == "hi":
        return _format_fact_hi(key, value, time_str)
    return _format_fact_en(key, value, time_str)


def _format_fact_en(key: str, value: str, time_str: str) -> str:
    """Format a single fact in English with temporal context."""
    templates = {
        "income":           f"You mentioned an income of {_format_currency(value)} {time_str}",
        "loan_type":        f"You expressed interest in a {value} {time_str}",
        "co_applicant":     f"You mentioned having a co-applicant {time_str}",
        "co_applicant_income": f"Your co-applicant's income is {_format_currency(value)}, mentioned {time_str}",
        "age":              f"Your age is {value}, shared {time_str}",
        "credit_score":     f"Your credit score is {value}, shared {time_str}",
        "employment":       f"You mentioned being {value} {time_str}",
        "documents":        f"You discussed documents {time_str}",
        "property":         f"You mentioned a property {time_str}",
        "property_location":f"You're looking at property in {value}, mentioned {time_str}",
        "loan_amount":      f"You requested a loan of {_format_currency(value)} {time_str}",
    }
    return templates.get(key, f"You shared {key}: {value} {time_str}")


def _format_fact_hi(key: str, value: str, time_str: str) -> str:
    """Format a single fact in Hindi with temporal context."""
    templates = {
        "income":           f"Aapne {time_str} {_format_currency(value)} income bataya tha",
        "loan_type":        f"Aapne {time_str} {value} mein interest dikhaya tha",
        "co_applicant":     f"Aapne {time_str} co-applicant ke baare mein bataya tha",
        "co_applicant_income": f"Aapke co-applicant ki income {_format_currency(value)} hai, {time_str} bataya tha",
        "age":              f"Aapki umar {value} hai, {time_str} bataya tha",
        "credit_score":     f"Aapka credit score {value} hai, {time_str} bataya tha",
        "employment":       f"Aapne {time_str} bataya tha ki aap {value} hain",
        "documents":        f"Aapne {time_str} documents ke baare mein baat ki thi",
        "loan_amount":      f"Aapne {time_str} {_format_currency(value)} ka loan maanga tha",
    }
    return templates.get(key, f"Aapne {time_str} {key}: {value} bataya tha")


def _format_currency(value: str | int | float) -> str:
    """Format a number as Indian currency (₹X,XX,XXX)."""
    try:
        num = int(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return str(value)

    if num >= 10000000:  # 1 crore+
        cr = num / 10000000
        return f"₹{cr:.1f}Cr" if cr != int(cr) else f"₹{int(cr)}Cr"
    if num >= 100000:  # 1 lakh+
        lakh = num / 100000
        return f"₹{lakh:.1f}L" if lakh != int(lakh) else f"₹{int(lakh)}L"

    # Indian number formatting
    s = str(num)
    if len(s) <= 3:
        return f"₹{s}"
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + "," + result
        s = s[:-2]
    return f"₹{result}"
