"""
Config Loader — Loads YAML agent profiles and applies template variables.

Supports:
1. Environment variable interpolation (${VAR_NAME})
2. System path defaults (%USERPROFILE% on Windows, ~ on Unix)
3. Template validation against AgentConfig schema
"""

import os
import re
import yaml
from typing import Dict, Any, Optional
from dataclasses import asdict

from agentfactory.base_agent import AgentConfig
from pathlib import Path

# Default repository paths — populate from environment variables
DEFAULT_REPO_PATHS = {
    "backend": os.environ.get("BACKEND_PATH", ""),
    "frontend": os.environ.get("FRONTEND_PATH", ""),
    "admin_panel": os.environ.get("ADMIN_PATH", ""),
}

# Default agent profile templates
DEFAULT_AGENTS_DIR = Path(__file__).parent
TEMPLATE_CACHE: Dict[str, str] = {}


def load_agent_config(yaml_path: str) -> AgentConfig:
    """
    Load an agent configuration from a YAML file.

    Supports environment variable interpolation in values:
        system_instructions: "Hello from ${USER}"

    Args:
        yaml_path: Path to YAML config file

    Returns:
        AgentConfig instance
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid config file: {yaml_path} — expected a dictionary")

    # Validate required fields
    required = ["agent_name", "rank", "responsibilities"]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field '{field}' in {yaml_path}")

    # Interpolate environment variables
    data = _interpolate_env_vars(data)

    return AgentConfig(
        name=data["agent_name"],
        rank=data["rank"],
        role_description=data["responsibilities"],
        tools=data.get("tools", []),
        model_preference=data.get("model_preference", ["gemini-2.5-flash", "gpt-4o"]),
        system_instructions=data.get("system_instructions", ""),
        constitutional_boundaries=data.get("constitutional_boundaries", {}),
        allow_delegation=data.get("allow_delegation", False),
        temperature=data.get("temperature", 0.2),
    )


def load_crew_config(yaml_path: str) -> Dict[str, AgentConfig]:
    """
    Load multiple agent configurations from a crew YAML file.

    The YAML can have either:
    - Top level: a single agent config
    - Under 'agents': a list of agent configs

    Args:
        yaml_path: Path to YAML config file

    Returns:
        Dict mapping agent name -> AgentConfig
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid config file: {yaml_path}")

    data = _interpolate_env_vars(data)

    configs: Dict[str, AgentConfig] = {}

    # Handle "agents" key containing a list
    if "agents" in data:
        for agent_def in data["agents"]:
            if not isinstance(agent_def, dict):
                continue
            name = agent_def.get("name", agent_def.get("agent_name", "unknown"))
            config = _dict_to_config(agent_def)
            configs[name] = config
    else:
        # Single agent config at top level
        config = _dict_to_config(data)
        configs[config.name] = config

    return configs


def _dict_to_config(data: Dict[str, Any]) -> AgentConfig:
    """Convert a dict to AgentConfig."""
    return AgentConfig(
        name=data.get("name", data.get("agent_name", "unknown")),
        rank=data.get("rank", "Junior"),
        role_description=data.get("responsibilities", data.get("role_description", "")),
        tools=data.get("tools", []),
        model_preference=data.get("model_preference", ["gemini-2.5-flash", "gpt-4o"]),
        system_instructions=data.get("system_instructions", ""),
        constitutional_boundaries=data.get("constitutional_boundaries", {}),
        allow_delegation=data.get("allow_delegation", False),
        temperature=data.get("temperature", 0.2),
    )


def _interpolate_env_vars(data: Any, _depth: int = 0) -> Any:
    """
    Recursively interpolate ${VAR_NAME} and ${VAR_NAME:default} patterns.

    Supports nested dicts, lists, and strings.
    """
    if _depth > 10:
        return data

    env_pattern = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

    def replace_env(match):
        var_name = match.group(1)
        default = match.group(2)
        value = os.environ.get(var_name, default if default is not None else "")

        # Expand ~ and user paths
        if value.startswith("~"):
            value = os.path.expanduser(value)

        return value

    if isinstance(data, dict):
        return {k: _interpolate_env_vars(v, _depth + 1) for k, v in data.items()}
    elif isinstance(data, list):
        return [_interpolate_env_vars(item, _depth + 1) for item in data]
    elif isinstance(data, str):
        return env_pattern.sub(replace_env, data)
    else:
        return data


def create_default_configs(output_dir: str = "agents/examples/") -> Dict[str, str]:
    """
    Generate default example agent configuration files.

    Args:
        output_dir: Directory to write example configs

    Returns:
        Dict of filename -> file path
    """
    os.makedirs(output_dir, exist_ok=True)

    configs = {
        "engineer_crew.yaml": """
# 3-tier Engineering Team Configuration
# This config creates a Senior → Junior → QA workflow

system_architecture: "Hierarchical_Supervisor_Worker"
max_worker_iterations: 2
failover_enabled: true

agents:
  - name: "Senior_Lead_Architect"
    rank: "Senior"
    model_preference: ["gemini-2.5-flash", "gpt-4o"]
    responsibilities: "Analyze repos, research tech trends, produce implementation blueprints"
    allow_delegation: true
    tools: ["research_web_for_upgrades", "analyze_codebase_files"]

  - name: "Junior_Feature_Engineer"
    rank: "Junior"
    model_preference: ["gemini-2.5-flash", "gpt-4o-mini"]
    responsibilities: "Write code on isolated branches across multi-repo projects"
    allow_delegation: false
    tools: ["create_feature_branch", "write_file_to_repo", "git_add_commit_push"]

  - name: "QA_Security_Auditor"
    rank: "QA"
    model_preference: ["gpt-4o-mini"]
    responsibilities: "Run tests and linters, report pass/fail with error context"
    allow_delegation: false
    tools: ["analyze_codebase_files"]
""",

        "excel_agent.yaml": """
# Excel Data Processing Agent
agent_name: "ExcelEngineer"
rank: "Senior"
model_preference: ["gemini-2.5-flash", "gpt-4o"]
responsibilities: "Convert PDFs, Markdown, and text into verified Excel spreadsheets"
allow_delegation: false
constitutional_boundaries:
  max_budget_usd_per_day: 3.00
  never_hardcode_values: true
tools: ["read_file_lines", "send_discord_notification"]
system_instructions: |
  You are an Excel Engineering Agent. Convert documents to spreadsheets and
  always run post-creation verification checks for row/column counts and nulls.
""",

        "researcher_agent.yaml": """
# Web Research Agent
agent_name: "ResearchBot"
rank: "Junior"
model_preference: ["gemini-2.5-flash"]
responsibilities: "Search the web, extract key findings, produce research summaries"
allow_delegation: false
tools: ["research_web_for_upgrades"]
system_instructions: |
  You are a research agent. Search the web for the latest information and
  summarize findings with source citations.
""",
    }

    written = {}
    for filename, content in configs.items():
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip())
        written[filename] = filepath

    return written


def get_config_path(filename: str) -> str:
    """Get the absolute path to an example config file."""
    return str(DEFAULT_AGENTS_DIR / "examples" / filename)
