"""
MemBridge AI — PostgreSQL Database Module
Handles connection pooling, schema migration, and query helpers.
"""

import psycopg2
import psycopg2.extras
import json
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Connection config
# ──────────────────────────────────────────────
DB_CONFIG = {
    "dbname": "membridge",
    "user": "postgres",
    "password": "1234",
    "host": "127.0.0.1",
    "port": 5432,
}

# ──────────────────────────────────────────────
# Connection pool (simple thread-safe approach)
# ──────────────────────────────────────────────
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg2 import pool
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            **DB_CONFIG,
        )
        logger.info("PostgreSQL connection pool created.")
    return _pool


@contextmanager
def get_connection():
    """Get a connection from the pool. Auto-commits on success, rolls back on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor=True):
    """Get a cursor from a pooled connection."""
    with get_connection() as conn:
        cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()


# ──────────────────────────────────────────────
# Schema migration
# ──────────────────────────────────────────────
SCHEMA_SQL = """
-- Structured memory facts with versioning
CREATE TABLE IF NOT EXISTS memory_facts (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           JSONB NOT NULL,
    confidence      REAL DEFAULT 0.8,
    version         INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'active' CHECK (status IN ('active', 'superseded')),
    source          TEXT DEFAULT 'user' CHECK (source IN ('user', 'inferred', 'llm')),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_facts_user_status ON memory_facts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_facts_user_key    ON memory_facts(user_id, key, status);
CREATE INDEX IF NOT EXISTS idx_facts_timeline    ON memory_facts(user_id, created_at DESC);

-- Chat history
CREATE TABLE IF NOT EXISTS chat_history (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    extracted_facts JSONB DEFAULT '[]'::jsonb,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_user ON chat_history(user_id, created_at DESC);
"""


def init_db():
    """Run schema migration. Safe to call multiple times."""
    with get_cursor(dict_cursor=False) as cur:
        cur.execute(SCHEMA_SQL)
    logger.info("Database schema initialized.")


# ──────────────────────────────────────────────
# JSON helpers
# ──────────────────────────────────────────────
def to_jsonb(value):
    """Convert a Python value to a JSON string for JSONB columns."""
    if isinstance(value, str):
        return json.dumps(value)
    return json.dumps(value)


def from_jsonb(value):
    """Parse a JSONB value back to Python. psycopg2 auto-parses most cases."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value
