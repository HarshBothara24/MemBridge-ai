"""
MemBridge AI — FastAPI Backend
Cognitive Memory Layer with structured memory, intent-based retrieval,
temporal reasoning, and bilingual (EN/HI) support.
"""

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import json
import logging
import os
from dotenv import load_dotenv
load_dotenv()

from db import init_db
from memory import extract_facts
from memory_engine import (
    upsert_facts, get_active_facts, get_facts_by_keys, get_relevant_facts,
    get_timeline, get_profile, save_chat_message, get_recent_history,
    get_or_create_session
)
from intent_router import classify_intent
from context_builder import detect_language, build_memory_context, build_recall_suggestions, build_full_prompt
from llm_service import extract_facts_llm, generate_response, generate_response_stream
from loan_calculator import get_calculation_context
from services.stt_service import transcribe
from services.tts_service import generate_audio
from services.language_service import detect_language as detect_lang_voice

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


# Ensure static dirs exist
os.makedirs("static/audio", exist_ok=True)
os.makedirs("static/temp", exist_ok=True)

app.mount("/audio", StaticFiles(directory="static/audio"), name="audio")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    customer_id: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    extracted_facts: list
    intent: str
    suggestions: list
    language: str
    session_id: str


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

    # Ensure Session
    session_id = get_or_create_session(req.customer_id, req.session_id)

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
    save_chat_message(req.customer_id, session_id, "user", req.message, merged_facts)

    # 6. Classify intent and fetch relevant memory dynamically ranked
    intent, memory_keys = classify_intent(req.message)
    logger.info("Intent: %s → memory keys: %s", intent, memory_keys)

    # Use Top-K Relevance Selector
    relevant_facts = get_relevant_facts(req.customer_id, memory_keys, limit=8)

    # 7. Build natural language context (NEVER raw DB values)
    memory_context = build_memory_context(relevant_facts, lang)
    logger.info("Memory context: %s", memory_context[:200])

    # Get recent chat history
    history = get_recent_history(req.customer_id, limit=6)

    # 8. Build full prompt and generate response
    prompt = build_full_prompt(req.message, memory_context, history, lang)

    # Inject pre-computed loan calculations if applicable
    calc_context = get_calculation_context(req.message, relevant_facts, lang)
    if calc_context:
        prompt = calc_context + "\n\n" + prompt

    logger.info("Prompt length: %d chars", len(prompt))

    response = generate_response(prompt)

    # 9. Save assistant response
    save_chat_message(req.customer_id, session_id, "assistant", response)

    # 10. Generate recall suggestions
    all_facts = get_active_facts(req.customer_id)
    suggestions = build_recall_suggestions(all_facts, intent, lang)

    return ChatResponse(
        response=response,
        extracted_facts=[{"key": f["key"], "value": f["value"]} for f in merged_facts],
        intent=intent,
        suggestions=suggestions,
        language=lang,
        session_id=session_id,
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

    # Ensure Session
    session_id = get_or_create_session(req.customer_id, req.session_id)

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
    save_chat_message(req.customer_id, session_id, "user", req.message, merged_facts)

    # 6. Classify intent and fetch relevant memory dynamically ranked
    intent, memory_keys = classify_intent(req.message)

    # Use Top-K Relevance Selector
    relevant_facts = get_relevant_facts(req.customer_id, memory_keys, limit=8)

    # 7. Build context
    memory_context = build_memory_context(relevant_facts, lang)
    history = get_recent_history(req.customer_id, limit=6)
    prompt = build_full_prompt(req.message, memory_context, history, lang)

    # Inject pre-computed loan calculations if applicable
    calc_context = get_calculation_context(req.message, relevant_facts, lang)
    if calc_context:
        prompt = calc_context + "\n\n" + prompt

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
            "session_id": session_id,
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
            save_chat_message(req.customer_id, session_id, "assistant", full_response)


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


# ──────────────────────────────────────────────
# Voice Endpoint
# ──────────────────────────────────────────────
@app.post("/voice")
async def voice_chat(
    audio: UploadFile = File(...),
    customer_id: str = Form(...),
    session_id: str = Form(None),
):
    """
    Voice interaction endpoint.
    1. Transcribe audio via Whisper
    2. Detect language
    3. Process via memory pipeline
    4. Generate TTS audio response
    Returns: { text, audio_url, language, transcription }
    """
    import tempfile

    suffix = os.path.splitext(audio.filename or "audio.webm")[-1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        # 1. Transcribe
        result = transcribe(tmp_path)
        transcribed_text = result["text"]
        whisper_lang = result["language"]

        if not transcribed_text.strip():
            return {"error": "Could not transcribe audio", "text": "", "audio_url": None, "language": "en"}

        # 2. Language detection — combine Whisper hint + text heuristic
        text_lang = detect_lang_voice(transcribed_text)
        # Whisper lang takes priority for hi/en, text heuristic catches mixed
        lang = text_lang if text_lang == "mixed" else whisper_lang

        # 3. Process via existing memory pipeline
        session = get_or_create_session(customer_id, session_id)
        regex_facts = extract_facts(transcribed_text)
        llm_facts = extract_facts_llm(transcribed_text)
        merged = {f["key"]: f for f in llm_facts}
        merged.update({f["key"]: f for f in regex_facts})
        merged_facts = list(merged.values())

        if merged_facts:
            upsert_facts(customer_id, merged_facts)
        save_chat_message(customer_id, session, "user", transcribed_text, merged_facts)

        intent, memory_keys = classify_intent(transcribed_text)
        relevant_facts = get_facts_by_keys(customer_id, memory_keys) if memory_keys else get_active_facts(customer_id)
        memory_context = build_memory_context(relevant_facts, lang)
        history = get_recent_history(customer_id, limit=6)
        prompt = build_full_prompt(transcribed_text, memory_context, history, lang)

        calc_context = get_calculation_context(transcribed_text, relevant_facts, lang)
        if calc_context:
            prompt = calc_context + "\n\n" + prompt

        response_text = generate_response(prompt)
        save_chat_message(customer_id, session, "assistant", response_text)

        # 4. TTS
        audio_filename = generate_audio(response_text, lang)
        audio_url = f"{BASE_URL}/audio/{audio_filename}"

        return {
            "transcription": transcribed_text,
            "text": response_text,
            "audio_url": audio_url,
            "language": lang,
            "extracted_facts": [{"key": f["key"], "value": f["value"]} for f in merged_facts],
        }

    except Exception as e:
        logger.error("Voice endpoint failed: %s", e)
        return {"error": str(e), "text": "", "audio_url": None, "language": "en"}
    finally:
        os.unlink(tmp_path)
