"""
Skill Marketplace — Dynamic skill loading and management.

Skills are pluggable packages that bundle tools, prompts, and configuration
for specific agent capabilities (e.g., Excel expert, email assistant, researcher).

Usage:
    # Register a skill programmatically
    factory = AgentFactory()
    factory.skill_registry.register_skill(Skill(
        name="excel-expert",
        tools=[excel_parse, excel_format],
        prompt_prefix="You are an Excel expert...",
    ))

    # Load a skill from a Python package
    skill = load_skill("agentfactory_skills.excel")

    # Load skills from a marketplace directory
    factory.load_skills_from_directory("./my_skills/")
"""

import importlib
import importlib.util
import os
import inspect
import structlog
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from agentfactory.base_tools import ToolRegistry, ToolDef

logger = structlog.get_logger()


@dataclass
class Skill:
    """
    A pluggable skill package that bundles tools and configuration.

    Skills can be registered programmatically or loaded dynamically
    from Python packages or directories.
    """
    name: str
    description: str = ""
    tools: List[Callable] = field(default_factory=list)
    prompt_prefix: str = ""
    dependencies: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    category: str = "generic"
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.description and self.tools:
            self.description = f"Skill providing {len(self.tools)} tools"

    def register_into(self, registry: ToolRegistry) -> None:
        """Register all tools from this skill into a ToolRegistry."""
        for tool_func in self.tools:
            registry.register_function(tool_func)
        logger.debug(f"Registered skill '{self.name}' with {len(self.tools)} tools")

    to_dict = lambda self: {
        "name": self.name,
        "description": self.description,
        "tool_count": len(self.tools),
        "version": self.version,
        "author": self.author,
        "category": self.category,
        "tags": self.tags,
        "dependencies": self.dependencies,
        "config": self.config,
    }


class SkillRegistry:
    """
    Registry of available skills with dynamic loading support.

    Supports:
    - Programmatic registration
    - Loading from Python packages (pip-installed skills)
    - Loading from directories (local skill files)
    - Dependency resolution
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._loaded_package_names: List[str] = []

    def register_skill(self, skill: Skill) -> None:
        """Register a skill into the registry."""
        if skill.name in self._skills:
            logger.warning(f"Skill '{skill.name}' already registered, overwriting")
        self._skills[skill.name] = skill
        logger.debug(f"Registered skill: {skill.name}")

    def get_skill(self, name: str) -> Optional[Skill]:
        """Retrieve a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """List all registered skill names."""
        return list(self._skills.keys())

    def list_skills_detailed(self) -> List[Dict[str, Any]]:
        """List all skills with metadata."""
        return [skill.to_dict() for skill in self._skills.values()]

    def get_by_category(self, category: str) -> List[Skill]:
        """Get all skills in a category."""
        return [s for s in self._skills.values() if s.category == category]

    def get_by_tag(self, tag: str) -> List[Skill]:
        """Get all skills with a specific tag."""
        return [s for s in self._skills.values() if tag in s.tags]

    def install_skill(self, skill: Skill, registry: ToolRegistry) -> None:
        """
        Install a skill into a tool registry.

        Registers all the skill's tools and stores the prompt_prefix
        for later use when composing agent system prompts.
        """
        if skill.name not in self._skills:
            raise ValueError(f"Unknown skill: {skill.name}")
        skill.register_into(registry)
        logger.info(f"Installed skill '{skill.name}' into tool registry")

    def uninstall_skill(self, skill_name: str, registry: ToolRegistry) -> None:
        """Remove a skill's tools from a registry."""
        skill = self.get_skill(skill_name)
        if not skill:
            return
        # Remove tools from registry
        for tool_func in skill.tools:
            tool_name = getattr(tool_func, "_tool_metadata", {}).get("name", tool_func.__name__)
            if tool_name in registry._tools:
                del registry._tools[tool_name]
        logger.info(f"Uninstalled skill '{skill_name}' from tool registry")

    # ============================================================
    # Dynamic Loading
    # ============================================================

    def load_from_package(self, package_name: str) -> Optional[Skill]:
        """
        Load a skill from an installed Python package.

        The package should define a `skill` attribute that is a Skill instance,
        or a `get_skill()` function that returns one.
        """
        try:
            module = importlib.import_module(package_name)
        except ImportError as e:
            logger.warning(f"Could not import skill package '{package_name}': {e}")
            return None

        skill = None
        if hasattr(module, "skill"):
            skill = module.skill
        elif hasattr(module, "get_skill"):
            skill = module.get_skill()

        if skill is None:
            logger.warning(f"No skill found in package '{package_name}'")
            return None

        if not isinstance(skill, Skill):
            logger.warning(f"Expected Skill instance in '{package_name}', got {type(skill)}")
            return None

        self.register_skill(skill)
        self._loaded_package_names.append(package_name)
        logger.info(f"Loaded skill from package: {package_name} -> {skill.name}")
        return skill

    def load_from_directory(self, directory: str) -> List[Skill]:
        """
        Load all skills from a directory of Python files.

        Each .py file in the directory should define a `skill` attribute
        or `get_skill()` function.
        """
        skills: List[Skill] = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.warning(f"Skill directory does not exist: {directory}")
            return skills

        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name.startswith("_") or py_file.name.startswith("test"):
                continue

            try:
                skill = self._load_skill_from_file(py_file)
                if skill:
                    self.register_skill(skill)
                    skills.append(skill)
            except Exception as e:
                logger.warning(f"Failed to load skill from {py_file}: {e}")

        logger.info(f"Loaded {len(skills)} skills from directory: {directory}")
        return skills

    def _load_skill_from_file(self, py_file: Path) -> Optional[Skill]:
        """Load a single skill from a .py file."""
        module_name = f"_skill_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        skill = None
        if hasattr(module, "skill"):
            skill = module.skill
        elif hasattr(module, "get_skill"):
            skill = module.get_skill()

        if skill and isinstance(skill, Skill):
            return skill

        logger.debug(f"No skill found in {py_file}")
        return None

    def resolve_dependencies(self, skill_name: str, installed: Optional[set] = None) -> List[str]:
        """
        Resolve all dependencies for a skill in load order.

        Returns a list of skill names in the order they should be loaded.
        """
        if installed is None:
            installed = set()

        skill = self.get_skill(skill_name)
        if not skill or skill_name in installed:
            return []

        order = []
        for dep in skill.dependencies:
            if dep not in installed:
                order.extend(self.resolve_dependencies(dep, installed))

        installed.add(skill_name)
        order.append(skill_name)
        return order

    def install_all(self, registry: ToolRegistry, categories: Optional[List[str]] = None) -> None:
        """
        Install all registered skills into a tool registry.

        Args:
            registry: The tool registry to install into
            categories: If provided, only install skills in these categories
        """
        for skill in self._skills.values():
            if categories and skill.category not in categories:
                continue
            skill.register_into(registry)
        logger.info(f"Installed {len(self._skills)} skills into tool registry")

    def clear(self) -> None:
        """Clear all registered skills."""
        self._skills.clear()
        self._loaded_package_names.clear()