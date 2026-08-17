"""
LLM Manager — Failover router with token tracing, budget control.

Prioritises Google Gemini 2.5 Flash (free tier) as the default engine,
with automatic failover to OpenAI or Anthropic on rate limits/credit issues.
Includes native Langfuse/OpenTelemetry tracing hooks.

Usage:
    manager = FailoverLLMManager()
    llm = manager.get_active_llm()
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

from agentfactory.config import settings

logger = structlog.get_logger()

# Optional Langfuse integration
_langfuse_client = None
if settings.has_langfuse:
    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse tracing enabled")
    except ImportError:
        logger.warning("langfuse package not installed. Install with: pip install langfuse")


@dataclass
class LLMConfig:
    """Configuration for a single LLM provider/model."""
    provider: str        # "google", "openai", "anthropic", "openai_compatible"
    model: str           # e.g., "gemini-2.5-flash"
    api_key_env: str     # Environment variable name
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    is_free_tier: bool = False
    base_url: Optional[str] = None  # OpenAI-compatible endpoints (Phase 4.4)


@dataclass
class TokenUsage:
    """Tracks token usage for cost calculation and tracing."""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def cost_usd(self) -> float:
        """Estimate cost based on model pricing (approximate)."""
        # Pricing per 1M tokens (as of 2024-11)
        pricing = {
            "gemini-2.5-flash": {"input": 0.0, "output": 0.0},      # Free tier
            "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
            "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4o": {"input": 2.5, "output": 10.0},
            "gpt-4": {"input": 3.0, "output": 60.0},
            "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
            "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        }
        model_key = self.model
        if model_key not in pricing:
            return 0.0

        prices = pricing[model_key]
        input_cost = (self.input_tokens / 1_000_000) * prices["input"]
        output_cost = (self.output_tokens / 1_000_000) * prices["output"]
        return input_cost + output_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "estimated_cost_usd": round(self.cost_usd(), 6),
            "timestamp": self.timestamp,
        }


class FailoverLLMManager:
    """
    Manages dynamic model switching across providers with failover.

    Tier priority: Gemini (free) → OpenAI → Anthropic (paid)
    Shuts down when budget threshold is exceeded or all models exhausted.
    """

    DEFAULT_PIPELINE: List[LLMConfig] = [
        LLMConfig(
            provider="google",
            model="gemini-2.5-flash",
            api_key_env="GEMINI_API_KEY",
            temperature=0.2,
            is_free_tier=True,
        ),
        LLMConfig(
            provider="openai",
            model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
            temperature=0.2,
        ),
        LLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            api_key_env="ANTHROPIC_API_KEY",
            temperature=0.2,
        ),
    ]

    def __init__(
        self,
        pipeline: Optional[List[LLMConfig]] = None,
        daily_budget_usd: Optional[float] = None,
        model_preferences: Optional[List[str]] = None,
    ):
        if pipeline is not None:
            self.pipeline = pipeline
        elif model_preferences:
            self.pipeline = self._build_pipeline_from_preferences(model_preferences)
        else:
            self.pipeline = self.DEFAULT_PIPELINE.copy()

        self.current_index = 0
        self.daily_budget_usd = daily_budget_usd or settings.daily_budget_usd
        self.current_spend_usd = 0.0
        self.token_history: List[TokenUsage] = []

    def _build_pipeline_from_preferences(self, model_preferences: List[str]) -> List[LLMConfig]:
        """Build a pipeline from a list of model name preferences."""
        pipeline = []
        provider_map = {
            "gemini": ("google", "GEMINI_API_KEY", True),
            "gpt": ("openai", "OPENAI_API_KEY", False),
            "claude": ("anthropic", "ANTHROPIC_API_KEY", False),
        }

        for model_name in model_preferences:
            provider_key = None
            for key in provider_map:
                if key in model_name.lower():
                    provider_key = key
                    break

            if provider_key:
                provider, env_var, is_free = provider_map[provider_key]
                pipeline.append(LLMConfig(
                    provider=provider,
                    model=model_name,
                    api_key_env=env_var,
                    is_free_tier=is_free,
                ))

        return pipeline if pipeline else self.DEFAULT_PIPELINE.copy()

    def generate_text(self, messages: List[Dict[str, str]], max_tokens: int = 1000) -> str:
        """
        Generate text using the active LLM with failover.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        try:
            llm = self.get_active_llm()
            # Use LangChain invoke for text generation
            response = llm.invoke(messages)
            if hasattr(response, 'content'):
                return str(response.content)
            return str(response)
        except PermissionError:
            return "Error: Daily budget exceeded. Set AGENT_DAILY_BUDGET_USD to increase."
        except RuntimeError:
            return "Error: No LLM models available. Check your API keys."
        except Exception as e:
            return f"Error generating text: {str(e)}"

    async def generate_with_failover(self, messages: List[Dict[str, Any]]) -> str:
        """
        Generate text with async failover support.

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            Generated text response
        """
        try:
            llm = self.get_active_llm()
            # Check if the LLM supports async invoke
            if hasattr(llm, 'ainvoke'):
                response = await llm.ainvoke(messages)
            else:
                # Fallback to sync
                response = llm.invoke(messages)

            if hasattr(response, 'content'):
                return str(response.content)
            return str(response)
        except PermissionError:
            return "Error: Daily budget exceeded."
        except RuntimeError:
            return "Error: No LLM models available."
        except Exception as e:
            # Try failover for rate limit errors
            should_failover = self.handle_rate_limit_failover(e)
            if should_failover:
                try:
                    llm = self.get_active_llm()
                    if hasattr(llm, 'ainvoke'):
                        response = await llm.ainvoke(messages)
                    else:
                        response = llm.invoke(messages)
                    if hasattr(response, 'content'):
                        return str(response.content)
                    return str(response)
                except Exception:
                    return f"Error after failover: {str(e)}"
            return f"Error generating text: {str(e)}"

    def get_active_llm(self) -> Any:
        """
        Returns the current active LLM instance.

        Raises PermissionError if budget exceeded.
        Raises RuntimeError if all models exhausted.

        With Langfuse enabled, LLM calls are automatically traced.
        """
        while self.current_index < len(self.pipeline):
            target = self.pipeline[self.current_index]
            api_key = os.getenv(target.api_key_env)

            if not api_key:
                logger.warning(
                    f"Skipping {target.model}: API key not found in env var {target.api_key_env}"
                )
                self.current_index += 1
                continue

            if self.current_spend_usd >= self.daily_budget_usd:
                logger.critical(
                    "Budget limit exceeded. Agent shutting down to prevent unexpected charges."
                )
                raise PermissionError("Global spending budget exceeded.")

            logger.info(
                f"Using model: {target.provider} | {target.model} | free_tier={target.is_free_tier}"
            )

            return self._create_llm(target)

        logger.critical("All models exhausted or missing API keys. Shutting down.")
        raise RuntimeError("No available LLM models left in the pool.")

    def _create_llm(self, config: LLMConfig) -> Any:
        """Create an LLM instance from config, with Langfuse tracing if enabled."""
        if config.provider == "openai":
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=config.model,
                temperature=config.temperature,
                api_key=os.getenv(config.api_key_env),
                max_tokens=config.max_tokens,
            )

            if _langfuse_client:
                # Langfuse automatic tracing is enabled via env vars
                # LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY trigger auto-tracing
                pass

            return llm

        elif config.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=config.model,
                temperature=config.temperature,
                google_api_key=os.getenv(config.api_key_env),
                max_tokens=config.max_tokens,
            )

        elif config.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=config.model,
                temperature=config.temperature,
                api_key=os.getenv(config.api_key_env),
                max_tokens=config.max_tokens,
            )

        elif config.provider in ("openai_compatible", "ollama"):
            # Any OpenAI-compatible endpoint: Ollama, vLLM, LM Studio, OpenRouter, ...
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=config.model,
                temperature=config.temperature,
                api_key=os.getenv(config.api_key_env) or "local",
                base_url=config.base_url,
                max_tokens=config.max_tokens,
            )

        raise ValueError(f"Unknown provider: {config.provider}")

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generate text with native tool calling support.

        Uses the LLM's native function_call / tool_use capability
        instead of parsing tool calls from text output.

        Args:
            messages: Conversation messages
            tools: List of tool schemas in OpenAI format:
                   {"name": "tool_name", "description": "...", "parameters": {...}}

        Returns:
            Dict with:
              - "text": generated text (may be empty if tool was called)
              - "tool_calls": list of {"name", "arguments"} dicts (may be empty)
        """
        try:
            llm = self.get_active_llm()

            # Convert tools to appropriate format for each provider
            if hasattr(llm, "bind_tools"):
                # LangChain 0.3+ has bind_tools
                llm_with_tools = llm.bind_tools(tools)
                response = llm_with_tools.invoke(messages)
            else:
                # Fallback: use raw provider API
                response = self._raw_tool_call(llm, messages, tools)

            # Parse response — may contain both text and tool calls
            tool_calls = []
            text_parts = []

            if hasattr(response, "tool_calls") and response.tool_calls:
                for tc in response.tool_calls:
                    tool_calls.append({
                        "name": tc.get("name", ""),
                        "arguments": tc.get("args", tc.get("arguments", {})),
                        "id": tc.get("id", ""),
                    })

            if hasattr(response, "content"):
                if isinstance(response.content, str):
                    text_parts.append(response.content)
                elif isinstance(response.content, list):
                    for part in response.content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif part.get("type") == "tool_use":
                                tool_calls.append({
                                    "name": part.get("name", ""),
                                    "arguments": part.get("input", {}),
                                    "id": part.get("id", ""),
                                })

            # Track token usage
            if hasattr(response, "usage") and response.usage:
                usage = TokenUsage(
                    input_tokens=getattr(response.usage, "prompt_tokens", 0),
                    output_tokens=getattr(response.usage, "completion_tokens", 0),
                    model=self.get_current_model_name(),
                )
                self.add_cost(usage.cost_usd(), usage.model, usage)

            return {
                "text": "\n".join(text_parts),
                "tool_calls": tool_calls,
            }

        except PermissionError:
            return {"text": "Error: Daily budget exceeded.", "tool_calls": []}
        except RuntimeError:
            return {"text": "Error: No LLM models available.", "tool_calls": []}
        except Exception as e:
            should_failover = self.handle_rate_limit_failover(e)
            if should_failover:
                try:
                    return self.generate_with_tools(messages, tools)
                except Exception:
                    return {"text": f"Error after failover: {str(e)}", "tool_calls": []}
            return {"text": f"Error generating text: {str(e)}", "tool_calls": []}

    def _raw_tool_call(self, llm, messages, tools):
        """Fallback for providers without bind_tools support."""
        # Convert messages to provider format and add tools
        if "openai" in type(llm).__name__.lower():
            return llm.client.chat.completions.create(
                model=llm.model_name,
                messages=messages,
                tools=[{"type": "function", "function": t} for t in tools],
                temperature=getattr(llm, "temperature", 0.2),
            )
        elif "anthropic" in type(llm).__name__.lower():
            return llm.client.messages.create(
                model=llm.model,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                tools=[{"type": "ext_tool", "name": t["name"], "input_schema": t.get("parameters", {})} for t in tools],
                max_tokens=getattr(llm, "max_tokens", 4000),
            )
        # Fallback to regular invoke
        return llm.invoke(messages)

    async def generate_streaming(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 4000,
    ) -> AsyncGenerator[str, None]:
        """
        Generate text with streaming (async iterator over tokens/chunks).

        Args:
            messages: Conversation messages
            max_tokens: Maximum tokens to generate

        Yields:
            Each chunk of generated text as it becomes available
        """
        try:
            llm = self.get_active_llm()

            if hasattr(llm, "astream"):
                async for chunk in llm.astream(messages):
                    if hasattr(chunk, "content") and chunk.content:
                        yield str(chunk.content)
                    else:
                        yield str(chunk)
            elif hasattr(llm, "stream"):
                # Sync streaming fallback
                for chunk in llm.stream(messages):
                    if hasattr(chunk, "content") and chunk.content:
                        yield str(chunk.content)
                    else:
                        yield str(chunk)
            else:
                # No streaming support — fall back to single call
                response = await self.generate_with_failover(messages)
                yield response

        except PermissionError:
            yield "Error: Daily budget exceeded."
        except RuntimeError:
            yield "Error: No LLM models available."
        except Exception as e:
            should_failover = self.handle_rate_limit_failover(e)
            if should_failover:
                async for chunk in self.generate_streaming(messages, max_tokens):
                    yield chunk
            else:
                yield f"Error generating text: {str(e)}"

    async def generate_streaming_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate text with streaming and tool calling.

        Yields dicts with either:
          - {"type": "chunk", "content": "text chunk"}
          - {"type": "tool_call", "name": "tool_name", "arguments": {...}}
        """
        try:
            llm = self.get_active_llm()

            if hasattr(llm, "bind_tools"):
                llm_with_tools = llm.bind_tools(tools)
                if hasattr(llm_with_tools, "astream"):
                    async for chunk in llm_with_tools.astream(messages):
                        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                            for tc in chunk.tool_call_chunks:
                                if tc.get("name") and tc.get("args"):
                                    yield {
                                        "type": "tool_call",
                                        "name": tc["name"],
                                        "arguments": json.loads(tc.get("args", "{}")) if tc.get("args") else {},
                                    }
                        if hasattr(chunk, "content") and chunk.content:
                            yield {"type": "chunk", "content": str(chunk.content)}
                else:
                    response = await self.generate_with_tools(messages, tools)
                    for tc in response["tool_calls"]:
                        yield {"type": "tool_call", "name": tc["name"], "arguments": tc["arguments"]}
                    if response["text"]:
                        yield {"type": "chunk", "content": response["text"]}
            else:
                # Fallback to non-streaming
                response = await self.generate_with_tools(messages, tools)
                for tc in response["tool_calls"]:
                    yield {"type": "tool_call", "name": tc["name"], "arguments": tc["arguments"]}
                if response["text"]:
                    yield {"type": "chunk", "content": response["text"]}

        except Exception as e:
            yield {"type": "error", "content": str(e)}

    def handle_rate_limit_failover(self, error: Optional[Exception] = None) -> bool:
        """
        Called when the current model throws rate/credit errors.

        Cycles to the next model. Returns True if failover happened, False if exhausted.
        """
        if error:
            error_str = str(error).lower()
            is_rate_limit = any(kw in error_str for kw in ["rate", "limit", "429", "quota", "credit", "balance", "insufficient"])
        else:
            is_rate_limit = True  # Assume failover is needed

        if not is_rate_limit:
            # S-10 log hygiene: provider errors can echo API keys — scrub before logging.
            from agentfactory.redact import redact_secrets
            logger.warning(f"Non-rate-limit error (not failing over): {redact_secrets(str(error))}")
            return False

        if self.current_index < len(self.pipeline) - 1:
            failed_model = self.pipeline[self.current_index]
            next_model = self.pipeline[self.current_index + 1]
            logger.warning(
                f"Model {failed_model.model} hit limits. "
                f"Failing over to {next_model.provider}/{next_model.model}"
            )
            self.current_index += 1
            return True
        else:
            logger.error("No more models to failover to. All exhausted.")
            return False

    def add_cost(self, usd_amount: float, model: str = "", usage: Optional[TokenUsage] = None) -> None:
        """Track cost and token usage. Used by tool implementations and LLM wrappers."""
        self.current_spend_usd += usd_amount

        if usage:
            self.token_history.append(usage)

            if _langfuse_client:
                # Trace token usage to Langfuse
                try:
                    _langfuse_client.generation(
                        model=usage.model,
                        usage={
                            "input": usage.input_tokens,
                            "output": usage.output_tokens,
                            "total": usage.total_tokens,
                        },
                        metadata={"cost_usd": usage.cost_usd()},
                    )
                except Exception as e:
                    logger.debug(f"Langfuse tracing failed: {e}")

        logger.debug(
            f"Cost tracked: ${usd_amount:.4f}, "
            f"total today: ${self.current_spend_usd:.4f}, "
            f"budget: ${self.daily_budget_usd:.2f}"
        )

    def get_current_model_name(self) -> str:
        """Returns the name of the current model."""
        if self.current_index < len(self.pipeline):
            return self.pipeline[self.current_index].model
        return "unknown"

    def get_usage_summary(self) -> Dict[str, Any]:
        """Return a summary of token usage and costs."""
        total_tokens = sum(u.total_tokens for u in self.token_history)
        total_cost = sum(u.cost_usd() for u in self.token_history)
        model_breakdown: Dict[str, Dict] = {}

        for u in self.token_history:
            if u.model not in model_breakdown:
                model_breakdown[u.model] = {"input": 0, "output": 0, "cost": 0.0}
            model_breakdown[u.model]["input"] += u.input_tokens
            model_breakdown[u.model]["output"] += u.output_tokens
            model_breakdown[u.model]["cost"] += u.cost_usd()

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "budget_usd": self.daily_budget_usd,
            "remaining_budget_usd": round(max(0, self.daily_budget_usd - total_cost), 4),
            "by_model": {k: {**v, "cost": round(v["cost"], 4)} for k, v in model_breakdown.items()},
            "current_model": self.get_current_model_name(),
        }

    def reset(self) -> None:
        """Reset the pipeline back to the first model."""
        self.current_index = 0
        self.current_spend_usd = 0.0
        logger.info("LLM manager reset to first model")

    def force_model(self, model_name: str) -> None:
        """Force the manager to use a specific model."""
        for i, config in enumerate(self.pipeline):
            if config.model == model_name or model_name in config.model:
                self.current_index = i
                logger.info(f"Forced model: {config.provider}/{config.model}")
                return
        logger.warning(f"Model '{model_name}' not found in pipeline")
