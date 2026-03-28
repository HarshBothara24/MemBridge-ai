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
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3:8b"
VOICE_MODEL_NAME = os.getenv("OLLAMA_VOICE_MODEL", MODEL_NAME)
TIMEOUT_SECONDS = 30  # generous timeout for local models
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "1"))
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", str(max(2, (os.cpu_count() or 4) - 1))))
ENABLE_HINDI_REWRITE_FALLBACK = os.getenv("ENABLE_HINDI_REWRITE_FALLBACK", "false").lower() in ("1", "true", "yes")

HINDI_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
HINDI_ROMAN_HINTS_RE = re.compile(
    r"\b(?:aap|main|mera|meri|mujhe|kripya|kya|kaise|kitna|loan|emi|hai|hain|nahi|ji)\b",
    re.IGNORECASE,
)
ENGLISH_FUNCTION_WORDS_RE = re.compile(
    r"\b(?:the|is|are|was|were|have|has|had|would|should|can|could|please|you|your|this|that|and|or|but)\b",
    re.IGNORECASE,
)


def _base_options() -> Dict[str, Any]:
    return {
        "num_gpu": OLLAMA_NUM_GPU,
        "num_thread": OLLAMA_NUM_THREAD,
    }


def warmup_ollama() -> None:
    """Warm up local Ollama model to reduce first-token latency."""
    payload = {
        "model": VOICE_MODEL_NAME,
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
        requests.post(OLLAMA_URL, json=payload, timeout=8)
        logger.info("Ollama warmup requested for model: %s", VOICE_MODEL_NAME)
    except Exception as e:
        logger.warning("Ollama warmup skipped: %s", e)


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
                "num_predict": 256,  # keep response short
            },
        }
        res = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
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
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            **_base_options(),
            "temperature": 0.5,
            "num_predict": 300,
            "repeat_penalty": 1.3,
            "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
        },
    }

    try:
        res = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        res.raise_for_status()
        response = res.json().get("response", "").strip()

        if not response:
            return "I'm sorry, I couldn't generate a response. Please try again."
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
            "VOICE RESPONSE — CONCISE: Primary language is Hindi, but code-switch to English if needed for clarity.\n"
            "2-3 short sentences max. Be direct, confident, no filler.\n\n"
        ) + prompt
    else:
        prompt = (
            "VOICE RESPONSE — CONCISE: 2-3 short sentences max.\n"
            "Be direct and confident. Skip hedging and verbose explanations.\n\n"
        ) + prompt

    payload = {
        "model": VOICE_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            **_base_options(),
            "temperature": 0.3,
            "num_predict": 140,
            "repeat_penalty": 1.2,
            "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
        },
    }

    try:
        res = requests.post(OLLAMA_URL, json=payload, timeout=20)
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
        res = requests.post(OLLAMA_URL, json=payload, timeout=15)
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
        **_base_options(),
        "temperature": 0.5,
        "num_predict": 300,
        "repeat_penalty": 1.3,
        "stop": ["\nUser:", "\nAssistant:", "User:", "Assistant:"],
    }

    full_response = ""

    try:
        stream_payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": stream_options,
        }
        with requests.post(OLLAMA_URL, json=stream_payload, timeout=120, stream=True) as res:
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
