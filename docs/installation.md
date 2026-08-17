# Installation

AgentFactory is distributed as a PyPI package. Install it with pip.

## Requirements

- Python >= 3.10
- pip >= 23.0

## Install

```bash
# Core package (LLM integrations are optional extras)
pip install agentfactory-studio

# With all LLM providers
pip install "agentfactory-studio[all]"

# Selective extras
pip install agentfactory-studio[gemini]      # Google Gemini
pip install agentfactory-studio[openai]      # OpenAI
pip install agentfactory-studio[anthropic]   # Anthropic
pip install agentfactory-studio[langfuse]    # Observability
pip install agentfactory-studio[search]      # Web search tools

# Development dependencies
pip install "agentfactory-studio[dev]"
```

## API Keys

Create a `.env` file from the template:

```bash
agentfactory init
```

This generates `.env`, `mcp.json`, and example agent configs. Edit `.env` with your keys:

```
GEMINI_API_KEY=your-gemini-api-key-here   # Free tier - recommended default
OPENAI_API_KEY=your-openai-api-key-here    # Paid fallback
ANTHROPIC_API_KEY=your-anthropic-api-key-here  # Premium fallback
TAVILY_API_KEY=your-tavily-key-here        # Optional: web search
LANGFUSE_SECRET_KEY=your-langfuse-secret  # Optional: observability
```

Get API keys:
- **Gemini**: https://aistudio.google.com/apikey
- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/keys
- **Tavily**: https://tavily.com (free tier available)
- **Langfuse**: https://cloud.langfuse.com (free tier available)

## Verify

```bash
# List all registered tools
agentfactory list-tools

# Check CLI
agentfactory --version
```

## From Source (development)

```bash
git clone https://github.com/theaaqibjavaid/agent-factory.git
cd agent-factory
pip install -e ".[dev]"
```
