"""
MemBridge AI — LLM Service
Structured LLM integration with exactly 2 calls:
  1. Fact extraction (from complex messages where regex fails)
  2. Response generation (with full memory context)

Uses local Llama 3.2 via Ollama. NO external APIs.
"""

import json
import re
import logging
import os
import requests
import time
from typing import List, Dict, Any, Optional
from collections import OrderedDict
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3:8b"
VOICE_MODEL_NAME = os.getenv("OLLAMA_VOICE_MODEL", MODEL_NAME)
TIMEOUT_SECONDS = 30  # generous timeout for local models
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "1"))
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", str(max(2, (os.cpu_count() or 4) - 1))))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "3072"))
ENABLE_HINDI_REWRITE_FALLBACK = os.getenv("ENABLE_HINDI_REWRITE_FALLBACK", "false").lower() in ("1", "true", "yes")
ENABLE_RESPONSE_CACHE = os.getenv("ENABLE_RESPONSE_CACHE", "true").lower() in ("1", "true", "yes")
RESPONSE_CACHE_TTL_SECONDS = int(os.getenv("RESPONSE_CACHE_TTL_SECONDS", "45"))
RESPONSE_CACHE_MAX_ITEMS = int(os.getenv("RESPONSE_CACHE_MAX_ITEMS", "128"))

HINDI_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
HINDI_ROMAN_HINTS_RE = re.compile(
    r"\b(?:aap|main|mera|meri|mujhe|kripya|kya|kaise|kitna|loan|emi|hai|hain|nahi|ji)\b",
    re.IGNORECASE,
)
ENGLISH_FUNCTION_WORDS_RE = re.compile(
    r"\b(?:the|is|are|was|were|have|has|had|would|should|can|could|please|you|your|this|that|and|or|but)\b",
    re.IGNORECASE,
)

_http = requests.Session()
_http.mount("http://", HTTPAdapter(pool_connections=16, pool_maxsize=32, max_retries=0))
_response_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()

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


def _base_options() -> Dict[str, Any]:
    return {
        "num_gpu": OLLAMA_NUM_GPU,
        "num_thread": OLLAMA_NUM_THREAD,
        "num_ctx": OLLAMA_NUM_CTX,
    }


def _cached_get(key: str) -> Optional[str]:
    if not ENABLE_RESPONSE_CACHE:
        return None
    now = time.time()
    value = _response_cache.get(key)
    if not value:
        return None
    ts, text = value
    if now - ts > RESPONSE_CACHE_TTL_SECONDS:
        _response_cache.pop(key, None)
        return None
    _response_cache.move_to_end(key)
    return text


def _cached_set(key: str, value: str) -> None:
    if not ENABLE_RESPONSE_CACHE or not value:
        return
    _response_cache[key] = (time.time(), value)
    _response_cache.move_to_end(key)
    while len(_response_cache) > RESPONSE_CACHE_MAX_ITEMS:
        _response_cache.popitem(last=False)


def _is_complex_prompt(prompt: str) -> bool:
    return len(prompt) > 2400 or prompt.count("\n") > 55


def _chat_options(prompt: str) -> Dict[str, Any]:
    complex_prompt = _is_complex_prompt(prompt)
    return {
        **_base_options(),
        "temperature": 0.45,
        "num_predict": 320 if complex_prompt else 180,
        "repeat_penalty": 1.2,
        "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
    }


def _voice_options() -> Dict[str, Any]:
    return {
        **_base_options(),
        "temperature": 0.25,
        "num_predict": 110,
        "repeat_penalty": 1.12,
        "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
    }


def warmup_ollama() -> None:
    """Warm up local Ollama model to reduce first-token latency."""
    for model in {MODEL_NAME, VOICE_MODEL_NAME}:
        payload = {
            "model": model,
            "prompt": "ping",
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                **_base_options(),
                "temperature": 0.0,
                "num_predict": 1,
            },
        }
        try:
            _http.post(OLLAMA_URL, json=payload, timeout=8)
            logger.info("Ollama warmup requested for model: %s", model)
        except Exception as e:
            logger.warning("Ollama warmup skipped for %s: %s", model, e)


