"""
Memory Tools — Persistent storage and recall for agents.

These tools allow agents to save and retrieve information across sessions.
"""

import os
import structlog
from typing import Optional, Any
from agentfactory.base_tools import tool, SafetyLevel

logger = structlog.get_logger()


def _get_memory(agent_id: str = None):
    """Get a PersistentMemory instance."""
    from agentfactory.memory import PersistentMemory

    if agent_id is None:
        agent_id = os.getenv("MEMORY_AGENT_ID", "default")
    return PersistentMemory(agent_id=agent_id)


@tool(
    "save_memory",
    category="memory",
    safety_level=SafetyLevel.SAFE,
    tags=["memory", "persist", "save"],
)
def save_memory(key: str, value: str, agent_id: Optional[str] = None) -> str:
    """
    Save a fact/key-value pair to persistent memory.

    This persists across agent restarts and is isolated per agent_id.

    Args:
        key: The fact key (e.g., "user_preferred_name", "task_completed")
        value: The fact value to store
        agent_id: Agent identifier (defaults to MEMORY_AGENT_ID env or "default")

    Returns:
        Confirmation message

    Example:
        save_memory("user_name", "Alice")
        save_memory("last_project", "ecommerce-site", agent_id="project-manager")
    """
    try:
        mem = _get_memory(agent_id)
        mem.save_fact(key, value)
        mem.close()
        return f"Saved to memory: {key} = {value}"
    except Exception as e:
        return f"Error saving memory: {str(e)}"


@tool(
    "recall_memory",
    category="memory",
    safety_level=SafetyLevel.SAFE,
    tags=["memory", "persist", "recall"],
)
def recall_memory(key: str, agent_id: Optional[str] = None) -> str:
    """
    Recall a fact from persistent memory.

    Args:
        key: The fact key to retrieve
        agent_id: Agent identifier (defaults to MEMORY_AGENT_ID env or "default")

    Returns:
        The stored value, or "Not found" if the key doesn't exist

    Example:
        recall_memory("user_name")  -> "Alice"
        recall_memory("last_project", agent_id="project-manager")
    """
    try:
        mem = _get_memory(agent_id)
        value = mem.load_fact(key)
        mem.close()

        if value is None:
            return f"Not found: no memory stored for key '{key}'"
        return str(value)
    except Exception as e:
        return f"Error recalling memory: {str(e)}"


@tool(
    "list_memory",
    category="memory",
    safety_level=SafetyLevel.SAFE,
    tags=["memory", "list", "all"],
)
def list_memory(agent_id: Optional[str] = None, prefix: Optional[str] = None) -> str:
    """
    List all stored facts for an agent.

    Args:
        agent_id: Agent identifier (defaults to MEMORY_AGENT_ID env or "default")
        prefix: Optional filter to only show keys starting with this prefix

    Returns:
        Formatted list of all stored facts

    Example:
        list_memory()  # List all facts for default agent
        list_memory(prefix="user_")  # Only user-related facts
    """
    try:
        mem = _get_memory(agent_id)
        facts = mem.list_facts(prefix=prefix)
        mem.close()

        if not facts:
            return f"No facts stored for agent_id={agent_id or 'default'}" + (f" with prefix '{prefix}'" if prefix else "")

        lines = [f"Memory facts for agent '{agent_id or 'default'}':"]
        for key, value in sorted(facts.items()):
            lines.append(f"  {key}: {str(value)[:100]}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing memory: {str(e)}"


@tool(
    "forget_memory",
    category="memory",
    safety_level=SafetyLevel.DESTRUCTIVE,
    tags=["memory", "forget", "delete"],
)
def forget_memory(key: str, agent_id: Optional[str] = None) -> str:
    """
    Delete a fact from persistent memory.

    WARNING: This operation cannot be undone.

    Args:
        key: The fact key to delete
        agent_id: Agent identifier (defaults to MEMORY_AGENT_ID env or "default")

    Returns:
        Confirmation message
    """
    try:
        mem = _get_memory(agent_id)
        deleted = mem.delete_fact(key)
        mem.close()

        if deleted:
            return f"Deleted memory: {key}"
        return f"Key '{key}' not found — nothing to delete"
    except Exception as e:
        return f"Error forgetting memory: {str(e)}"
