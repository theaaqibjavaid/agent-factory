"""NeuraHive v2 public core API.

The v2 namespace is independent from the legacy AgentFactory platform. Core
contracts are lightweight and dependency-injected; concrete model, memory,
tool, policy, and platform integrations live outside the core.
"""

from neurahive.core import (
    Agent,
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentRuntime,
    ExecutionError,
)
from neurahive.tools import Tool, ToolRegistry, ToolResult
from neurahive.providers import MemoryProvider, Model, ModelProvider
from neurahive.contracts import (
    MCPProvider,
    ModelRequest,
    ModelResponse,
    ToolExecutor,
    VerificationResult,
    Verifier,
)
from neurahive.runtime import BasicAgentExecutor, InProcessRuntime

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentContext",
    "AgentResult",
    "AgentRuntime",
    "ExecutionError",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "MemoryProvider",
    "Model",
    "ModelProvider",
    "MCPProvider",
    "ModelRequest",
    "ModelResponse",
    "ToolExecutor",
    "VerificationResult",
    "Verifier",
    "BasicAgentExecutor",
    "InProcessRuntime",
]

__version__ = "2.0.0.dev0"
