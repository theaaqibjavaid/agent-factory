#!/usr/bin/env python3
"""
Example: Using the AgentFactory to create a custom agent.

This script demonstrates how to:
1. Create a custom agent from YAML config
2. Create an agent programmatically
3. Register a new tool
4. Run a tiered engineering team on a feature request
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentfactory.base_agent import AgentConfig, AgentFactory, RunnableAgent
from agentfactory.base_tools import tool, list_tools, get_tool
from agentfactory.llm_manager import FailoverLLMManager, LLMConfig
from agentfactory.agents.config_loader import load_crew_config, get_config_path

# ============================================================
# Example 1: Load the engineering crew from YAML
# ============================================================

def example_load_crew():
    """Load the 3-tier engineering team from YAML."""
    yaml_path = get_config_path("engineer_crew.yaml")
    configs = load_crew_config(yaml_path)

    print("=== Loaded Agent Configurations ===")
    for name, config in configs.items():
        print(f"  {name} (rank={config.rank})")
        print(f"    Tools: {config.tools}")
        print(f"    Models: {config.model_preference}")
        print(f"    Delegation: {config.allow_delegation}")
        print()


# ============================================================
# Example 2: Create a custom agent programmatically
# ============================================================

def example_custom_agent():
    """Create a custom agent config (without instantiating LLM)."""
    config = AgentConfig(
        name="CodeReviewer",
        rank="Senior",
        role_description="Reviews code for security vulnerabilities and best practices",
        tools=["read_file_lines", "analyze_codebase_files"],
        model_preference=["gemini-2.5-flash", "gpt-4o"],
        system_instructions="You are a senior code reviewer. Find security bugs and suggest fixes.",
        constitutional_boundaries={"never_modify_production": True},
        allow_delegation=False,
    )

    # Build system prompt without instantiating LLM
    system_prompt = AgentFactory._build_system_prompt(config)

    print(f"=== Created Agent Configuration ===")
    print(f"  Name: {config.name}")
    print(f"  Rank: {config.rank}")
    print(f"  Model preference: {config.model_preference}")
    print(f"  Tools: {config.tools}")
    print(f"  Delegation: {config.allow_delegation}")
    print(f"  System prompt preview: {system_prompt[:100]}...")
    print()
    print("  (Note: Set GEMINI_API_KEY or OPENAI_API_KEY to instantiate a runnable agent)")


# ============================================================
# Example 3: Register a new custom tool
# ============================================================

@tool("generate_markdown_doc", category="document")
def generate_markdown_doc(title: str, sections: str) -> str:
    """Generate a markdown document with the given title and sections."""
    return f"# {title}\n\n{sections}"


def example_custom_tool():
    """Show how custom tools are registered."""
    print("=== Registered Tools ===")
    for name in list_tools():
        tool_def = get_tool(name)
        print(f"  {name} ({tool_def.category}): {tool_def.description[:60]}...")
    print()


# ============================================================
# Example 4: Run the tiered engineering team
# ============================================================

def example_full_pipeline():
    """Run a feature through the full tiered team pipeline."""
    yaml_path = get_config_path("engineer_crew.yaml")
    configs = load_crew_config(yaml_path)

    print(f"=== Processing Feature Request ===")
    print(f"  Request: Add JWT-based authentication to the FastAPI backend")
    print()

    # Show what would happen
    print("  Tiered Engineering Team:")
    for name, config in configs.items():
        print(f"    {name} (rank={config.rank})")
        print(f"      Tools: {config.tools}")
        print(f"      Models: {config.model_preference}")
    print()

    print("  Pipeline Flow:")
    print("    1. Senior Lead Architect researches & plans the feature")
    print("    2. Proposal registered via FastAPI approval server")
    print("    3. You approve via Discord/Gmail or curl command")
    print("    4. Worker creates feature branches across repos")
    print("    5. Junior Engineer writes the code")
    print("    6. QA Auditor runs tests & linters")
    print("    7. If tests fail, self-correction loop (max 2 attempts)")
    print("    8. Notification sent for your manual production merge")
    print()
    print("  Note: Set API keys and start the server to run actual execution:")
    print("    uvicorn app.approval_server:app --port 8000")
    print("    python agents/worker.py --watch")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("AgentFactory Examples")
    print("=" * 60 + "\n")

    example_load_crew()
    example_custom_agent()
    example_custom_tool()
    example_full_pipeline()
