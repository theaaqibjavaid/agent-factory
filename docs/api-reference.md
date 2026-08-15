# API Reference

Complete Python API for AgentFactory core classes.

## agentfactory.llm_manager

### `FailoverLLMManager`

```python
from agentfactory.llm_manager import FailoverLLMManager, LLMConfig
```

Manages LLM failover pipeline with budget tracking and Langfuse tracing.

#### Constructor

```python
manager = FailoverLLMManager(
    pipeline: list[LLMConfig] | None = None,
    daily_budget_usd: float = 5.00,
    model_preferences: dict[str, list[str]] | None = None,
    langfuse_secret_key: str | None = None,
    langfuse_public_key: str | None = None,
    langfuse_host: str = "https://cloud.langfuse.com",
    temperature: float = 0.2,
)
```

#### Methods

| Method | Description |
|--------|-------------|
| `generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 4000, temperature: float = None) -> str` | Generate text with automatic failover |
| `generate_with_failover(prompt: str, system_prompt: str = "", max_tokens: int = 4000, temperature: float = None) -> str` | Explicit failover generation |
| `handle_rate_limit_failover() -> str` | Advance to next provider, return its name |
| `reset()` | Reset spend tracking and current index |
| `get_current_provider() -> str` | Get current provider name |
| `get_spend() -> float` | Get current daily spend in USD |
| `is_budget_exhausted() -> bool` | Check if daily budget is exceeded |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipeline` | list[LLMConfig] | Ordered list of LLM configs |
| `daily_budget_usd` | float | Daily budget cap |
| `current_index` | int | Current provider index |
| `current_spend_usd` | float | Today's spend |
| `date` | date | Current tracking date |

### `LLMConfig`

```python
from agentfactory.llm_manager import LLMConfig

config = LLMConfig(
    provider: str,           # "google", "openai", "anthropic"
    model: str,              # e.g., "gemini-2.5-flash"
    api_key_env: str,        # env var name, e.g., "GEMINI_API_KEY"
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
)
```

## agentfactory.base_agent

### `AgentFactory`

```python
from agentfactory.base_agent import AgentFactory

factory = AgentFactory(
    llm_manager: FailoverLLMManager | None = None,
)
```

Main factory for creating and managing agents.

#### Methods

| Method | Description |
|--------|-------------|
| `create_agent(config: AgentConfig) -> RunnableAgent` | Create an agent instance |
| `create_agent_from_yaml(path: str) -> RunnableAgent` | Create agent from YAML config |
| `build_system_prompt(config: AgentConfig) -> str` | Build system prompt (static) |

### `RunnableAgent`

```python
from agentfactory.base_agent import RunnableAgent

agent = factory.create_agent(config)
result = agent.run(task_prompt: str, max_iterations: int = 10) -> str
```

#### Methods

| Method | Description |
|--------|-------------|
| `run(task_prompt: str, max_iterations: int = 10) -> str` | Execute a task |
| `run_with_config(task_prompt: str, config: dict) -> str` | Execute with runtime config |

### `AgentConfig`

```python
from agentfactory.base_agent import AgentConfig

config = AgentConfig(
    name: str,
    rank: str = "Junior",                     # Senior, Junior, QA, Manager
    role_description: str = "",
    model_preference: list[str] | None = None,
    tools: list[str] | None = None,
    system_instructions: str = "",
    constitutional_boundaries: dict | None = None,
    allow_delegation: bool = False,
    max_worker_iterations: int = 5,
    budget_usd: float = 5.00,
)
```

### `AgentExecutionStats`

Dataclass tracking agent execution metrics.

| Field | Type | Description |
|-------|------|-------------|
| `total_calls` | int | Total LLM calls made |
| `total_tokens` | int | Total tokens used |
| `total_cost_usd` | float | Total cost in USD |
| `calls_per_provider` | dict | Calls broken down by provider |
| `failover_count` | int | Number of failovers triggered |

## agentfactory.base_tools

### `@tool` decorator

```python
from agentfactory.base_tools import tool, SafetyLevel

@tool(
    name="my_tool",
    description="Description",
    category="custom",
    cost_per_call_usd=0.01,
    safety_level=SafetyLevel.SAFE,
    tags=["tag1", "tag2"],
)
def my_tool(arg: str) -> str:
    return result
```

### `ToolDef`

```python
@dataclass
class ToolDef:
    name: str
    func: Callable
    description: str
    args_schema: dict | None
    category: str = "generic"
    cost_per_call_usd: float = 0.0
    safety_level: SafetyLevel = SafetyLevel.SAFE
    tags: list[str] = []
```

### `ToolRegistry`

Class-based registry for managing tools.

```python
from agentfactory.base_tools import ToolRegistry, ToolWrapper

