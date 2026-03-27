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
# Importance Scoring Logic
# ──────────────────────────────────────────────
def calculate_importance(fact: Dict[str, Any], current_time: datetime) -> float:
    """Calculate the dynamic importance score of a memory fact."""
    # 1. Category Weight
    type_weights = {"financial": 1.0, "profile": 0.8, "preference": 0.5, "event": 0.3}
    w1_val = type_weights.get(fact.get("type", "profile"), 0.5)

    # 2. Recency
    updated_at = fact.get("updated_at")
    if not isinstance(updated_at, datetime):
        updated_at = current_time
    days_since_update = max((current_time - updated_at).days, 0)
    w2_val = 1.0 / (1.0 + days_since_update)

    # 3. Frequency & Access
    access_count = fact.get("access_count", 0)
    created_at = fact.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = current_time
    days_since_creation = max((current_time - created_at).days, 0)
    
    w3_val = access_count / (days_since_creation + 1.0)
    w4_val = min(access_count * 0.1, 1.0)

    score = (0.4 * w1_val) + (0.3 * w2_val) + (0.2 * w3_val) + (0.1 * w4_val)
    return round(score, 4)

def _record_access_and_recalculate(facts: List[Dict[str, Any]]):
    """Increments access tracking and recalculates importance scores."""
    if not facts: return
    now = datetime.now()
    updates = []
    for fact in facts:
        fact["access_count"] = fact.get("access_count", 0) + 1
        fact["last_accessed_at"] = now
        fact["importance_score"] = calculate_importance(fact, now)
        updates.append((fact["access_count"], now, fact["importance_score"], fact["id"]))

    with get_cursor() as cur:
        for acc_count, l_acc, imp_score, f_id in updates:
            cur.execute(
                "UPDATE memory_facts SET access_count = %s, last_accessed_at = %s, importance_score = %s WHERE id = %s",
                (acc_count, l_acc, imp_score, f_id)
            )

# ──────────────────────────────────────────────
# Users and Sessions
# ──────────────────────────────────────────────
def upsert_user(user_id: str) -> None:
    """Ensure a user exists in the database."""
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (id) VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (user_id,)
        )

def get_or_create_session(user_id: str, session_id: Optional[str] = None) -> str:
    """Get or create an active session for the user."""
    import uuid
    upsert_user(user_id)
    with get_cursor() as cur:
        if session_id:
            cur.execute(
                """
                INSERT INTO sessions (id, user_id) VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (session_id, user_id)
            )
            return session_id
        else:
            cur.execute(
                "SELECT id FROM sessions WHERE user_id = %s AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
                (user_id,)
            )
            row = cur.fetchone()
            if row:
                return row["id"]
            
            new_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO sessions (id, user_id) VALUES (%s, %s)",
                (new_id, user_id)
            )
            return new_id



# ──────────────────────────────────────────────
# Upsert Logic (with conflict handling)
# ──────────────────────────────────────────────
def upsert_fact(
    user_id: str,
    key: str,
    value: Any,
    confidence: float = 0.8,
    source: str = "user",
    type_: str = "profile",
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
            INSERT INTO memory_facts (user_id, type, key, value, confidence, version, source)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id, user_id, type, key, value, confidence, importance_score, version, status, source, created_at, updated_at
            """,
            (user_id, type_, key, json_value, confidence, new_version, source),
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
            type_=fact.get("type", "profile"),
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
            SELECT id, type, key, value, confidence, importance_score, access_count, version, source, created_at, updated_at, last_accessed_at
            FROM memory_facts
            WHERE user_id = %s AND status = 'active'
            ORDER BY key, updated_at DESC
            """,
            (user_id,),
        )
        facts = [dict(row) for row in cur.fetchall()]
        _record_access_and_recalculate(facts)
        return facts


def get_facts_by_keys(user_id: str, keys: List[str]) -> List[Dict[str, Any]]:
    """Fetch specific fact types for a user."""
    if not keys:
        return get_active_facts(user_id)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, type, key, value, confidence, importance_score, access_count, version, source, created_at, updated_at, last_accessed_at
            FROM memory_facts
            WHERE user_id = %s AND status = 'active' AND key = ANY(%s)
            ORDER BY key, updated_at DESC
            """,
            (user_id, keys),
        )
        facts = [dict(row) for row in cur.fetchall()]
        _record_access_and_recalculate(facts)
        return facts

def get_relevant_facts(user_id: str, keys: List[str], limit: int = 8) -> List[Dict[str, Any]]:
    """Fetch the most critically relevant facts dynamically ranked by importance."""
    if keys:
        requested = get_facts_by_keys(user_id, keys)
        req_ids = {f["id"] for f in requested}
        remaining_limit = limit - len(requested)
        top_other = []
        if remaining_limit > 0:
            with get_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, type, key, value, confidence, importance_score, access_count, version, source, created_at, updated_at, last_accessed_at
                    FROM memory_facts
                    WHERE user_id = %s AND status = 'active'
                    ORDER BY importance_score DESC
                    LIMIT %s
                    """,
                    (user_id, limit)
                )
                all_top = [dict(row) for row in cur.fetchall()]
                top_other = [f for f in all_top if f["id"] not in req_ids][:remaining_limit]
        final_facts = requested + top_other
    else:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, type, key, value, confidence, importance_score, access_count, version, source, created_at, updated_at, last_accessed_at
                FROM memory_facts
                WHERE user_id = %s AND status = 'active'
                ORDER BY importance_score DESC
                LIMIT %s
                """,
                (user_id, limit)
            )
            final_facts = [dict(row) for row in cur.fetchall()]
            
    _record_access_and_recalculate(final_facts)
    return final_facts


def get_fact_history(user_id: str, key: str) -> List[Dict[str, Any]]:
    """Get full version history for a specific fact key."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, type, key, value, confidence, importance_score, access_count, version, status, source, created_at, updated_at, last_accessed_at
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
            SELECT id, type, key, value, confidence, importance_score, access_count, version, status, source, created_at, updated_at, last_accessed_at
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
            "type": fact["type"],
            "value": fact["value"],
            "confidence": fact["confidence"],
            "importance_score": fact["importance_score"],
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
    session_id: str,
    role: str,
    content: str,
    extracted_facts: Optional[List[Dict]] = None,
) -> None:
    """Save a chat message to history."""
    facts_json = json.dumps(extracted_facts or [])
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_history (user_id, session_id, role, content, extracted_facts)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (user_id, session_id, role, content, facts_json),
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
