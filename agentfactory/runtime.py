"""
Platform Agent Runtime (Phase 2) — agents-as-data execution engine.

Turns a platform ``agents`` DB row into a running agent:
- ``render_agent_config`` — system prompt + tool manifest (Phase 2.1)
- ``RunEventBroker`` — per-run SSE event stream (design.md §6 event names:
  ``run.start | token | tool_call | tool_result | verify | memory | cost | run.end | error``)
- ``PlatformAgentRuntime`` — streaming run loop using native LLM tool calls,
  verification, per-run stats/cost, and budget + safety gates (2.2/2.5)
- ``execute_run`` / ``start_run_execution`` — orchestration + worker entry
  point with FAILED recovery via retries (2.6)

The LLM call is injectable via ``llm_generate`` (or the module-level test
hook ``_LLM_GENERATE_OVERRIDE``) so the runtime is fully testable without
API keys; production uses ``FailoverLLMManager.generate_with_tools``.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import structlog

# Ensure built-in tools are registered in the global registry.
import agentfactory.tools  # noqa: F401
from agentfactory.base_agent import AgentPersona
from agentfactory.base_tools import SafetyLevel, ToolRegistry, ToolWrapper, get_tool
from agentfactory.llm_manager import FailoverLLMManager
from agentfactory.memory import PersistentMemory
from agentfactory.verifier import Verifier

logger = structlog.get_logger()


# --------------------------------------------------------------------------
# Event broker (SSE per run)
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_event(event_name: str, **data: Any) -> Dict[str, Any]:
    """Build an SSE event dict (seq is assigned by the broker)."""
    return {"event": event_name, "data": data, "ts": _now_iso()}


class RunEventBroker:
    """Buffers the event stream for one run and fans it out to SSE clients."""

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._seq = 0
        self._condition = asyncio.Condition()
        self.finished = False

    @property
    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

    async def publish(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Append an event and notify waiting stream subscribers."""
        async with self._condition:
            self._seq += 1
            event["seq"] = self._seq
            self._events.append(event)
            self._condition.notify_all()
        return event

    def finish(self) -> None:
        """Mark the stream as complete (no more events will be published)."""
        self.finished = True

    async def stream(self, after_seq: int = 0):
        """
        Async iterator over events with ``seq > after_seq``.

        Replays buffered events first, then waits for live events. Exits once
        the run is finished and all events have been delivered.
        """
        index = 0
        while index < len(self._events) and self._events[index]["seq"] <= after_seq:
            index += 1
        while True:
            while index < len(self._events):
                yield self._events[index]
                index += 1
            if self.finished:
                return
            async with self._condition:
                await self._condition.wait()


_RUN_BROKERS: Dict[str, RunEventBroker] = {}


def get_broker(run_id: str) -> RunEventBroker:
    """Get (creating if needed) the event broker for a run."""
    broker = _RUN_BROKERS.get(run_id)
    if broker is None:
        broker = RunEventBroker()
        _RUN_BROKERS[run_id] = broker
    return broker


def reset_broker(run_id: str) -> RunEventBroker:
    """Replace the run's broker with a fresh one (used on retry, Phase 2.6)."""
    broker = RunEventBroker()
    _RUN_BROKERS[run_id] = broker
    return broker


# --------------------------------------------------------------------------
# Agent config rendering (Phase 2.1)
# --------------------------------------------------------------------------

def memory_scope_id(workspace_id: str, agent_id: str) -> str:
    """Composite memory scope key: workspace-scoped per agent."""
    return f"{workspace_id}:{agent_id}"


def workspace_root_for(workspace_id: str) -> str:
    """Sandbox root for a workspace's custom code (path-scope, Phase 4.1)."""
    base = os.getenv("AGENTFACTORY_WORKSPACE_ROOT", os.path.join(os.path.expanduser("~"), ".agentfactory", "workspaces"))
    return os.path.join(base, workspace_id)


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def agent_row_to_persona(row: dict) -> AgentPersona:
    """Build an AgentPersona from a platform agents DB row."""
    return AgentPersona(
        rank=row.get("rank") or "Junior",
        responsibilities=[row["role_description"]] if row.get("role_description") else [],
        system_instructions=row.get("system_instructions") or "",
        model_preferences=_json_list(row.get("model_preferences")) or ["gemini-2.5-flash"],
        max_budget_usd_per_day=float(row.get("max_budget_usd_per_day") or 5.0),
        max_iterations=int(row.get("max_iterations") or 20),
        temperature=float(row.get("temperature") or 0.2),
    )


