"""
MemBridge AI — FastAPI Backend
Cognitive Memory Layer with structured memory, intent-based retrieval,
temporal reasoning, and bilingual (EN/HI) support.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import logging

from db import init_db
from memory import extract_facts
from memory_engine import (
    upsert_facts, get_active_facts, get_facts_by_keys,
    get_timeline, get_profile, save_chat_message, get_recent_history,
)
from intent_router import classify_intent
from context_builder import detect_language, build_memory_context, build_recall_suggestions, build_full_prompt
from llm_service import extract_facts_llm, generate_response, generate_response_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────
app = FastAPI(title="MemBridge AI", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Initialize database on startup."""
    init_db()
    logger.info("MemBridge AI v2.0 — Cognitive Memory Layer ready.")


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    customer_id: str


class ChatResponse(BaseModel):
    response: str
    extracted_facts: list
    intent: str
    suggestions: list
    language: str


# ──────────────────────────────────────────────
# Main Chat Endpoint
# ──────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Enhanced chat flow:
    1. Detect language
    2. Regex fact extraction (fast)
    3. LLM fact extraction (richer, for complex messages)
    4. Merge & upsert facts into PostgreSQL
    5. Classify intent → fetch relevant memory
    6. Build natural language context
    7. LLM response generation
    8. Save chat history
    9. Return response + metadata
    """
    # 1. Detect language
    lang = detect_language(req.message)
    logger.info("Language detected: %s", lang)

    # 2. Fast regex fact extraction
    regex_facts = extract_facts(req.message)
    logger.info("Regex extracted %d facts", len(regex_facts))

    # 3. LLM fact extraction (richer, handles complex sentences)
    llm_facts = extract_facts_llm(req.message)
    logger.info("LLM extracted %d facts", len(llm_facts))

    # 4. Merge facts (regex takes priority for same keys due to higher confidence)
    merged_facts = _merge_facts(regex_facts, llm_facts)
    logger.info("Merged into %d unique facts", len(merged_facts))

    # 5. Upsert facts into PostgreSQL
    if merged_facts:
        upsert_facts(req.customer_id, merged_facts)

    # Save user message to chat history
    save_chat_message(req.customer_id, "user", req.message, merged_facts)

    # 6. Classify intent and fetch relevant memory
    intent, memory_keys = classify_intent(req.message)
    logger.info("Intent: %s → memory keys: %s", intent, memory_keys)

    if memory_keys:
        relevant_facts = get_facts_by_keys(req.customer_id, memory_keys)
    else:
        relevant_facts = get_active_facts(req.customer_id)

    # 7. Build natural language context (NEVER raw DB values)
    memory_context = build_memory_context(relevant_facts, lang)
    logger.info("Memory context: %s", memory_context[:200])

    # Get recent chat history
    history = get_recent_history(req.customer_id, limit=6)

    # 8. Build full prompt and generate response
    prompt = build_full_prompt(req.message, memory_context, history, lang)
    logger.info("Prompt length: %d chars", len(prompt))

    response = generate_response(prompt)

    # 9. Save assistant response
    save_chat_message(req.customer_id, "assistant", response)

    # 10. Generate recall suggestions
    all_facts = get_active_facts(req.customer_id)
    suggestions = build_recall_suggestions(all_facts, intent, lang)

    return ChatResponse(
        response=response,
        extracted_facts=[{"key": f["key"], "value": f["value"]} for f in merged_facts],
        intent=intent,
        suggestions=suggestions,
        language=lang,
    )


def _merge_facts(regex_facts: list, llm_facts: list) -> list:
    """
    Merge regex and LLM extracted facts.
    Regex facts take priority for same keys (more reliable).
    """
    merged = {}

    # LLM facts first (lower priority)
    for f in llm_facts:
        key = f.get("key", "")
        if key:
            merged[key] = f

    # Regex facts override (higher priority)
    for f in regex_facts:
        key = f.get("key", "")
        if key:
            merged[key] = f

    return list(merged.values())


# ──────────────────────────────────────────────
# Streaming Chat Endpoint
# ──────────────────────────────────────────────
@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """
    Same as /chat but streams the LLM response token-by-token.
    Returns an NDJSON stream where each line is a JSON object.
    """
    # 1. Detect language
    lang = detect_language(req.message)

    # 2. Fast regex fact extraction
    regex_facts = extract_facts(req.message)

    # 3. LLM fact extraction
    llm_facts = extract_facts_llm(req.message)

    # 4. Merge facts
    merged_facts = _merge_facts(regex_facts, llm_facts)

    # 5. Upsert facts into PostgreSQL
    if merged_facts:
        upsert_facts(req.customer_id, merged_facts)

    # Save user message
    save_chat_message(req.customer_id, "user", req.message, merged_facts)

    # 6. Classify intent and fetch relevant memory
    intent, memory_keys = classify_intent(req.message)

    if memory_keys:
        relevant_facts = get_facts_by_keys(req.customer_id, memory_keys)
    else:
        relevant_facts = get_active_facts(req.customer_id)

    # 7. Build context
    memory_context = build_memory_context(relevant_facts, lang)
    history = get_recent_history(req.customer_id, limit=6)
    prompt = build_full_prompt(req.message, memory_context, history, lang)

    # 8. Generate suggestions (sent as first chunk before streaming starts)
    all_facts = get_active_facts(req.customer_id)
    suggestions = build_recall_suggestions(all_facts, intent, lang)

    def event_stream():
        # Send metadata as the first line
        meta = {
            "type": "meta",
            "extracted_facts": [{"key": f["key"], "value": f["value"]} for f in merged_facts],
            "intent": intent,
            "suggestions": suggestions,
            "language": lang,
        }
        yield json.dumps(meta) + "\n"

        # Stream LLM tokens
        full_response = ""
        for chunk in generate_response_stream(prompt):
            data = json.loads(chunk)
            if data.get("done"):
                full_response = data.get("full_response", "")
            yield json.dumps({"type": "token", **data}) + "\n"

        # Save assistant response after streaming completes
        if full_response:
            save_chat_message(req.customer_id, "assistant", full_response)


    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ──────────────────────────────────────────────
# Memory Endpoints
# ──────────────────────────────────────────────
@app.get("/memory/{customer_id}/profile")
def read_profile(customer_id: str):
    """Get structured customer profile for the left panel."""
    return get_profile(customer_id)


@app.get("/memory/{customer_id}/timeline")
def read_timeline(customer_id: str, limit: int = 50):
    """Get chronological memory events for the timeline panel."""
    timeline = get_timeline(customer_id, limit)
    # Serialize datetime objects
    for item in timeline:
        for key in ("created_at", "updated_at"):
            if key in item and hasattr(item[key], "isoformat"):
                item[key] = item[key].isoformat()
    return {"timeline": timeline}


@app.get("/memory/{customer_id}/suggestions")
def read_suggestions(customer_id: str, intent: str = "general", lang: str = "en"):
    """Get memory recall suggestions."""
    facts = get_active_facts(customer_id)
    suggestions = build_recall_suggestions(facts, intent, lang)
    return {"suggestions": suggestions}


@app.get("/memory/{customer_id}/history")
def read_history(customer_id: str, limit: int = 20):
    """Get recent chat history."""
    history = get_recent_history(customer_id, limit)
    for item in history:
        if "created_at" in item and hasattr(item["created_at"], "isoformat"):
            item["created_at"] = item["created_at"].isoformat()
    return {"history": history}
