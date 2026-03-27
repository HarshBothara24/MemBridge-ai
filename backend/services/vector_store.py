"""
MemBridge AI — FAISS Vector Store
Semantic search over past conversations using sentence-transformers + FAISS.
"""

import faiss
import numpy as np
import os
import json
import logging
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 produces 384-dim vectors

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VECTOR_INDEX_DIR = os.path.join(DATA_DIR, "vectors")

# ──────────────────────────────────────────────
# Lazy-loaded model (loaded once on first use)
# ──────────────────────────────────────────────
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model lazily so startup stays fast."""
    global _model
    if _model is None:
        logger.info("Loading embedding model '%s' …", EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _model


# ──────────────────────────────────────────────
# Per-customer store: FAISS index + text mapping
# ──────────────────────────────────────────────
# In-memory cache so we don't reload from disk every call
_stores: Dict[str, Dict[str, Any]] = {}


def _index_path(customer_id: str) -> str:
    return os.path.join(VECTOR_INDEX_DIR, f"{customer_id}.index")


def _mapping_path(customer_id: str) -> str:
    return os.path.join(VECTOR_INDEX_DIR, f"{customer_id}_map.json")


def _load_store(customer_id: str) -> Dict[str, Any]:
    """Load or create a per-customer FAISS index + text mapping."""
    if customer_id in _stores:
        return _stores[customer_id]

    os.makedirs(VECTOR_INDEX_DIR, exist_ok=True)
    idx_file = _index_path(customer_id)
    map_file = _mapping_path(customer_id)

    if os.path.exists(idx_file) and os.path.exists(map_file):
        index = faiss.read_index(idx_file)
        with open(map_file, "r", encoding="utf-8") as f:
            mapping = json.load(f)
    else:
        # L2 (Euclidean) flat index — simple & exact
        index = faiss.IndexFlatL2(EMBEDDING_DIM)
        mapping = {"texts": [], "metadata": []}

    store = {"index": index, "mapping": mapping}
    _stores[customer_id] = store
    return store


def _persist_store(customer_id: str) -> None:
    """Write index + mapping to disk."""
    store = _stores.get(customer_id)
    if store is None:
        return

    os.makedirs(VECTOR_INDEX_DIR, exist_ok=True)
    faiss.write_index(store["index"], _index_path(customer_id))
    with open(_mapping_path(customer_id), "w", encoding="utf-8") as f:
        json.dump(store["mapping"], f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def embed_text(text: str) -> np.ndarray:
    """
    Convert a text string to a 384-dim embedding vector.

    Returns:
        numpy array of shape (384,)
    """
    model = _get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.astype("float32")


def add_to_vector_store(
    customer_id: str,
    text: str,
    role: str = "user",
) -> None:
    """
    Embed a text and add it to the customer's FAISS index.

    Args:
        customer_id: Unique customer identifier.
        text: The message text to store.
        role: 'user' or 'assistant'.
    """
    store = _load_store(customer_id)
    vec = embed_text(text).reshape(1, -1)

    store["index"].add(vec)
    store["mapping"]["texts"].append(text)
    store["mapping"]["metadata"].append({"role": role})

    _persist_store(customer_id)


def search_similar(
    customer_id: str,
    query: str,
    k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Find the top-k most similar past messages for a customer.

    Args:
        customer_id: Unique customer identifier.
        query: The query text to search against.
        k: Number of results to return.

    Returns:
        List of dicts: [{"text": ..., "role": ..., "score": ...}, ...]
        Sorted by relevance (lowest L2 distance = most similar).
    """
    store = _load_store(customer_id)

    # Nothing stored yet
    if store["index"].ntotal == 0:
        return []

    query_vec = embed_text(query).reshape(1, -1)

    # Don't request more results than we have
    actual_k = min(k, store["index"].ntotal)
    distances, indices = store["index"].search(query_vec, actual_k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue  # FAISS can return -1 for missing entries
        results.append({
            "text": store["mapping"]["texts"][idx],
            "role": store["mapping"]["metadata"][idx].get("role", "unknown"),
            "score": float(dist),
        })

    return results
