# Skill Marketplace

AgentFactory supports dynamic skill loading — pluggable packages that bundle tools,
prompts, and configuration for specific agent capabilities.

## Overview

Skills are defined in [`agentfactory/skill.py`](skill.md) and consist of:

- A `Skill` dataclass with metadata (name, description, version, tags)
- A list of `@tool`-decorated functions
- An optional prompt prefix for agent system instructions
- Declared dependencies on other skills

## Built-in vs. Custom Skills

The framework ships with built-in tools in `agentfactory/tools/`. Custom skills
are loaded dynamically at runtime from:

1. **Python packages** — installed via pip, exposing a `skill` attribute
2. **Local directories** — `.py` files in a directory, each defining a skill

## Programmatic Usage

```python
from agentfactory import AgentFactory, Skill
from agentfactory.tools import git_tools, file_tools

# Create an agent factory
factory = AgentFactory()

# Register tools from a skill
factory.register_skill(Skill(
    name="my-expert",
    description="Custom domain expert",
    tools=[git_tools.git_commit_changes, file_tools.write_text_file],
    prompt_prefix="You are a domain expert. Always verify changes.",
    tags=["custom", "expert"],
    category="domain",
))

# Alternatively, load from a package
factory.load_skill_package("agentfactory_skills.excel")

# Load all skills from a directory
factory.load_skills_from_directory("./my_skills/")

# Install a skill's tools into the registry
factory.install_skill("excel-expert")
```

## Skill Package Format

A pip-installable skill package is a standard Python package that exposes
either a `skill` attribute or a `get_skill()` function:

```python
# my_skill_package/__init__.py

from agentfactory.skill import Skill
from my_tool_lib import excel_analyze, excel_export

skill = Skill(
    name="excel-expert",
    description="Excel data analysis and reporting",
    tools=[excel_analyze, excel_export],
    prompt_prefix="You are an Excel expert with deep knowledge of formulas, "
                   "pivot tables, and data visualization.",
    dependencies=["data-reader"],
    version="1.1.0",
    author="Your Name",
    tags=["excel", "data", "analysis"],
    category="business",
    config={"max_rows": 10000},
)
```

## Skill Metadata

Each `Skill` exposes:

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Unique skill identifier |
| `description` | str | Human-readable description |
| `tools` | List[Callable] | `@tool`-decorated functions |
| `prompt_prefix` | str | System prompt additions for this skill |
| `dependencies` | List[str] | Other skill names this depends on |
| `version` | str | Semantic version string |
| `author` | str | Author name |
| `tags` | List[str] | Searchable tags |
| `category` | str | Category for filtering |
| `config` | Dict[str, Any] | Arbitrary skill-specific config |

## Dependency Resolution

Skills can declare dependencies on other skills. The `SkillRegistry` resolves
dependencies automatically:

```python
factory.skill_registry.resolve_dependencies("excel-expert")
# Returns ["data-reader", "excel-expert"] — data-reader first
```