def _custom_tool_defs(workspace_id: Optional[str], names: List[str]) -> Dict[str, Any]:
    """Load enabled custom tool registrations the agent references (Phase 4.1)."""
    if not workspace_id:
        return {}
    from agentfactory.app import db
    from agentfactory.custom_tools import tool_def_from_registration

    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tool_registrations WHERE workspace_id = ? AND enabled = 1",
            (workspace_id,),
        ).fetchall()
    finally:
        conn.close()

    wanted = set(names)
    defs: Dict[str, Any] = {}
    for row in rows:
        data = dict(row)
        if data["name"] not in wanted or not data.get("code"):
            continue
        try:
            defs[data["name"]] = tool_def_from_registration(data, workspace_root=workspace_root_for(workspace_id))
        except Exception as e:  # noqa: BLE001 — a broken custom tool must not sink the agent
            logger.warning("Custom tool failed to load", workspace=workspace_id, tool=data["name"], error=str(e))
    return defs


def build_tool_registry(agent_row: dict) -> Tuple[ToolRegistry, List[Dict[str, Any]]]:
    """
    Create a fresh ToolRegistry seeded with the agent's configured tools.

    Resolves built-in tools from the SDK registry first, then workspace custom
    tool registrations by name (Phase 4.1). Returns ``(registry, manifest)``
    where manifest is the OpenAI-style tool schema list with a ``safety``
    field appended for the UI.
    """
    registry = ToolRegistry()
    manifest: List[Dict[str, Any]] = []
    names = _json_list(agent_row.get("tools"))
    custom_defs = _custom_tool_defs(agent_row.get("workspace_id"), names)
    for name in names:
        tool_def = custom_defs.get(name)
        if tool_def is None:
            try:
                tool_def = get_tool(name)
            except KeyError:
                logger.warning("Agent references unknown tool", agent=agent_row.get("id"), tool=name)
                continue
        # Register the ToolDef directly so its metadata (safety, cost, schema)
        # survives into the runtime registry regardless of how it was created.
        registry._tools[name] = ToolWrapper(tool_def)
        wrapper = registry.get(name)
        if wrapper is None:
            continue
        parameters = tool_def.args_schema or wrapper.signature or {"properties": {}, "required": []}
        manifest.append({
            "name": name,
            "description": wrapper.metadata.description,
            "parameters": parameters,
            "safety": wrapper.metadata.safety_level.value if isinstance(wrapper.metadata.safety_level, SafetyLevel) else str(wrapper.metadata.safety_level),
            "category": wrapper.metadata.category,
            "cost_per_call_usd": wrapper.metadata.cost_per_call_usd,
        })
    return registry, manifest


