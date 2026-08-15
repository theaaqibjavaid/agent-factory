"""
AgentFactory — Universal AI Agent Framework.

A production-grade, clonable Python framework for creating any type of AI agent
(Excel agents, software engineers, researchers, etc.).

Usage:
    from agentfactory import AgentFactory, RunnableAgent
    from agentfactory.tools import git_tools, file_tools

    # Create an agent
    factory = AgentFactory()
    agent = factory.create_agent("Senior")
    result = await agent.run("Implement user authentication in the backend")
"""

__version__ = "1.0.0"
__author__ = "Aaqib"
__license__ = "MIT"

from agentfactory.cli import cli
from agentfactory.base_agent import AgentFactory, RunnableAgent
from agentfactory.skill import Skill, SkillRegistry
from agentfactory.memory import PersistentMemory
from agentfactory.mcp_integration import MCPServerConfig, MCPClient

__all__ = [
    "cli",
    "AgentFactory",
    "RunnableAgent",
    "Skill",
    "SkillRegistry",
    "PersistentMemory",
    "MCPServerConfig",
    "MCPClient",
    "__version__",
]