# ──────────────────────────────────────────────
# Call 1: Fact Extraction
# ──────────────────────────────────────────────
def extract_facts_llm(message: str) -> List[Dict[str, str]]:
    """
    Use LLM to extract structured facts from a user message.
    This is Call #1 — used for complex messages where regex fails.

    Returns a list of {key, value, confidence} dicts.
    Falls back to empty list on any error.
    """
    prompt = f"""Extract key financial facts from the user message below.
Output ONLY a valid JSON array. Each item must include: type, key, value, confidence (0.0-1.0).

Allowed types: financial, profile, preference, event
Allowed keys: income, loan_type, co_applicant, co_applicant_income, co_applicant_name, age, credit_score, employment, documents, property, property_location, property_value, loan_amount, emi, tenure

If no facts are present, return: []
Be strict: only extract explicitly stated information.

Message: "{message}"

JSON Array:"""

    try:
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                **_base_options(),
                "temperature": 0.1,  # low temp for deterministic extraction
                "num_predict": 180,  # keep extraction short and fast
            },
        }
        res = _http.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        res.raise_for_status()
        raw = res.json().get("response", "").strip()

        # Try to parse JSON from the response
        facts = _parse_json_from_response(raw)
        if facts:
            logger.info("LLM extracted %d facts from message.", len(facts))
        return facts

    except requests.exceptions.Timeout:
        logger.warning("LLM fact extraction timed out — falling back to regex.")
        return []
    except Exception as e:
        logger.warning("LLM fact extraction failed: %s", e)
        return []


def _parse_json_from_response(raw: str) -> List[Dict[str, str]]:
    """Try to extract a JSON array from LLM response text."""
    # Try direct parse
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return _validate_facts(parsed)
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in the response
    match = re.search(r'\[[\s\S]*?\]', raw)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return _validate_facts(parsed)
        except json.JSONDecodeError:
            pass
        

    return []


def _validate_facts(facts: list) -> List[Dict[str, str]]:
    """Validate and clean extracted facts."""
    valid = []
    for f in facts:
        if isinstance(f, dict) and "key" in f and "value" in f:
            valid.append({
                "type": str(f.get("type", "profile")).strip().lower(),
                "key": str(f["key"]).strip().lower().replace(" ", "_"),
                "value": str(f["value"]).strip(),
                "confidence": float(f.get("confidence", 0.7)),
            })
    return valid


# ──────────────────────────────────────────────
# Call 2: Response Generation
# ──────────────────────────────────────────────
def generate_response(prompt: str) -> str:
    """
    Generate an LLM response using the full contextual prompt.
    This is Call #2 — uses memory context + history.
    """
    cache_key = f"chat::{MODEL_NAME}::{hash(prompt)}"
    cached = _cached_get(cache_key)
    if cached:
        return cached

    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _chat_options(prompt),
    }

    try:
        res = _http.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        res.raise_for_status()
        response = res.json().get("response", "").strip()

        if not response:
            return "I'm sorry, I couldn't generate a response. Please try again."
        _cached_set(cache_key, response)
        return response

    except requests.exceptions.Timeout:
        return "I'm taking longer than expected. Please try again in a moment."
    except Exception as e:
        logger.error("LLM response generation failed: %s", e)
        return "Something went wrong. Please try again."