def _skill_instructions(workspace_id: Optional[str], skill_names: List[str]) -> str:
    """
    Resolve skill instructions for the agent's configured skills (Phase 4.2).

    Skill ``dependencies`` are expanded depth-first before the skill itself
    (deduplicated, cycle-safe) so prerequisite knowledge precedes dependent
    instructions in the rendered prompt.
    """
    if not workspace_id or not skill_names:
        return ""
    from agentfactory.app import db

    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT name, metadata FROM skill_registrations WHERE workspace_id = ? AND enabled = 1",
            (workspace_id,),
        ).fetchall()
    finally:
        conn.close()

    by_name: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        try:
            by_name[row["name"]] = json.loads(row["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            by_name[row["name"]] = {}

    ordered: List[str] = []

    def resolve(name: str, stack: List[str]) -> None:
        if name in ordered:
            return
        if name in stack:
            logger.warning("Skill dependency cycle detected", skill=name, chain=stack + [name])
            return
        meta = by_name.get(name)
        if meta is None:
            return
        for dep in meta.get("dependencies") or []:
            resolve(dep, stack + [name])
        ordered.append(name)

    for name in skill_names:
        resolve(name, [])

    parts = []
    for name in ordered:
        meta = by_name.get(name, {})
        instructions = meta.get("instructions") or meta.get("description")
        if instructions:
            parts.append(f"[Skill: {name}] {instructions}")
    return "\n\n".join(parts)


def build_system_prompt(agent_row: dict, manifest: List[Dict[str, Any]]) -> str:
    """Render the agent's system prompt from its DB config (reuses the SDK prompt format)."""
    name = agent_row.get("name") or "Agent"
    rank = agent_row.get("rank") or "Junior"
    prompt = agent_row.get("system_instructions") or (
        f"You are an {rank} level AI agent named {name}.\n"
        f"Responsibilities: {agent_row.get('role_description') or 'Execute the task at hand.'}\n"
        f"Maximum budget per day: ${float(agent_row.get('max_budget_usd_per_day') or 5.0):.2f}\n"
    )
    if manifest:
        lines = [f"- {t['name']}({', '.join((t['parameters'].get('properties') or {}).keys())}): {t['description']}"
                 for t in manifest]
        prompt += "\n\nAvailable tools:\n" + "\n".join(lines)
    # Skills (Phase 4.2): instructions from workspace skill registrations.
    skills = _skill_instructions(agent_row.get("workspace_id"), _json_list(agent_row.get("skills")))
    if skills:
        prompt += "\n\nYou have the following skills:\n\n" + skills
    prompt += f"\n\nCurrent date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    prompt += "\n\nAlways think step by step. Use tools when needed."
    return prompt


def build_llm_pipeline(
    model_preferences: Optional[List[str]] = None,
    workspace_id: Optional[str] = None,
) -> List[Any]:
    """
    Build a FailoverLLMManager pipeline for the agent's model preferences.

    Resolves workspace ``model_connections`` first (Phase 4.4 — custom
    providers like Ollama/OpenRouter with base URLs), then falls back to the
    SDK's provider-prefix mapping.
    """
    from agentfactory.llm_manager import FailoverLLMManager, LLMConfig

    prefs = _json_list(model_preferences) or ["gemini-2.5-flash"]
    connections: Dict[str, Dict[str, Any]] = {}
    if workspace_id:
        from agentfactory.app import db

        conn = db.get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM model_connections WHERE workspace_id = ? AND enabled = 1",
                (workspace_id,),
            ).fetchall()
        finally:
            conn.close()
        connections = {dict(r)["model"]: dict(r) for r in rows}

    provider_env = {"google": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    pipeline: List[Any] = []
    for model in prefs:
        row = connections.get(model)
        if row:
            provider = row.get("provider") or "openai_compatible"
            key_ref = row.get("key_ref") or provider_env.get(provider, "OPENAI_API_KEY")
            pipeline.append(LLMConfig(
                provider=provider,
                model=model,
                api_key_env=key_ref,
                base_url=row.get("base_url"),
                is_free_tier=provider == "ollama",
            ))
        else:
            pipeline.append(_config_from_prefix(model))
    return pipeline or FailoverLLMManager.DEFAULT_PIPELINE.copy()


def _config_from_prefix(model: str):
    """Map a model name to an LLMConfig via the SDK's provider-prefix rules."""
    from agentfactory.llm_manager import FailoverLLMManager, LLMConfig

    lower = model.lower()
    if "gemini" in lower:
        return LLMConfig(provider="google", model=model, api_key_env="GEMINI_API_KEY", is_free_tier=True)
    if "claude" in lower:
        return LLMConfig(provider="anthropic", model=model, api_key_env="ANTHROPIC_API_KEY")
    if "gpt" in lower or "o3" in lower or "o1" in lower or "llama" in lower:
        return LLMConfig(provider="openai", model=model, api_key_env="OPENAI_API_KEY")
    return FailoverLLMManager.DEFAULT_PIPELINE[0]


def render_agent_config(agent_row: dict) -> Dict[str, Any]:
    """Render a DB agent row into a runnable config (system prompt + tool manifest)."""
    _, manifest = build_tool_registry(agent_row)
    return {
        "id": agent_row.get("id"),
        "name": agent_row.get("name"),
        "rank": agent_row.get("rank"),
        "system_prompt": build_system_prompt(agent_row, manifest),
        "tools": manifest,
        "model_preferences": _json_list(agent_row.get("model_preferences")),
        "hitl_mode": agent_row.get("hitl_mode", "auto"),
        "max_iterations": agent_row.get("max_iterations", 20),
        "max_budget_usd_per_day": agent_row.get("max_budget_usd_per_day", 5.0),
    }


# --------------------------------------------------------------------------
# Platform runtime
# --------------------------------------------------------------------------

# Test/embedding hook: when set, replaces the LLM call entirely (async fn
# taking (messages, tool_manifest) and returning {"text", "tool_calls"}).
_LLM_GENERATE_OVERRIDE: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None


class PlatformAgentRuntime:
    """Runs a platform agent row end-to-end, publishing SSE events."""

    def __init__(
        self,
        agent_row: dict,
        workspace_settings: Optional[dict] = None,
        memory: Optional[PersistentMemory] = None,
        llm_generate: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
    ) -> None:
        self.agent_row = agent_row
        self.workspace_settings = workspace_settings or {}
        self.persona = agent_row_to_persona(agent_row)
        self.registry, self.manifest = build_tool_registry(agent_row)
        self.allow_destructive = bool(self.workspace_settings.get("allow_destructive", False))
        self.memory = memory
        self.verifier = Verifier()
        self.stats: Dict[str, Any] = {
            "iterations": 0,
            "tool_calls_made": 0,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "duration_seconds": 0.0,
            "errors": [],
            "successes": [],
            "budget_usd": self.persona.max_budget_usd_per_day,
        }
        manager = FailoverLLMManager(
            pipeline=build_llm_pipeline(self.persona.model_preferences, agent_row.get("workspace_id")),
            daily_budget_usd=self.persona.max_budget_usd_per_day,
        )
        self._llm = llm_generate or _LLM_GENERATE_OVERRIDE or manager.generate_with_tools
        self._manager = manager
        self._mcp_clients: List[Any] = []

    # -- helpers ----------------------------------------------------------

    def _messages(self, task: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": build_system_prompt(self.agent_row, self.manifest)}]
        messages.extend(history)
        messages.append({"role": "user", "content": task})
        return messages

    def _tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in self.manifest]

    async def _attach_mcp_tools(self) -> None:
        """Connect the agent's configured MCP servers and register their tools (Phase 4.3)."""
        server_names = _json_list(self.agent_row.get("mcp_servers"))
        if not server_names:
            return
        from agentfactory.app import db
        from agentfactory.mcp_integration import MCPClient, MCPServerConfig

        conn = db.get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM mcp_servers WHERE workspace_id = ? AND enabled = 1",
                (self.agent_row.get("workspace_id"),),
            ).fetchall()
        finally:
            conn.close()
        servers = {dict(r)["name"]: dict(r) for r in rows}

        for name in server_names:
            row = servers.get(name)
            if row is None:
                logger.warning("Agent references unknown MCP server", agent=self.agent_row.get("id"), server=name)
                continue
            if row.get("transport") != "stdio":
                logger.warning("SSE MCP transport not yet supported by the runtime", server=name)
                continue
            if not row.get("command"):
                logger.warning("MCP server has no command", server=name)
                continue
            # Per-tool enablement (Phase 4.3): servers store the discovered
            # tool list + an enablement map in metadata; disabled tools are
            # never exposed to the agent.
            try:
                mcp_meta = json.loads(row.get("metadata") or "{}")
            except (json.JSONDecodeError, TypeError):
                mcp_meta = {}
            enabled_tools = mcp_meta.get("enabled_tools") or {}
            # Env allowlist: only pass through explicitly permitted variables.
            env = {}
            for key in _json_list(row.get("env_allow")):
                if key in os.environ:
                    env[key] = os.environ[key]
            config = MCPServerConfig(
                name=name,
                command=row["command"],
                args=_json_list(row.get("args")),
                env=env,
                timeout=float(row.get("timeout") or 10.0),
            )
            client = MCPClient(config)
            try:
                await client.connect()
                tools = await client.list_tools()
            except Exception as e:  # noqa: BLE001 — a dead server must not sink the run
                logger.warning("MCP server connection failed", server=name, error=str(e))
                await client.close()
                continue
            self._mcp_clients.append(client)
            for info in tools:
                if enabled_tools.get(info.name, True) is False:
                    logger.info("MCP tool disabled by workspace", server=name, tool=info.name)
                    continue
                self.registry.register_mcp_tool(
                    info.name,
                    info.metadata,
                    server_name=info.server_name,
                    client=client,
                    input_schema=info.input_schema,
                )
                self.manifest.append({
                    "name": info.name,
                    "description": info.description,
                    "parameters": info.input_schema or {"properties": {}, "required": []},
                    "safety": "safe",
                    "category": f"mcp-{name}",
                    "cost_per_call_usd": 0.0,
                })

    async def _execute_tool(self, name: str, arguments: Dict[str, Any], broker: RunEventBroker) -> str:
        """Execute one tool call, enforcing the DESTRUCTIVE safety gate."""
        wrapper = self.registry.get(name)
        if wrapper is None:
            return f"Error: Tool '{name}' is not available to this agent."
        safety = wrapper.metadata.safety_level
        is_destructive = safety == SafetyLevel.DESTRUCTIVE or getattr(safety, "value", None) == "destructive"
        if is_destructive and not self.allow_destructive:
            msg = (
                f"Blocked: tool '{name}' is DESTRUCTIVE and this workspace does not allow "
                "destructive tools. Enable 'allow_destructive' in workspace settings "
                "or run with human-in-the-loop approval."
            )
            await broker.publish(run_event("error", message=msg, tool=name))
            self.stats["errors"].append(msg)
            return msg
        try:
            result = await wrapper.execute(arguments)
        except Exception as e:  # noqa: BLE001 — tool errors are surfaced to the agent
            result = f"Error: Tool '{name}' failed: {e}"
            self.stats["errors"].append(result)
        self.stats["tool_calls_made"] += 1
        self.stats["total_cost_usd"] += wrapper.metadata.cost_per_call_usd
        self.stats["successes"].append(name)
        return result

    # -- main loop ---------------------------------------------------------

    async def run(self, task: str, run_id: str, broker: RunEventBroker) -> Dict[str, Any]:
        """Execute the task loop, publishing SSE events. Returns final result + stats."""
        start = monotonic()

        # Attach MCP servers first so their tools appear in run.start + schemas.
        await self._attach_mcp_tools()

        await broker.publish(run_event(
            "run.start",
            run_id=run_id,
            agent_id=self.agent_row.get("id"),
            agent_name=self.agent_row.get("name"),
            task=task,
            tools=[t["name"] for t in self.manifest],
            hitl_mode=self.agent_row.get("hitl_mode", "auto"),
        ))
        try:
            result = await self._run_loop(task, run_id, broker, start)
        finally:
            for client in self._mcp_clients:
                try:
                    await client.close()
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    pass
        return result

    async def _run_loop(self, task: str, run_id: str, broker: RunEventBroker, start: float) -> Dict[str, Any]:
        """The main agent loop: LLM call → tool calls → verification (Phase 2.2)."""
        history: List[Dict[str, Any]] = []
        final_result = ""
        failed_error: Optional[str] = None
        iterations = max(1, self.persona.max_iterations)

        for i in range(iterations):
            self.stats["iterations"] = i + 1
            try:
                response = await self._llm(self._messages(task, history), self._tool_schemas())
            except PermissionError as e:
                msg = f"Budget exceeded for this agent: {e}"
                await broker.publish(run_event("error", message=msg))
                return {"result": msg, "stats": self._finalize(start), "verification_errors": [], "budget_blocked": True}
            except Exception as e:  # noqa: BLE001
                msg = f"LLM call failed: {e}"
                await broker.publish(run_event("error", message=msg))
                self.stats["errors"].append(msg)
                final_result = msg
                failed_error = msg
                break

            text = (response or {}).get("text") or ""
            tool_calls = (response or {}).get("tool_calls") or []

            if text:
                await broker.publish(run_event("token", content=text))
                history.append({"role": "assistant", "content": text})

            # Execute each tool call, then feed results back to the model
            for tc in tool_calls:
                name = tc.get("name", "")
                arguments = tc.get("arguments") or {}
                await broker.publish(run_event("tool_call", name=name, arguments=arguments))
                result = await self._execute_tool(name, arguments, broker)
                await broker.publish(run_event("tool_result", name=name, result=result[:4000]))
                history.append({"role": "user", "content": json.dumps({"tool": name, "result": result})[:8000]})

            # Verification step (Phase 2.2 — verifier loop)
            verification = await self.verifier.verify_all(text or final_result)
            await broker.publish(run_event(
                "verify",
                passed=verification.passed,
                summary=verification.summary,
                passed_checks=verification.passed_checks,
                failed=len(verification.failed_checks),
            ))

            if not tool_calls:
                final_result = text or final_result
                break

        # Persist the conversation into scoped memory (Phase 2.4)
        if self.memory and history:
            try:
                self.memory.save_history(history)
                await broker.publish(run_event("memory", action="saved_history", messages=len(history)))
            except Exception as e:  # noqa: BLE001
                logger.warning("Could not save run history to memory", error=str(e))

        stats = self._finalize(start)
        await broker.publish(run_event("cost", stats=stats))
        return {"result": final_result, "stats": stats, "verification_errors": [], "error": failed_error}

    def _finalize(self, start: float) -> Dict[str, Any]:
        self.stats["duration_seconds"] = round(monotonic() - start, 3)
        return dict(self.stats)


# --------------------------------------------------------------------------
# Orchestration (worker entry point)
# --------------------------------------------------------------------------

def _get_agent_row(run_row: dict) -> Optional[dict]:
    """Load the agent row for a run, preferring the stored config snapshot."""
    from agentfactory.app import db

    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (run_row["agent_id"],)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_workspace_settings(workspace_id: str) -> dict:
    from agentfactory.app import db

    conn = db.get_db()
    try:
        row = conn.execute("SELECT settings FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return {}
    try:
        parsed = json.loads(row["settings"])
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _update_run(run_id: str, **fields: Any) -> None:
    from agentfactory.app import db

    sets = ", ".join(f"{k} = ?" for k in fields)
    conn = db.get_db()
    try:
        conn.execute(f"UPDATE agent_runs SET {sets}, updated_at = ? WHERE id = ?",
                     (*fields.values(), _now_iso(), run_id))
        conn.commit()
    finally:
        conn.close()


async def execute_run(run_id: str) -> None:
    """Execute a run end-to-end (worker entry point, Phase 2.6)."""
    from agentfactory.app import db

    broker = get_broker(run_id)
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        broker.finish()
        return
    run_row = dict(row)

    agent_row = _get_agent_row(run_row)
    if agent_row is None:
        _update_run(run_id, status="failed", error="Agent no longer exists")
        await broker.publish(run_event("error", message="Agent no longer exists"))
        broker.finish()
        return

    _update_run(run_id, status="running")
    memory = PersistentMemory(agent_id=memory_scope_id(run_row["workspace_id"], agent_row["id"]))
    runtime = PlatformAgentRuntime(agent_row, workspace_settings=_get_workspace_settings(run_row["workspace_id"]), memory=memory)

    try:
        result = await runtime.run(run_row["task"], run_id, broker)
        stats = result.get("stats") or {}
        failed_error = result.get("error")
        if failed_error:
            _update_run(run_id, status="failed", result=result.get("result", ""), stats=json.dumps(stats), error=failed_error)
            await broker.publish(run_event("run.end", status="failed", run_id=run_id, error=failed_error))
        else:
            _update_run(run_id, status="completed", result=result.get("result", ""), stats=json.dumps(stats), error=None)
            await broker.publish(run_event("run.end", status="completed", run_id=run_id, result=result.get("result", ""), stats=stats))
    except Exception as e:  # noqa: BLE001 — FAILED state recovery via retry
        logger.error("Run failed", run_id=run_id, error=str(e))
        _update_run(run_id, status="failed", error=str(e))
        await broker.publish(run_event("run.end", status="failed", run_id=run_id, error=str(e)))
    finally:
        broker.finish()


def start_run_execution(run_id: str) -> None:
    """Kick off a run on the current event loop (call from async context)."""
    asyncio.get_running_loop().create_task(execute_run(run_id))


def retry_run(run_id: str) -> bool:
    """Reset a failed run for re-execution (Phase 2.6 — FAILED recovery)."""
    from agentfactory.app import db

    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None or row["status"] != "failed":
            return False
        conn.execute("UPDATE agent_runs SET status = 'pending', retries = retries + 1, error = NULL, updated_at = ? WHERE id = ?",
                     (_now_iso(), run_id))
        conn.commit()
        return True
    finally:
        conn.close()
