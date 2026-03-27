"""
Call Routes — Exotel voice call integration.
Handles bilingual (EN/HI) voice conversations via Whisper STT + gTTS.
Delegates all LLM/memory logic to the existing chat pipeline.
"""

import logging
import os
import tempfile
from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from services import stt_service
from services.language_service import detect_language
from services.tts_service import generate_audio
from utils.audio_utils import download_audio
from fastapi.responses import FileResponse

# Import existing core pipeline (DO NOT modify these)
from memory import extract_facts
from memory_engine import upsert_facts, get_active_facts, get_facts_by_keys, save_chat_message, get_recent_history
from intent_router import classify_intent
from context_builder import build_memory_context, build_recall_suggestions, build_full_prompt
from llm_service import extract_facts_llm, generate_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/call", tags=["voice"])

BASE_URL = os.getenv("BASE_URL", "https://fb7e-103-97-164-106.ngrok-free.app")

BILINGUAL_GREETING = "Namaste! Main aapka AI assistant hoon. Aapki kaise madad kar sakta hoon?"


def _process(user_id: str, input_text: str) -> str:
    """
    Thin wrapper that calls the existing MemBridge pipeline.
    Mirrors the chat endpoint logic without duplicating LLM/memory code.
    """
    from context_builder import detect_language as _detect_lang

    lang = _detect_lang(input_text)

    regex_facts = extract_facts(input_text)
    llm_facts = extract_facts_llm(input_text)

    # Merge (regex takes priority)
    merged = {f["key"]: f for f in llm_facts}
    merged.update({f["key"]: f for f in regex_facts})
    merged_facts = list(merged.values())

    if merged_facts:
        upsert_facts(user_id, merged_facts)

    save_chat_message(user_id, "user", input_text, merged_facts)

    intent, memory_keys = classify_intent(input_text)
    relevant_facts = get_facts_by_keys(user_id, memory_keys) if memory_keys else get_active_facts(user_id)

    memory_context = build_memory_context(relevant_facts, lang)
    history = get_recent_history(user_id, limit=6)
    prompt = build_full_prompt(input_text, memory_context, history, lang)

    response = generate_response(prompt)
    save_chat_message(user_id, "assistant", response)

    return response


def _exotel_xml(audio_url: str, action_url: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="en-IN">
        Hello! I am your bank agent, How may I help you?
    </Say>
    <Record 
        action="{action_url}" 
        method="POST" 
        maxLength="30"
        timeout="5"
        finishOnKey="#"
    />
</Response>"""

def _gather_config(greeting_url: str) -> dict:
    """
    JSON config returned to Exotel's dynamic Gather.
    Tells Gather: play this audio, record speech, post result back here.
    """
    return {
        "mssg": greeting_url,       # audio URL to play as prompt
        "timeout": 5,
        "finishOnKey": "#",
        "numDigits": 1,
    }


# ──────────────────────────────────────────────
# /call/start — Exotel webhook on call connect
# ──────────────────────────────────────────────
@router.api_route("/start", methods=["GET", "POST"], response_class=HTMLResponse)
async def call_start(request: Request):
    """
    Called by Exotel when a call connects.
    Plays bilingual greeting and starts recording.
    """
    params = dict(request.query_params)
    form = await request.form() if request.method == "POST" else {}
    caller = params.get("CallFrom") or params.get("From") or form.get("CallFrom") or form.get("From", "unknown")
    logger.info("Call started from: %s", caller)

    try:
        audio_url = f"{BASE_URL}/audio/greeting.mp3"
        action_url = f"{BASE_URL}/call/handle?caller={caller}"
        return HTMLResponse(
    content="""
<Response>
    <Say>Hello test working</Say>
    <Record action="https://fb7e-103-97-164-106.ngrok-free.app/call/handle" method="POST" />
</Response>
""",
    media_type="application/xml"
)
    except Exception as e:
        logger.error("call/start failed: %s", e)
        return HTMLResponse(content=_fallback_xml(), status_code=200)


# ──────────────────────────────────────────────
# /call/handle — Exotel webhook after recording
# ──────────────────────────────────────────────
@router.api_route("/handle", methods=["GET", "POST"], response_class=HTMLResponse)
async def call_handle(request: Request, caller: str = "unknown"):
    """
    Called by Exotel after user speaks.
    Downloads recording → transcribes → processes → responds.
    """
    params = dict(request.query_params)
    form_data = await request.form() if request.method == "POST" else {}
    recording_url = params.get("RecordingUrl") or form_data.get("RecordingUrl", "")
    caller = params.get("CallFrom") or params.get("From") or form_data.get("CallFrom") or form_data.get("From", caller)

    logger.info("Handling recording from %s: %s", caller, recording_url)

    if not recording_url:
        return HTMLResponse(content=_error_xml("Sorry, I didn't catch that. Please try again.", "en"))

    try:
        # 1. Download audio
        audio_path = download_audio(recording_url)

        # 2. Transcribe
        result = stt_service.transcribe(audio_path)
        text = result["text"]

        if not text.strip():
            return HTMLResponse(content=_error_xml("I didn't hear anything. Please speak after the beep.", "en"))

        # 3. Detect language
        lang = detect_language(text)
        logger.info("Transcription: '%s' | Language: %s", text[:80], lang)

        # 4. Process via existing MemBridge pipeline
        response_text = _process(user_id=caller, input_text=text)

        # 5. Generate TTS
        audio_file = generate_audio(response_text, lang)
        audio_url = f"{BASE_URL}/audio/{audio_file}"
        action_url = f"{BASE_URL}/call/handle?caller={caller}"

        return HTMLResponse(
    content=_exotel_xml(audio_url, action_url),
    media_type="application/xml"
)

    except FileNotFoundError:
        return HTMLResponse(content=_error_xml("Could not retrieve your audio. Please try again.", "en"))
    except Exception as e:
        logger.error("call/handle failed: %s", e)
        return HTMLResponse(content=_error_xml("Something went wrong. Please try again.", "en"))


# ──────────────────────────────────────────────
# /test-call — Manual test endpoint
# ──────────────────────────────────────────────
@router.post("/test-call")
async def test_call(
    audio: UploadFile = File(...),
    phone_number: str = Form(...),
):
    """
    Test endpoint: upload an audio file + phone number.
    Returns transcription, detected language, response text, and audio URL.
    """
    suffix = os.path.splitext(audio.filename)[-1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        result = stt_service.transcribe(tmp_path)
        text = result["text"]

        if not text.strip():
            return JSONResponse({"error": "Empty transcription"}, status_code=400)

        lang = detect_language(text)
        response_text = _process(user_id=phone_number, input_text=text)
        audio_file = generate_audio(response_text, lang)
        audio_url = f"{BASE_URL}/audio/{audio_file}"

        return {
            "transcription": text,
            "detected_language": lang,
            "response_text": response_text,
            "audio_url": audio_url,
        }
    finally:
        os.unlink(tmp_path)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _error_xml(message: str, lang: str) -> str:
    """Generate a simple error response XML."""
    try:
        audio_file = generate_audio(message, lang)
        audio_url = f"{BASE_URL}/audio/{audio_file}"
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Hangup/>
</Response>"""
    except Exception:
        return """<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup/></Response>"""


def _fallback_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup/></Response>"""
