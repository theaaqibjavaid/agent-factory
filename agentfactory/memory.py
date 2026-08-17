"""
Persistent Memory — SQLite-backed conversation and fact storage for agents.

Provides:
- Conversation history persistence across restarts
- Key-value fact storage (agent "learned" knowledge)
- Per-agent memory isolation (memory_id)
- Automatic pruning of old history beyond context window

Usage:
    from agentfactory.memory import PersistentMemory

    # Create or load memory for an agent
    mem = PersistentMemory(agent_id="my-excel-agent")

    # Save conversation
    mem.save_history(messages=[{"role": "user", "content": "Hello"}])

    # Load conversation
    history = mem.load_history(limit=50)

    # Save a fact
    mem.save_fact("user_preferred_format", "xlsx")

    # Recall a fact
    format = mem.load_fact("user_preferred_format")
"""

import sqlite3
import json
import os
import threading
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from agentfactory.crypto import encrypt_text, decrypt_text, encryption_enabled

logger = structlog.get_logger()

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"),
    ".agentfactory",
    "memory.db"
)


class PersistentMemory:
    """
    Persistent memory store for AI agents using SQLite.

    Stores conversation history and facts that persist across agent restarts.
    Each agent gets isolated memory via agent_id.
    """

    def __init__(self, agent_id: str = "default", db_path: Optional[str] = None):
        self.agent_id = agent_id
        self.db_path = db_path or os.getenv("MEMORY_DB_PATH", DEFAULT_DB_PATH)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database with required tables."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")

            # Conversation history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    message_role TEXT NOT NULL,
                    message_content TEXT NOT NULL,
                    message_metadata TEXT,
                    created_at TEXT NOT NULL,
                    seq INTEGER NOT NULL
                )
            """)

            # Facts table (key-value store)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    fact_value TEXT NOT NULL,
                    fact_type TEXT DEFAULT 'string',
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(agent_id, fact_key)
                )
            """)

            # Indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_agent_seq
                ON memory_history(agent_id, seq)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_facts_agent_key
                ON memory_facts(agent_id, fact_key)
            """)

            conn.commit()
            conn.close()

            logger.debug(f"Memory DB initialized for agent '{self.agent_id}' at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def save_history(self, messages: List[Dict[str, Any]]) -> None:
        """
        Save conversation messages to persistent storage.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                # Get current max sequence
                row = conn.execute(
                    "SELECT MAX(seq) as max_seq FROM memory_history WHERE agent_id = ?",
                    (self.agent_id,)
                ).fetchone()
                start_seq = (row["max_seq"] or 0) + 1

                for i, msg in enumerate(messages):
                    content = str(msg.get("content", ""))
                    metadata = json.dumps(msg.get("metadata", {}))
                    # S-9 encryption-at-rest: only active when AGENTFACTORY_ENCRYPTION_KEY is set.
                    if encryption_enabled():
                        content = encrypt_text(content)
                        metadata = encrypt_text(metadata)

                    conn.execute("""
                        INSERT INTO memory_history
                            (agent_id, message_role, message_content, message_metadata, created_at, seq)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        self.agent_id,
                        msg.get("role", "unknown"),
                        content,
                        metadata,
                        now,
                        start_seq + i,
                    ))

                conn.commit()
                logger.debug(f"Saved {len(messages)} messages to history for {self.agent_id}")
            finally:
                conn.close()

    def load_history(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Load conversation history from persistent storage.

        Args:
            limit: Maximum number of messages to return
            offset: Skip this many recent messages (for pagination)

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        with self._lock:
            conn = self._get_conn()
            try:
                # Get messages in chronological order
                rows = conn.execute("""
                    SELECT message_role, message_content, message_metadata
                    FROM memory_history
                    WHERE agent_id = ?
                    ORDER BY seq DESC
                    LIMIT ? OFFSET ?
                """, (self.agent_id, limit, offset)).fetchall()

                # Reverse to get chronological order (oldest first)
                rows = list(reversed(rows))

                messages = []
                for row in rows:
                    stored_content = row["message_content"]
                    stored_metadata = row["message_metadata"]
                    # S-9: Fernet tokens decrypt; legacy plaintext passes through.
                    if encryption_enabled():
                        stored_content = decrypt_text(stored_content)
                        stored_metadata = decrypt_text(stored_metadata)
                    try:
                        metadata = json.loads(stored_metadata) if stored_metadata else {}
                    except json.JSONDecodeError:
                        metadata = {}

                    messages.append({
                        "role": row["message_role"],
                        "content": stored_content,
                        "metadata": metadata,
                    })

                return messages
            finally:
                conn.close()

    def clear_history(self) -> int:
        """
        Clear all conversation history for this agent.

        Returns:
            Number of messages deleted
        """
        with self._lock:
            conn = self._get_conn()
            try:
                result = conn.execute(
                    "DELETE FROM memory_history WHERE agent_id = ?",
                    (self.agent_id,)
                )
                conn.commit()
                return result.rowcount
            finally:
                conn.close()

    def save_fact(self, key: str, value: Any, fact_type: str = "string", confidence: float = 1.0) -> None:
        """
        Save a fact/key-value pair for this agent.

        Args:
            key: Fact key (e.g., "preferred_format")
            value: Fact value (will be JSON-serialized if not a string)
            fact_type: Type hint for the value
            confidence: Confidence level (0.0 to 1.0)
        """
        now = datetime.now(timezone.utc).isoformat()
        value_str = value if isinstance(value, str) else json.dumps(value)
        if encryption_enabled():
            value_str = encrypt_text(value_str)

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO memory_facts
                        (agent_id, fact_key, fact_value, fact_type, confidence, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.agent_id,
                    key,
                    value_str,
                    fact_type,
                    confidence,
                    now,
                    now,
                ))
                conn.commit()
                logger.debug(f"Saved fact '{key}' for {self.agent_id}")
            finally:
                conn.close()

    def load_fact(self, key: str) -> Optional[Any]:
        """
        Load a fact value by key.

        Args:
            key: Fact key to retrieve

        Returns:
            The fact value, or None if not found.
            Non-string values are JSON-deserialized.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("""
                    SELECT fact_value, fact_type FROM memory_facts
                    WHERE agent_id = ? AND fact_key = ?
                """, (self.agent_id, key)).fetchone()

                if row is None:
                    return None

                value = row["fact_value"]
                fact_type = row["fact_type"]
                if encryption_enabled():
                    value = decrypt_text(value)

                # Try to deserialize non-string types
                if fact_type in ("json", "dict", "list", "int", "float", "bool"):
                    try:
                        return json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        return value
                return value
            finally:
                conn.close()

    def list_facts(self, prefix: Optional[str] = None) -> Dict[str, Any]:
        """
        List all facts for this agent.

        Args:
            prefix: Filter keys by prefix

        Returns:
            Dict mapping fact keys to values
        """
        with self._lock:
            conn = self._get_conn()
            try:
                if prefix:
                    rows = conn.execute("""
                        SELECT fact_key, fact_value, fact_type
                        FROM memory_facts
                        WHERE agent_id = ? AND fact_key LIKE ?
                        ORDER BY fact_key
                    """, (self.agent_id, f"{prefix}%")).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT fact_key, fact_value, fact_type
                        FROM memory_facts
                        WHERE agent_id = ?
                        ORDER BY fact_key
                    """, (self.agent_id,)).fetchall()

                facts = {}
                for row in rows:
                    value = row["fact_value"]
                    fact_type = row["fact_type"]
                    if encryption_enabled():
                        value = decrypt_text(value)
                    if fact_type in ("json", "dict", "list", "int", "float", "bool"):
                        try:
                            facts[row["fact_key"]] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            facts[row["fact_key"]] = value
                    else:
                        facts[row["fact_key"]] = value

                return facts
            finally:
                conn.close()

    def delete_fact(self, key: str) -> bool:
        """
        Delete a fact by key.

        Returns:
            True if the fact was deleted, False if it didn't exist
        """
        with self._lock:
            conn = self._get_conn()
            try:
                result = conn.execute(
                    "DELETE FROM memory_facts WHERE agent_id = ? AND fact_key = ?",
                    (self.agent_id, key)
                )
                conn.commit()
                return result.rowcount > 0
            finally:
                conn.close()

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about stored history."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("""
                    SELECT COUNT(*) as count,
                           MIN(created_at) as first_seen,
                           MAX(created_at) as last_seen
                    FROM memory_history
                    WHERE agent_id = ?
                """, (self.agent_id,)).fetchone()

                return {
                    "message_count": row["count"] if row else 0,
                    "first_seen": row["first_seen"] if row and row["first_seen"] else None,
                    "last_seen": row["last_seen"] if row and row["last_seen"] else None,
                    "agent_id": self.agent_id,
                }
            finally:
                conn.close()

    def close(self) -> None:
        """Close the database connection (no-op for SQLite, but kept for interface compatibility)."""
        pass


def clear_all_memory(db_path: Optional[str] = None) -> int:
    """
    Clear all memory for all agents (dangerous — use only for testing).

    Returns:
        Total number of records deleted
    """
    db = db_path or DEFAULT_DB_PATH
    if not os.path.exists(db):
        return 0

    conn = sqlite3.connect(db)
    try:
        h_count = conn.execute("DELETE FROM memory_history").rowcount
        f_count = conn.execute("DELETE FROM memory_facts").rowcount
        conn.commit()
        return h_count + f_count
    finally:
        conn.close()