def generate_response_voice(prompt: str, lang: str = "en") -> str:
    """
    Generate a faster voice-first response with lower token budget.
    Supports multilingual: default English, adapt to user's language preference.
    """
    if lang in ("hi", "mixed"):
        prompt = (
            "VOICE RESPONSE — SPOKEN LANGUAGE FOR HEARING:\n\n"
            "You are a friendly banking assistant. Generate responses optimized for speech, not reading.\n\n"
            "KEY RULES:\n"
            "1. Use SIMPLE language — short sentences, natural phrasing.\n"
            "2. Structure for LISTENING — 2–3 sentences max, one idea per sentence.\n"
            "3. ROUND numbers — say 'around 20,000' not '21,347.50'.\n"
            "4. Reference memory NATURALLY — 'Based on your income...' not robotic.\n"
            "5. NO calculator tone — sound like a real agent on a call.\n"
            "6. ONE question to continue — ask one short follow-up only if needed.\n"
            "7. Primary language is Hindi, code-switch to English for clarity only.\n\n"
            "TONE: Friendly, calm, confident, slightly advisory.\n\n"
        ) + prompt
    else:
        prompt = (
            "VOICE RESPONSE — SPOKEN LANGUAGE FOR HEARING:\n\n"
            "You are a friendly banking assistant. Generate responses optimized for speech, not reading.\n\n"
            "KEY RULES:\n"
            "1. Use SIMPLE language — short sentences, natural phrasing.\n"
            "2. Structure for LISTENING — 2–3 sentences max, one idea per sentence.\n"
            "3. ROUND numbers — say 'around 20,000' not '21,347.50'.\n"
            "4. Reference memory NATURALLY — 'As you mentioned...' or 'Based on your profile...'\n"
            "5. NO calculator tone — sound like a real agent on a call.\n"
            "6. ONE question to continue — ask one short follow-up only if needed.\n"
            "7. Default to English; code-switch to Hindi if user prefers.\n\n"
            "TONE: Friendly, calm, confident, slightly advisory.\n\n"
            "DO NOT: Use complex jargon, overload with numbers, sound robotic, write paragraphs.\n\n"
        ) + prompt

    cache_key = f"voice::{VOICE_MODEL_NAME}::{lang}::{hash(prompt)}"
    cached = _cached_get(cache_key)
    if cached:
        return cached

    payload = {
        "model": VOICE_MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _voice_options(),
    }

    try:
        res = _http.post(OLLAMA_URL, json=payload, timeout=20)
        res.raise_for_status()
        response = res.json().get("response", "").strip()

        if (
            ENABLE_HINDI_REWRITE_FALLBACK
            and response
            and lang in ("hi", "mixed")
            and not _is_hindi_quality_response(response)
        ):
            response = _rewrite_to_hindi(response)

        if not response:
            return "Maaf kijiye, main is baar jawab generate nahi kar paaya."
        _cached_set(cache_key, response)
        return response

    except requests.exceptions.Timeout:
        return "Main thoda slow ho raha hoon. Kripya dobara try kijiye."
    except Exception as e:
        logger.error("Voice LLM response generation failed: %s", e)
        return "Kuch technical issue aa gaya. Kripya dobara try kijiye."


def _is_hindi_quality_response(text: str) -> bool:
    """Heuristic check: accept Devanagari or strong Hindi-romanized signal."""
    if not text:
        return False

    if HINDI_DEVANAGARI_RE.search(text):
        return True

    hindi_hits = len(HINDI_ROMAN_HINTS_RE.findall(text))
    english_hits = len(ENGLISH_FUNCTION_WORDS_RE.findall(text))
    return hindi_hits >= max(2, english_hits)


def _rewrite_to_hindi(text: str) -> str:
    """Fallback rewrite to Hindi when first pass is English-heavy."""
    rewrite_prompt = (
        "Rewrite the following assistant response into natural Hindi for an Indian banking customer. "
        "Keep all numbers and financial facts exactly same. Keep it concise (2-3 short sentences). "
        "Do not add new details. Output only Hindi (Devanagari or Roman Hindi).\n\n"
        f"Text: {text}\n\nHindi:"
    )

    payload = {
        "model": VOICE_MODEL_NAME,
        "prompt": rewrite_prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            **_base_options(),
            "temperature": 0.2,
            "num_predict": 120,
            "repeat_penalty": 1.1,
        },
    }

    try:
        res = _http.post(OLLAMA_URL, json=payload, timeout=15)
        res.raise_for_status()
        rewritten = res.json().get("response", "").strip()
        return rewritten or text
    except Exception as e:
        logger.warning("Hindi rewrite fallback failed: %s", e)
        return text


def generate_response_stream(prompt: str):
    """
    Stream LLM response token-by-token using Ollama's streaming API.
    Yields JSON lines: {"token": "...", "done": false} for each chunk,
    and {"token": "", "done": true, "full_response": "..."} at the end.
    """
    stream_options = {
        **_chat_options(prompt),
    }

    full_response = ""

    try:
        stream_payload = {
            "model": MODEL_NAME,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": stream_options,
        }
        with _http.post(OLLAMA_URL, json=stream_payload, timeout=120, stream=True) as res:
            res.raise_for_status()
            for line in res.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    done = chunk.get("done", False)
                    full_response += token

                    if done:
                        yield json.dumps({"token": "", "done": True, "full_response": full_response.strip()}) + "\n"
                    else:
                        yield json.dumps({"token": token, "done": False}) + "\n"
                except json.JSONDecodeError:
                    continue

    except requests.exceptions.Timeout:
        yield json.dumps({"token": "", "done": True, "full_response": "I'm taking longer than expected. Please try again."}) + "\n"
    except Exception as e:
        logger.error("LLM streaming failed: %s", e)
        yield json.dumps({"token": "", "done": True, "full_response": "Something went wrong. Please try again."}) + "\n"
