"""
Base Agent — Core agent framework primitives.

Provides:
- RunnableAgent: Base class with tool execution, memory, and LLM failover
- AgentFactory: Registry of agent types that can be cloned for any repo
- Tool execution loop with error handling, retries, and context pruning
"""

from typing import List, Dict, Any, Optional, Callable, AsyncGenerator
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from dataclasses import dataclass, field as dc_field
import structlog
import asyncio
import json

from agentfactory.config import settings
from agentfactory.llm_manager import FailoverLLMManager, LLMConfig
from agentfactory.base_tools import ToolRegistry, ToolWrapper as Tool, ToolCall, tool
from agentfactory.verifier import Verifier, VerificationResult, VerificationReport, AuditResult
from agentfactory.mcp_integration import MCPServerConfig, register_mcp_tools, cleanup_mcp_clients
from agentfactory.memory import PersistentMemory
from agentfactory.skill import SkillRegistry, Skill

logger = structlog.get_logger()


class AgentConfig(BaseModel):
    """
    Legacy-compatible agent configuration loaded from YAML.

    Used by agents/config_loader.py to load agent profiles.
    """
    name: str = Field(..., description="Agent name")
    rank: str = Field(default="Junior", description="Agent rank")
    role_description: str = Field(default="", description="Agent role/responsibilities")
    tools: List[str] = Field(default_factory=list, description="Tool names to enable")
    model_preference: List[str] = Field(default_factory=lambda: ["gemini-2.5-flash", "gpt-4o"])
    system_instructions: str = Field(default="", description="System prompt instructions")
    constitutional_boundaries: Dict[str, Any] = Field(default_factory=dict)
    allow_delegation: bool = Field(default=False)
    temperature: float = Field(default=0.2)
    max_budget_usd_per_day: float = Field(default=5.0)

    model_config = {"arbitrary_types_allowed": True}


class AgentPersona(BaseModel):
    """Defines the personality, role, and constraints for an agent."""
    rank: str = Field(..., description="Agent rank: Manager, Senior, Junior, QA")
    responsibilities: List[str] = Field(default_factory=list)
    system_instructions: str = Field(default_factory=str)
    model_preferences: List[str] = Field(default_factory=list, description="Ordered model names (free→paid)")
    max_budget_usd_per_day: float = Field(default=5.0)
    allow_delegation: bool = Field(default=False)
    max_iterations: int = Field(default=20)
    max_context_length: int = Field(default=200000)

    model_config = {"arbitrary_types_allowed": True}


@dataclass
class AgentExecutionStats:
    """Tracks execution statistics for an agent run."""
    start_time: datetime = dc_field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls_made: int = 0
    iterations: int = 0
    errors: List[str] = dc_field(default_factory=list)
    successes: List[str] = dc_field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def to_dict(self) -> dict:
        return {
            "duration_seconds": self.duration_seconds,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "tool_calls_made": self.tool_calls_made,
            "iterations": self.iterations,
            "errors": len(self.errors),
            "successes": len(self.successes),
        }


