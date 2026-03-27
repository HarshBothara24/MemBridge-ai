"""
MemBridge AI — Memory Engine
Core structured memory system with upsert, conflict handling, and retrieval.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from db import get_cursor, to_jsonb

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Upsert Logic (with conflict handling)
# ──────────────────────────────────────────────
def upsert_fact(
    user_id: str,
    key: str,
    value: Any,
    confidence: float = 0.8,
    source: str = "user",
) -> Dict[str, Any]:
    """
    Insert or update a memory fact.

    If an active fact with the same (user_id, key) exists:
      1. Mark old fact as 'superseded'
      2. Insert new fact with version = old.version + 1

    Returns the newly inserted fact.
    """
    with get_cursor() as cur:
        # Check for existing active fact with same key
        cur.execute(
            """
            SELECT id, value, version, confidence
            FROM memory_facts
            WHERE user_id = %s AND key = %s AND status = 'active'
            ORDER BY version DESC
            LIMIT 1
            """,
            (user_id, key),
        )
        existing = cur.fetchone()

        new_version = 1
        json_value = to_jsonb(value)

        if existing:
            old_value = existing["value"]
            # Only supersede if value actually changed
            if json.dumps(old_value) != json_value:
                # Mark old as superseded
                cur.execute(
                    """
                    UPDATE memory_facts
                    SET status = 'superseded', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (existing["id"],),
                )
                new_version = existing["version"] + 1
                logger.info(
                    "Superseded fact %s=%s (v%d) for user %s",
                    key, old_value, existing["version"], user_id,
                )
            else:
                # Same value — just update confidence if higher
                if confidence > existing["confidence"]:
                    cur.execute(
                        """
                        UPDATE memory_facts
                        SET confidence = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (confidence, existing["id"]),
                    )
                return dict(existing)

        # Insert new fact
        cur.execute(
            """
            INSERT INTO memory_facts (user_id, key, value, confidence, version, source)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id, user_id, key, value, confidence, version, status, source, created_at, updated_at
            """,
            (user_id, key, json_value, confidence, new_version, source),
        )
        new_fact = cur.fetchone()
        logger.info(
            "Stored fact %s=%s (v%d, confidence=%.2f) for user %s",
            key, value, new_version, confidence, user_id,
        )
        return dict(new_fact)


def upsert_facts(
    user_id: str,
    facts: List[Dict[str, Any]],
    source: str = "user",
) -> List[Dict[str, Any]]:
    """
    Upsert multiple facts at once.

    Each fact dict should have: {key, value, confidence?}
    """
    results = []
    for fact in facts:
        result = upsert_fact(
            user_id=user_id,
            key=fact["key"],
            value=fact["value"],
            confidence=fact.get("confidence", 0.8),
            source=source,
        )
        results.append(result)
    return results


# ──────────────────────────────────────────────
# Retrieval
# ──────────────────────────────────────────────
def get_active_facts(user_id: str) -> List[Dict[str, Any]]:
    """Get all active (non-superseded) facts for a user."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, key, value, confidence, version, source, created_at, updated_at
            FROM memory_facts
            WHERE user_id = %s AND status = 'active'
            ORDER BY key, updated_at DESC
            """,
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_facts_by_keys(user_id: str, keys: List[str]) -> List[Dict[str, Any]]:
    """Fetch specific fact types for a user."""
    if not keys:
        return get_active_facts(user_id)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, key, value, confidence, version, source, created_at, updated_at
            FROM memory_facts
            WHERE user_id = %s AND status = 'active' AND key = ANY(%s)
            ORDER BY key, updated_at DESC
            """,
            (user_id, keys),
        )
        return [dict(row) for row in cur.fetchall()]


def get_fact_history(user_id: str, key: str) -> List[Dict[str, Any]]:
    """Get full version history for a specific fact key."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, key, value, confidence, version, status, source, created_at, updated_at
            FROM memory_facts
            WHERE user_id = %s AND key = %s
            ORDER BY version DESC
            """,
            (user_id, key),
        )
        return [dict(row) for row in cur.fetchall()]


def get_timeline(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all facts ordered chronologically for timeline display."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, key, value, confidence, version, status, source, created_at, updated_at
            FROM memory_facts
            WHERE user_id = %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def get_profile(user_id: str) -> Dict[str, Any]:
    """
    Build a structured customer profile from active facts.
    Returns a dict grouped by fact key with confidence info.
    """
    facts = get_active_facts(user_id)
    profile = {}
    for fact in facts:
        profile[fact["key"]] = {
            "value": fact["value"],
            "confidence": fact["confidence"],
            "version": fact["version"],
            "updated_at": fact["updated_at"].isoformat() if isinstance(fact["updated_at"], datetime) else str(fact["updated_at"]),
            "source": fact["source"],
        }
    return {
        "user_id": user_id,
        "facts": profile,
        "total_facts": len(facts),
    }


# ──────────────────────────────────────────────
# Chat History
# ──────────────────────────────────────────────
def save_chat_message(
    user_id: str,
    role: str,
    content: str,
    extracted_facts: Optional[List[Dict]] = None,
) -> None:
    """Save a chat message to history."""
    facts_json = json.dumps(extracted_facts or [])
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_history (user_id, role, content, extracted_facts)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (user_id, role, content, facts_json),
        )


def get_recent_history(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get the most recent chat messages for a user."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT role, content, extracted_facts, created_at
            FROM chat_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
        # Return in chronological order
        return [dict(row) for row in reversed(rows)]
