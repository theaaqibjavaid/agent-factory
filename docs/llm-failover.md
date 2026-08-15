# LLM Failover & Budgeting

AgentFactory uses a failover pipeline to minimize costs while maximizing reliability. The `FailoverLLMManager` tries providers in order: free → paid.

## Pipeline Order

```
1. Google Gemini 2.5 Flash (free tier) ← default
   if rate-limited or fails:
2. OpenAI GPT-4o / GPT-4o-mini (paid)
   if rate-limited or fails:
3. Anthropic Claude (premium)
```

## Budget Control

Each day, the LLM manager tracks total spend. When `AGENT_DAILY_BUDGET_USD` is reached:

1. All paid providers (OpenAI, Anthropic) are disabled
2. Only free-tier providers (Gemini) remain active
3. Once Gemini budget is exhausted, the manager raises an error

Default daily budget: **$5.00**

## Configuration

```python
from agentfactory.llm_manager import FailoverLLMManager, LLMConfig

# Default pipeline (Gemini → OpenAI → Anthropic)
manager = FailoverLLMManager(
    daily_budget_usd=10.0,  # $10/day budget
    model_preferences={"Senior": ["gemini-2.5-flash", "gpt-4o"]},
)

# Custom pipeline
custom_pipeline = [
    LLMConfig(provider="google", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY"),
    LLMConfig(provider="openai", model="gpt-4o-mini", api_key_env="OPENAI_API_KEY"),
]
manager = FailoverLLMManager(pipeline=custom_pipeline, daily_budget_usd=2.0)
```

## Methods

| Method | Description |
|--------|-------------|
| `generate_text(prompt, ...)` | Generate text with automatic failover |
| `generate_with_failover(prompt, ...)` | Explicit failover generation |
| `handle_rate_limit_failover()` | Advance to next provider on rate limit |
| `reset()` | Reset day counter and spend tracking |

## Langfuse Tracing

When `LANGFUSE_SECRET_KEY` is set, all LLM calls are traced:

- Each provider call is logged as a span
- Spend tracking includes token usage
- Traces available in Langfuse dashboard

## Per-Rank Model Preferences

Agent configs can specify different model pipelines per rank:

```yaml
agents:
  - name: "Senior"
    rank: "Senior"
    model_preference: ["gemini-2.5-flash", "gpt-4o"]
  - name: "Junior"
    rank: "Junior"
    model_preference: ["gemini-2.5-flash", "gpt-4o-mini"]
  - name: "QA"
    rank: "QA"
    model_preference: ["gpt-4o-mini"]
```