class RunnableAgent:
    """
    Base class for all agents — handles tool execution, LLM failover,
    memory management, and context pruning for self-correction.

    This class is clonable: any agent created from this template
    can be cloned for different repositories with shared tool registry.
    """

    def __init__(
        self,
        persona: AgentPersona,
        tool_registry: ToolRegistry,
        llm_manager: Optional[FailoverLLMManager] = None,
        mcp_configs: Optional[Dict[str, MCPServerConfig]] = None,
        agent_id: str = "default",
        memory: Optional[PersistentMemory] = None,
    ):
        self.persona = persona
        self.tools = tool_registry
        self.llm_manager = llm_manager or FailoverLLMManager()
        self.mcp_configs = mcp_configs or {}
        self.stats = AgentExecutionStats()
        self.verifier = Verifier()

        # Persistent memory — enables conversation history across restarts
        self.agent_id = agent_id
        self.memory = memory or PersistentMemory(agent_id=agent_id)

        # Memory: rolling conversation history with context window limit
        self._history: List[Dict[str, Any]] = []
        self._max_history_tokens: int = persona.max_context_length - 20000  # Reserve for tools

        # MCP clients are connected lazily on first run (see _ensure_mcp_tools)
        self._mcp_clients: Dict[str, Any] = {}

        # Load persistent history on init
        self._load_persistent_history()

        # Only messages after this index are new and need persisting.
        # Messages loaded from the DB are already stored, so we never re-save them.
        self._last_saved_count = len(self._history)

    def _load_persistent_history(self) -> None:
        """Load conversation history from persistent memory."""
        if self.memory:
            try:
                saved = self.memory.load_history(limit=50)
                if saved:
                    self._history = saved
                    logger.debug(f"Loaded {len(saved)} messages from persistent memory")
            except Exception as e:
                logger.warning(f"Could not load persistent history: {e}")

    def _save_persistent_history(self) -> None:
        """
        Save only the *new* conversation messages to persistent memory.

        Re-saving the entire history on every turn caused quadratic growth in
        the SQLite database (regression fixed in Phase 0). We track how many
        messages have already been persisted and only write the delta.
        """
        if self.memory and self._history:
            try:
                new_messages = self._history[self._last_saved_count:]
                if new_messages:
                    self.memory.save_history(new_messages)
                    self._last_saved_count = len(self._history)
            except Exception as e:
                logger.debug(f"Could not save persistent history: {e}")

    @classmethod
    def clone(cls, agent: "RunnableAgent", tool_registry: ToolRegistry) -> "RunnableAgent":
        """
        Clone an agent for a new repository with the same configuration
        but a shared tool registry.
        """
        return cls(
            persona=agent.persona,
            tool_registry=tool_registry,
            llm_manager=agent.llm_manager,
            mcp_configs=agent.mcp_configs,
        )

    async def _ensure_mcp_tools(self):
        """Lazily connect to MCP servers and register their tools."""
        if self.mcp_configs and not self._mcp_clients:
            logger.debug(f"Connecting to MCP servers for {self.persona.rank} agent")
            self._mcp_clients = await register_mcp_tools(self.tools, self.mcp_configs)

    async def think(
        self,
        task: str,
        context: Optional[List[Dict[str, Any]]] = None,
        require_tool: bool = False,
    ) -> str:
        """
        Generate a thought/reply using LLM failover.

        Args:
            task: The prompt or task to process
            context: Optional additional context (will be appended to history)
            require_tool: If True, force the model to use a tool

        Returns:
            The generated text response
        """
        # Add context to history if provided
        if context:
            self._history.extend(context)

        messages = self._build_messages(task)
        result = await self.llm_manager.generate_with_failover(messages)

        # Save to persistent memory
        self._history.append({"role": "user", "content": task})
        self._history.append({"role": "assistant", "content": result})
        self._save_persistent_history()

        return result

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """
        Execute a single tool call with error handling and retries.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool

        Returns:
            Tool execution result as string
        """
        self.stats.tool_calls_made += 1

        tool_obj = self.tools.get(tool_name)
        if not tool_obj:
            return f"Error: Tool '{tool_name}' not found in registry"

        try:
            # Log the tool call
            logger.debug(f"Executing tool: {tool_name}", args=tool_args)

            result = await tool_obj.execute(tool_args)

            # Track stats
            cost = tool_obj.metadata.cost_per_call_usd
            self.stats.total_cost_usd += cost

            if "Error" not in result:
                self.stats.successes.append(f"{tool_name}: {result[:100]}")
            else:
                self.stats.errors.append(f"{tool_name}: {result}")

            return result

        except Exception as e:
            error_msg = f"Tool '{tool_name}' failed: {str(e)}"
            self.stats.errors.append(error_msg)
            logger.error(error_msg)
            return error_msg

    async def execute_tool_calls(self, tool_calls: List[ToolCall]) -> List[str]:
        """
        Execute multiple tool calls (parallel-safe).

        Args:
            tool_calls: List of ToolCall objects to execute

        Returns:
            List of results (parallel to tool_calls)
        """
        tasks = []
        for tc in tool_calls:
            tasks.append(self.execute_tool(tc.name, tc.arguments))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error strings
        formatted = []
        for r in results:
            if isinstance(r, Exception):
                formatted.append(f"Error: {str(r)}")
                self.stats.errors.append(str(r))
            else:
                formatted.append(str(r))

        return formatted

    async def run(
        self,
        task_description: str,
        initial_input: Optional[str] = None,
        max_iterations: Optional[int] = None,
        tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the agent's main loop: think → plan → act → verify → self-correct.

        This is the primary method for running an agent task.

        Args:
            task_description: Natural language task description
            initial_input: Optional initial context/input
            max_iterations: Override default max iterations
            tools: Optional list of tool names to restrict usage to

        Returns:
            Dict with results, stats, and any errors
        """
        await self._ensure_mcp_tools()

        iterations = max_iterations or self.persona.max_iterations
        self.stats.start_time = datetime.now(timezone.utc)

        logger.info(
            f"Agent {self.persona.rank} starting task",
            task=task_description,
            max_iterations=iterations,
        )

        # Build initial prompt
        prompt = self._build_system_prompt()
        if initial_input:
            prompt += f"\n\nInitial Input:\n{initial_input}\n"
        prompt += f"\nTask: {task_description}"

        result = await self._agent_loop(prompt, iterations, tools)

        self.stats.end_time = datetime.now(timezone.utc)
        logger.info(
            f"Agent {self.persona.rank} completed task",
            stats=self.stats.to_dict(),
        )

        return result

    async def _agent_loop(self, prompt: str, max_iterations: int, tools: Optional[List[str]]) -> Dict[str, Any]:
        """Main agent execution loop with self-correction."""
        final_result = ""
        verification_errors = []

        for i in range(max_iterations):
            self.stats.iterations = i + 1

            # Think
            thoughts = await self.think(prompt, require_tool=True)

            # Parse and execute tool calls
            tool_calls = self._parse_tool_calls(thoughts)

            if tool_calls:
                results = await self.execute_tool_calls(tool_calls)
                final_result = "\n".join(results)

                # Run verification
                verification = await self.verifier.verify_all(final_result)
                if verification.failed_checks:
                    verification_errors.append(verification)

                    # Self-correction with pruned context
                    correction_context = self.verifier.get_pruned_context()
                    if correction_context:
                        prompt = f"""
Self-correction needed. The previous result had verification failures.

{correction_context}

Previous result:
{final_result[-2000:] if len(final_result) > 2000 else final_result}

Please fix the issues above and retry.
"""
                        continue
            else:
                final_result = thoughts

            # If no verification errors, we're done
            if not verification_errors:
                break

        return {
            "result": final_result,
            "stats": self.stats.to_dict(),
            "verification_errors": [str(e) for e in verification_errors],
        }

    def _build_system_prompt(self) -> str:
        """Build the system prompt from persona configuration."""
        prompt = self.persona.system_instructions or (
            f"You are an {self.persona.rank} level AI agent.\n"
            f"Responsibilities: {', '.join(self.persona.responsibilities)}\n"
            f"Maximum budget per day: ${self.persona.max_budget_usd_per_day}\n"
            f"You can delegate tasks to lower-ranked agents: {self.persona.allow_delegation}\n"
        )

        if self.tools:
            tool_descs = []
            for name, t in self.tools._tools.items():
                desc = t.metadata.description or name
                args_str = ", ".join(f"{k}" for k in (t.signature or {}).get("properties", {}).keys())
                tool_descs.append(f"- {name}({args_str}): {desc}")
            prompt += f"\n\nAvailable tools:\n" + "\n".join(tool_descs)

        prompt += f"\n\nCurrent date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        prompt += "\n\nAlways think step by step. Use tools when needed."

        return prompt

    def _build_messages(self, task: str) -> List[Dict[str, Any]]:
        """Build message list for LLM API."""
        messages = []

        # System message
        messages.append({
            "role": "system",
            "content": self._build_system_prompt(),
        })

        # History
        messages.extend(self._history[-50:])  # Keep last 50 messages

        # Current task
        messages.append({
            "role": "user",
            "content": task,
        })

        return messages

    def _parse_tool_calls(self, text: str) -> List[ToolCall]:
        """Parse tool call requests from LLM response."""
        # Try JSON format first
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [ToolCall(**tc) for tc in data if isinstance(tc, dict) and "name" in tc and "arguments" in tc]
            if isinstance(data, dict) and "tool_call" in data:
                tc = data["tool_call"]
                return [ToolCall(name=tc["name"], arguments=tc.get("arguments", {}), id=tc.get("id", ""))]
        except json.JSONDecodeError:
            pass

        # Try XML-style format
        if "<use_tool>" in text:
            import re
            pattern = r'<use_tool\s+name="([^"]+)"\s*(?:\s+id="([^"]*)")?>(.*?)</use_tool>'
            matches = re.findall(pattern, text, re.DOTALL)
            return [ToolCall(name=name, arguments={"input": args.strip()}, id=tool_id or "")
                    for name, tool_id, args in matches]

        return []

    async def close(self):
        """Clean up resources."""
        await cleanup_mcp_clients(self._mcp_clients)

    async def learn_from_correction(
        self,
        original_prompt: str,
        original_output: str,
        correction: str,
        max_correction_iterations: int = 2,
    ) -> str:
        """
        Learn from a correction by re-running the prompt with correction context.

        This is the feedback learning loop: given what the agent originally
        produced and a human correction, the agent re-attempts the task
        with the correction baked into context, then saves the corrected
        conversation to persistent memory.

        Args:
            original_prompt: The original task/prompt that was given
            original_output: The agent's original (incorrect) output
            correction: The human-provided correction/note
            max_correction_iterations: Maximum self-correction attempts

        Returns:
            The corrected output
        """
        logger.info(
            f"Learning from correction for {self.persona.rank} agent",
            correction_length=len(correction),
        )

        # Build a learning prompt that includes the original attempt and correction
        learning_prompt = self._build_system_prompt()
        learning_prompt += f"""

ORIGINAL TASK:
{original_prompt}

YOUR ORIGINAL OUTPUT:
{original_output}

HUMAN CORRECTION:
{correction}

INSTRUCTIONS: Redo the task, taking the correction into account. Do not repeat the
same mistakes. You can use tools if needed."""

        # Store the learning context in history for future reference
        self._history.append({
            "role": "user",
            "content": f"[CORRECTION LEARNING] Original task: {original_prompt[:200]}... Correction: {correction[:200]}...",
        })

        # Re-run with correction context
        corrected_output = ""
        for iteration in range(max_correction_iterations):
            result = await self.think(learning_prompt, require_tool=False)
            corrected_output = result
            self._history.append({"role": "assistant", "content": result})

            # If the result looks corrected (non-empty and different), we're done
            if result.strip() and result != original_output:
                break

            # Try self-correction with more detail
            learning_prompt += f"\n\nPrevious attempt was insufficient. Please improve:\n{result}"

        # Save the correction learning to persistent memory as a fact
        if self.memory:
            try:
                self.memory.save_fact(
                    "correction_learning",
                    f"Prompt: {original_prompt[:500]} | Correction: {correction[:500]}",
                )
            except Exception as e:
                logger.debug(f"Could not save correction learning to memory: {e}")

        self._save_persistent_history()

        logger.info(
            f"Correction learning complete for {self.persona.rank} agent",
            corrected_length=len(corrected_output),
        )

        return corrected_output


# ============================================================
# AgentFactory: Registry of agent types
# ============================================================

class AgentFactory:
    """
    Factory for creating and cloning agents.

    Manages:
    - Default agent personas (Manager, Senior, Junior, QA)
    - Tool registry sharing across repositories
    - MCP server discovery and registration
    - Easy cloning for new repos
    """

    DEFAULT_RANKS = ["Manager", "Senior", "Junior", "QA"]

    DEFAULT_PERSONAS = {
        "Manager": AgentPersona(
            rank="Manager",
            responsibilities=["Overall project coordination", "Approval gate for proposals", "Resource allocation"],
            model_preferences=["gpt-4o", "claude-3-5-sonnet-20241022"],
            allow_delegation=True,
            max_iterations=50,
            max_budget_usd_per_day=20.0,
        ),
        "Senior": AgentPersona(
            rank="Senior",
            responsibilities=["Code implementation", "Architecture decisions", "Code review for juniors"],
            model_preferences=["gemini-2.5-flash", "gpt-4o", "claude-3-5-sonnet-20241022"],
            allow_delegation=True,
            max_iterations=30,
            max_budget_usd_per_day=10.0,
        ),
        "Junior": AgentPersona(
            rank="Junior",
            responsibilities=["Small bug fixes", "Code following patterns", "Test writing"],
            model_preferences=["gemini-2.5-flash", "gpt-4o-mini"],
            allow_delegation=True,
            max_iterations=25,
            max_budget_usd_per_day=5.0,
        ),
        "QA": AgentPersona(
            rank="QA",
            responsibilities=["Testing", "Bug finding", "Verification"],
            model_preferences=["gpt-4o-mini", "gemini-2.5-flash"],
            allow_delegation=False,
            max_iterations=20,
            max_budget_usd_per_day=3.0,
        ),
    }

    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self._registry = tool_registry or ToolRegistry()
        self._personas: Dict[str, AgentPersona] = self.DEFAULT_PERSONAS.copy()
        self._mcp_configs: Dict[str, MCPServerConfig] = {}
        self._llm_managers: Dict[str, FailoverLLMManager] = {}
        self.skill_registry = SkillRegistry()

    @staticmethod
    def _build_system_prompt(config: "AgentConfig") -> str:
        """Build a system prompt from an AgentConfig (legacy support)."""
        prompt = config.system_instructions or f"You are an AI agent named {config.name}."

        prompt += f"\nRank: {config.rank}"
        if config.role_description:
            prompt += f"\nRole: {config.role_description}"
        if config.tools:
            prompt += f"\nTools available: {', '.join(config.tools)}"
        if config.allow_delegation:
            prompt += "\nYou are authorized to delegate tasks to lower-ranked agents."
        if config.constitutional_boundaries:
            prompt += "\nConstitutional Boundaries:"
            for k, v in config.constitutional_boundaries.items():
                prompt += f"\n  - {k}: {v}"

        return prompt

    def register_tools(self, tools: List[Callable]) -> None:
        """Register a list of tool functions."""
        for t in tools:
            self._registry.register_function(t)

    def register_skill(self, skill: Skill) -> None:
        """Register a skill into the skill registry."""
        self.skill_registry.register_skill(skill)

    def load_skill_package(self, package_name: str) -> Optional[Skill]:
        """Load a skill from an installed Python package."""
        return self.skill_registry.load_from_package(package_name)

    def load_skills_from_directory(self, directory: str) -> List[Skill]:
        """Load all skills from a directory of Python files."""
        return self.skill_registry.load_from_directory(directory)

    def install_skill(self, skill_name: str) -> None:
        """Install a registered skill's tools into the tool registry."""
        skill = self.skill_registry.get_skill(skill_name)
        if skill is None:
            raise ValueError(f"Unknown skill: {skill_name}")
        skill.register_into(self._registry)

    def load_mcp_config(self, config_path: str = "mcp.json") -> None:
        """Load MCP server configurations."""
        from agentfactory.mcp_integration import load_mcp_config
        self._mcp_configs = load_mcp_config(config_path)
        logger.info(f"Loaded {len(self._mcp_configs)} MCP server configurations")

    def register_persona(self, rank: str, persona: AgentPersona) -> None:
        """Register a custom agent persona."""
        self._personas[rank] = persona

    def create_agent(
        self,
        rank: str,
        repo_name: str = "default",
    ) -> RunnableAgent:
        """
        Create a new agent instance.

        Args:
            rank: Agent rank (Manager, Senior, Junior, QA)
            repo_name: Name for the repository context

        Returns:
            A new RunnableAgent instance
        """
        persona = self._personas.get(rank)
        if not persona:
            raise ValueError(f"Unknown rank: {rank}. Available: {list(self._personas.keys())}")

        llm_manager = self._llm_managers.get(repo_name) or FailoverLLMManager(
            model_preferences=persona.model_preferences,
            daily_budget_usd=persona.max_budget_usd_per_day,
        )

        if repo_name not in self._llm_managers:
            self._llm_managers[repo_name] = llm_manager

        return RunnableAgent(
            persona=persona,
            tool_registry=self._registry,
            llm_manager=llm_manager,
            mcp_configs=self._mcp_configs,
        )

    def clone_for_repository(self, repo_path: str) -> "AgentFactory":
        """
        Create a new AgentFactory instance for a separate repository.

        Shares the same personas and MCP configs but creates
        a fresh LLM manager with budget tracking per-repo.
        """
        new_factory = AgentFactory(tool_registry=self._registry)
        new_factory._personas = self._personas.copy()
        new_factory._mcp_configs = self._mcp_configs.copy()

        logger.info(f"Cloned AgentFactory for repository: {repo_path}")
        return new_factory

    def get_shared_registry(self) -> ToolRegistry:
        """Get the shared tool registry for all cloned agents."""
        return self._registry

    def get_agent_rank(self, rank: str) -> RunnableAgent:
        """Get a singleton agent for a given rank (no repo context)."""
        return self.create_agent(rank)

    @property
    def available_ranks(self) -> List[str]:
        """List all registered agent ranks."""
        return list(self._personas.keys())

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._registry._tools)
