from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json
import logging

from memory import extract_facts, save_memory, get_memory, build_prompt
from services.vector_store import add_to_vector_store, search_similar

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    customer_id: str

def generate_response(prompt: str) -> str:
    payload = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "stream": False,
    }
    res = requests.post("http://localhost:11434/api/generate", json=payload)
    res.raise_for_status()
    return res.json()["response"]

@app.post("/chat")
def chat(req: ChatRequest):
    # 1. Extract facts from the user message
    facts = extract_facts(req.message)

    # 2. Save user message + facts to JSON memory
    save_memory(req.customer_id, req.message, role="user", facts=facts)

    # 3. Add user message to FAISS vector store
    add_to_vector_store(req.customer_id, req.message, role="user")

    # 4. Retrieve semantically similar past messages
    semantic_results = search_similar(req.customer_id, req.message, k=3)

    # 5. Build prompt combining structured memory + semantic memory
    prompt = build_prompt(req.message, req.customer_id, semantic_results=semantic_results)
    logger.info("Prompt length: %d chars", len(prompt))

    # 6. Call the LLM
    response = generate_response(prompt)

    # 7. Save assistant response to JSON memory + vector store
    save_memory(req.customer_id, response, role="assistant")
    add_to_vector_store(req.customer_id, response, role="assistant")

    # 8. Return response
    return {"response": response}


@app.get("/memory/{customer_id}")
def read_memory(customer_id: str):
    """Debug endpoint — returns structured memory for a customer."""
    return get_memory(customer_id)


@app.get("/memory/{customer_id}/search")
def search_memory(customer_id: str, q: str, k: int = 3):
    """Debug endpoint — semantic search over a customer's conversation history."""
    results = search_similar(customer_id, q, k=k)
    return {"query": q, "results": results}
