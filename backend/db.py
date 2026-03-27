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
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Structured memory facts with versioning
CREATE TABLE IF NOT EXISTS memory_facts (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    type            TEXT NOT NULL DEFAULT 'profile' CHECK (type IN ('financial', 'profile', 'preference', 'event')),
    key             TEXT NOT NULL,
    value           JSONB NOT NULL,
    confidence      REAL DEFAULT 0.8,
    importance_score REAL DEFAULT 0.0,
    version         INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'active' CHECK (status IN ('active', 'superseded')),
    source          TEXT DEFAULT 'user' CHECK (source IN ('user', 'inferred', 'llm')),
    affects         JSONB DEFAULT '[]',
    used_for        JSONB DEFAULT '[]',
    relations       JSONB DEFAULT '[]',
    access_count    INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP DEFAULT NOW(),
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
    user_id         TEXT NOT NULL REFERENCES users(id),
    session_id      TEXT REFERENCES sessions(id),
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
        # Safe migrations for existing deployments
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'profile';")
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS importance_score REAL DEFAULT 0.0;")
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;")
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP DEFAULT NOW();")
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS affects JSONB DEFAULT '[]';")
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS used_for JSONB DEFAULT '[]';")
        cur.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS relations JSONB DEFAULT '[]';")
        cur.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS session_id TEXT;")
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
