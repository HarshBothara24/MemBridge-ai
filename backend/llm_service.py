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
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:3b"
TIMEOUT_SECONDS = 30  # generous timeout for local models


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
    prompt = f"""Extract structured financial facts from the following user message.
Return ONLY a valid JSON array. Each item must have "key", "value", and "confidence" (0.0-1.0).

Valid keys: income, loan_type, co_applicant, co_applicant_income, co_applicant_name, age, credit_score, employment, documents, property, property_location, property_value, loan_amount, emi, tenure

If no facts found, return: []

Message: "{message}"

JSON:"""

    try:
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
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
        "options": {
            "temperature": 0.7,
            "num_predict": 512,
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
