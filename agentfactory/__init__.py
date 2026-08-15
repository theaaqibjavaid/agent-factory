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

__all__ = ["cli", "AgentFactory", "RunnableAgent", "__version__"]