registry = ToolRegistry()
registry.register_function(my_tool_func)
registry.register_mcp_tool(name, metadata, server_name, client)
```

| Method | Description |
|--------|-------------|
| `register_function(func)` | Register a function as a tool |
| `register_mcp_tool(name, metadata, server_name, client)` | Register an MCP tool |
| `get(name) -> ToolWrapper \| None` | Get a tool by name |
| `list_tools() -> list[str]` | List tool names |
| `list_tools_detailed() -> list[dict]` | List tools with metadata |
| `get_by_category(category) -> list[ToolWrapper]` | Get tools by category |
| `get_by_tag(tag) -> list[ToolWrapper]` | Get tools by tag |

### `ToolWrapper`

Wraps a `ToolDef` for async execution.

#### Methods

| Method | Description |
|--------|-------------|
| `execute(arguments: dict) -> str` | Execute the tool (async) |

### Global Functions

| Function | Description |
|----------|-------------|
| `list_tools() -> list[str]` | List all registered tool names |
| `list_tools_detailed() -> list[dict]` | List tools with metadata |
| `get_tool(name: str) -> ToolDef` | Get a tool definition |
| `get_tools_by_category(category: str) -> list[ToolDef]` | Get tools by category |
| `get_tools_by_tag(tag: str) -> list[ToolDef]` | Get tools by tag |
| `register_tool(tool_def: ToolDef)` | Manually register a ToolDef |
| `clear_registry()` | Clear all registered tools |
| `to_langchain_tools(names: list[str]) -> list[Tool]` | Convert to LangChain tools |

### `SafetyLevel`

```python
from agentfactory.base_tools import SafetyLevel

class SafetyLevel(str, Enum):
    SAFE = "safe"              # No risk, read-only
    MODIFIED = "modified"      # Writes files but safe
    DESTRUCTIVE = "destructive"  # Could cause data loss
```

### `ToolMetadata`

```python
@dataclass
class ToolMetadata:
    name: str
    category: str = "generic"
    description: str = ""
    cost_per_call_usd: float = 0.0
    safety_level: SafetyLevel = SafetyLevel.SAFE
    tags: list[str] = []
```

### `ToolCall`

```python
from agentfactory.base_tools import ToolCall
from pydantic import BaseModel

class ToolCall(BaseModel):
    name: str
    arguments: dict
    id: str = ""
    result: str | None = None
```

## agentfactory.verifier

### `Verifier`

```python
from agentfactory.verifier import Verifier

verifier = Verifier()
verifier.add_check(name="pytest", command="pytest tests/", timeout=120)
report = verifier.run(repo_path=".")
```

#### Methods

| Method | Description |
|--------|-------------|
| `add_check(name: str, command: str, timeout: int = 60, fail_on_stderr: bool = False)` | Add a verification check |
| `run(repo_path: str, feature_name: str = None, branch_name: str = None) -> VerificationReport` | Run all checks |

### `VerificationReport`

```python
from agentfactory.verifier import VerificationReport

report = VerificationReport(feature_name="test", branch_name="feature/test")
report.add_check(check: AuditResult)
json_report = report.to_dict()
```

| Field | Type | Description |
|-------|------|-------------|
| `feature_name` | str | Feature being verified |
| `branch_name` | str | Branch being verified |
| `checks` | list[AuditResult] | All check results |
| `overall_passed` | bool | True if all checks passed |
| `created_at` | datetime | Report timestamp |

#### Methods

| Method | Description |
|--------|-------------|
| `add_check(check: AuditResult)` | Add a check result |
| `to_dict() -> dict` | Serialize to dictionary |

### `AuditResult`

```python
from agentfactory.verifier import AuditResult

result = AuditResult(
    name="pytest",
    passed=True,
    message="All tests passed",
    stdout="",
    stderr="",
    failed_lines=[],
)
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Check name |
| `passed` | bool | Pass/fail status |
| `message` | str | Result message |
| `stdout` | str | Command stdout |
| `stderr` | str | Command stderr |
| `failed_lines` | list[str] | Pruned failing lines |

### `FailedCheck`

```python
from agentfactory.verifier import FailedCheck

@dataclass
class FailedCheck:
    line_number: int
    line_content: str
    context_before: list[str]
    context_after: list[str]
```

## agentfactory.config

### `AgentFactorySettings`

```python
from agentfactory.config import AgentFactorySettings

settings = AgentFactorySettings()
```

Pydantic Settings class that loads from `.env`.

| Field | Type | Default |
|-------|------|---------|
| `gemini_api_key` | str \| None | — |
| `openai_api_key` | str \| None | — |
| `anthropic_api_key` | str \| None | — |
| `tavily_api_key` | str \| None | — |
| `langfuse_secret_key` | str \| None | — |
| `langfuse_public_key` | str \| None | — |
| `langfuse_host` | str | `https://cloud.langfuse.com` |
| `backend_path` | str \| None | — |
| `frontend_path` | str \| None | — |
| `admin_path` | str \| None | — |
| `agent_daily_budget_usd` | float | `5.00` |
| `llm_temperature` | float | `0.2` |
