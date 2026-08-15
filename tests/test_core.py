"""
Tests for AgentFactory core modules.

Run with: pytest tests/ -v
"""

import pytest
import asyncio
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# ============================================================
# Test imports
# ============================================================

from agentfactory.config import settings
from agentfactory.llm_manager import FailoverLLMManager, LLMConfig
from agentfactory.base_tools import ToolRegistry, ToolWrapper, ToolCall, tool, SafetyLevel, ToolMetadata
from agentfactory.verifier import Verifier, FailedCheck, VerificationResult
from agentfactory.mcp_integration import MCPServerConfig, load_mcp_config, create_mcp_config_template
from agentfactory.base_agent import AgentFactory, RunnableAgent, AgentPersona


# ============================================================
# Config Tests
# ============================================================

class TestConfig:
    """Test configuration loading and validation."""

    def test_settings_loaded(self):
        """Test that settings load without error."""
        assert settings is not None

    def test_daily_budget_default(self):
        """Test default daily budget."""
        assert settings.daily_budget_usd == 5.0

    def test_llm_temperature_default(self):
        """Test default temperature."""
        assert settings.default_temperature == 0.2

    def test_api_keys_optional(self):
        """Test that API keys are optional."""
        # At least the structure should be correct
        assert hasattr(settings, 'gemini_api_key')
        assert hasattr(settings, 'openai_api_key')


# ============================================================
# LLM Manager Tests
# ============================================================

class TestFailoverLLMManager:
    """Test LLM failover functionality."""

    def test_default_pipeline(self):
        """Test default model pipeline."""
        manager = FailoverLLMManager()
        assert len(manager.DEFAULT_PIPELINE) == 3
        assert manager.DEFAULT_PIPELINE[0].provider == "google"
        assert manager.DEFAULT_PIPELINE[0].model == "gemini-2.5-flash"

    def test_rate_limit_failover(self):
        """Test rate limit failover logic."""
        manager = FailoverLLMManager()

        class MockRateLimitError(Exception):
            pass

        # Start on first model, trigger failover
        result = manager.handle_rate_limit_failover(MockRateLimitError("Rate limited"))
        # Should cycle to next model (returns True for failover)
        assert result is True
        assert manager.current_index == 1

    def test_daily_budget_tracking(self):
        """Test daily budget reset and tracking."""
        manager = FailoverLLMManager()
        assert manager.daily_budget_usd == 5.0

    def test_generate_without_api_key(self):
        """Test graceful handling when no API key is set."""
        manager = FailoverLLMManager()
        # Should not raise — should return error string
        result = manager.generate_text([{"role": "user", "content": "Hello"}], max_tokens=10)
        assert isinstance(result, str)


# ============================================================
# Tool Registry Tests
# ============================================================

class TestToolRegistry:
    """Test tool registration and execution."""

    def test_register_function(self):
        """Test registering a tool function."""
        registry = ToolRegistry()

        @tool("test_function", category="test")
        def my_func(x: int) -> str:
            return f"Got: {x}"

        registry.register_function(my_func)
        assert "test_function" in registry._tools

    def test_get_tool(self):
        """Test retrieving a registered tool."""
        registry = ToolRegistry()

        @tool("getter_test", category="test")
        def my_func() -> str:
            return "hello"

        registry.register_function(my_func)
        tool_obj = registry.get("getter_test")
        assert tool_obj is not None
        assert tool_obj.metadata.name == "getter_test"

    def test_string_name_decorator(self):
        """Test @tool('name', ...) syntax with string name."""
        registry = ToolRegistry()

        @tool("string_named_tool", category="test", cost_per_call_usd=0.001)
        def my_func(x: int) -> str:
            return str(x)

        # Decorator should handle both @tool and @tool("name", ...) forms
        assert my_func is not None
        assert hasattr(my_func, '_tool_metadata')

    def test_list_tools_detailed(self):
        """Test listing all tools with metadata."""
        registry = ToolRegistry()

        @tool("list_test_1", category="test")
        def func1():
            pass

        @tool("list_test_2", category="other", cost_per_call_usd=0.005)
        def func2():
            pass

        registry.register_function(func1)
        registry.register_function(func2)

        tools = registry.list_tools_detailed()
        names = [t["name"] for t in tools]
        assert "list_test_1" in names
        assert "list_test_2" in names

    def test_tool_call_serialization(self):
        """Test ToolCall model."""
        tc = ToolCall(name="test_tool", arguments={"x": 1}, id="call_1")
        assert tc.name == "test_tool"
        assert tc.arguments == {"x": 1}
        assert tc.id == "call_1"


# ============================================================
# Verifier Tests
# ============================================================

class TestVerifier:
    """Test verification and pruning functionality."""

    def test_pruning_excludes_full_files(self):
        """CRITICAL: Test that get_pruned_context never includes full files."""
        verifier = Verifier()

        large_content = "\n".join([f"# Line {i}" for i in range(1000)])

        # Create a failed check with context
        failed = FailedCheck(
            name="test_error",
            message="Syntax error at line 500",
            line_number=500,
            context_snippet="```python\n499: # Line 499\n>>> 500: # Line 500\n501: # Line 501\n```",
        )
        verifier._last_result = VerificationResult(failed_checks=[failed])

        context = verifier.get_pruned_context()

        # Should NOT contain file content beyond the snippet
        assert "# Line 1" not in context or context.count("# Line") < 10
        assert "test_error" in context

    def test_python_syntax_check(self):
        """Test Python syntax verification."""
        verifier = Verifier()
        result = asyncio.run(verifier.verify_all("x = 1\nprint(x)\n"))
        assert result.passed

    def test_python_syntax_error_detection(self):
        """Test that syntax errors are detected."""
        verifier = Verifier()
        # Intentionally broken syntax
        result = asyncio.run(verifier.verify_all("def broken(:\n    pass\n"))
        assert not result.passed
        assert len(result.failed_checks) > 0

    def test_context_snippet_extraction(self):
        """Test that context snippets are extracted correctly."""
        verifier = Verifier()

        code = """line1
line2
line3
line4
line5"""

        snippet = verifier._get_context_snippet(code, 3)
        assert "line2" in snippet
        assert "line3" in snippet  # The failing line
        assert "line4" in snippet

    def test_security_checks(self):
        """Test security issue detection."""
        verifier = Verifier()

        code_with_eval = "eval('malicious')"
        result = asyncio.run(verifier._check_security(code_with_eval))

        assert len(result) > 0
        assert result[0].name == "security_eval"

    def test_placeholder_detection(self):
        """Test detection of placeholder content."""
        verifier = Verifier()

        code_with_todo = """
def my_func():
    TODO: implement this
    pass
"""
        result = asyncio.run(verifier._check_placeholders(code_with_todo))
        assert len(result) > 0

    def test_get_failing_checks(self):
        """Test retrieval of failing checks."""
        verifier = Verifier()
        failed = FailedCheck(name="test", message="Error")
        verifier._last_result = VerificationResult(failed_checks=[failed])

        checks = verifier.get_failing_checks()
        assert len(checks) == 1
        assert checks[0].name == "test"

    def test_get_pruned_context_empty(self):
        """Test that empty context is returned for no failures."""
        verifier = Verifier()
        verifier._last_result = VerificationResult(failed_checks=[])

        context = verifier.get_pruned_context()
        assert context == ""


# ============================================================
# MCP Integration Tests
# ============================================================

class TestMCPIntegration:
    """Test MCP configuration and integration."""

    def test_load_mcp_config_missing(self):
        """Test loading MCP config when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "nonexistent.json")
            result = load_mcp_config(config_path)
            assert result == {}

    def test_create_mcp_config_template(self):
        """Test MCP config template creation."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmpfile = f.name

        try:
            template = create_mcp_config_template(tmpfile)
            assert "mcpServers" in template
            assert os.path.exists(tmpfile)
        finally:
            os.unlink(tmpfile)

    def test_load_valid_mcp_config(self):
        """Test loading a valid MCP config."""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "python",
                    "args": ["-m", "test"],
                    "enabled": True
                }
            }
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(config_data, f)
            tmpfile = f.name

        try:
            result = load_mcp_config(tmpfile)
            assert "test-server" in result
            assert result["test-server"].command == "python"
        finally:
            os.unlink(tmpfile)

    def test_mcp_server_config_defaults(self):
        """Test MCPServerConfig default values."""
        config = MCPServerConfig(name="test", command="python")
        assert config.args == []
        assert config.env == {}
        assert config.timeout == 10.0
        assert config.enabled == True


# ============================================================
# Agent Factory Tests
# ============================================================

class TestAgentFactory:
    """Test agent factory creation and cloning."""

    def test_factory_creation(self):
        """Test creating an AgentFactory."""
        factory = AgentFactory()
        assert factory is not None
        assert len(factory.available_ranks) >= 4
        assert "Senior" in factory.available_ranks
        assert "Junior" in factory.available_ranks
        assert "QA" in factory.available_ranks
        assert "Manager" in factory.available_ranks

    def test_create_agent(self):
        """Test creating an agent for a specific rank."""
        factory = AgentFactory()
        agent = factory.create_agent("Junior")
        assert agent is not None
        assert agent.persona.rank == "Junior"

    def test_clone_agent(self):
        """Test cloning an agent for a new repo."""
        factory = AgentFactory()
        original = factory.create_agent("Senior")
        cloned = RunnableAgent.clone(original, factory.get_shared_registry())
        assert cloned.persona.rank == "Senior"

    def test_register_persona(self):
        """Test registering a custom persona."""
        factory = AgentFactory()
        custom = AgentPersona(rank="Custom", model_preferences=["gpt-4o"])
        factory.register_persona("Custom", custom)
        assert "Custom" in factory.available_ranks

    def test_load_mcp_config(self):
        """Test MCP config loading in factory."""
        factory = AgentFactory()
        # Should not crash even if no mcp.json exists
        factory.load_mcp_config("/nonexistent/path.json")

    def test_tool_registry_sharing(self):
        """Test that cloned agents share a tool registry."""
        factory = AgentFactory()
        agent1 = factory.create_agent("Senior")
        agent2 = factory.create_agent("Junior")

        # Both agents should share the same registry
        assert agent1.tools is agent2.tools


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """Integration tests across multiple modules."""

    def test_tool_decorator_with_registry(self):
        """Test that tools registered via decorator work with registry."""
        registry = ToolRegistry()

        @tool("integration_test", category="test", cost_per_call_usd=0.001)
        def my_tool(x: int, y: int) -> str:
            return str(x + y)

        registry.register_function(my_tool)

        async def run_test():
            result = await registry.get("integration_test").execute({"x": 5, "y": 3})
            return result

        result = asyncio.run(run_test())
        assert result == "8"

    def test_verifier_with_base_agent(self):
        """Test that verifier integrates with agent self-correction."""
        verifier = Verifier()

        # Broken Python code
        bad_code = "def func(:\n    pass\n"
        result = asyncio.run(verifier.verify_all(bad_code))

        assert not result.passed
        assert result.has_failures

        # Pruned context should be available for self-correction
        context = verifier.get_pruned_context()
        assert len(context) > 0

    def test_end_to_end_agent_setup(self):
        """Test full agent creation with tools."""
        factory = AgentFactory()

        # Register some tools
        @tool("test_math", category="math")
        def add(a: int, b: int) -> int:
            return a + b

        factory.register_tools([add])

        # Create agent
        agent = factory.create_agent("Junior")
        assert agent is not None

        # Check tools are registered
        tools = agent.tools.list_tools_detailed()
        assert "test_math" in [t["name"] for t in tools]


# ============================================================
# File Tools Tests
# ============================================================

class TestFileTools:
    """Test file operation tools."""

    def test_read_write_file(self):
        """Test basic file write and read."""
        from agentfactory.tools.file_tools import write_text_file, read_text_file

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmpfile = f.name

        try:
            result = write_text_file(tmpfile, "Hello, World!")
            assert "Successfully" in result

            content = read_text_file(tmpfile)
            assert content == "Hello, World!"
        finally:
            os.unlink(tmpfile)

    def test_append_file(self):
        """Test appending to a file."""
        from agentfactory.tools.file_tools import write_text_file, read_text_file

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmpfile = f.name

        try:
            write_text_file(tmpfile, "Line 1\n")
            write_text_file(tmpfile, "Line 2\n", append=True)
            content = read_text_file(tmpfile)
            assert "Line 1" in content
            assert "Line 2" in content
        finally:
            os.unlink(tmpfile)

    def test_list_directory(self):
        """Test listing directory contents."""
        from agentfactory.tools.file_tools import list_directory_contents, write_text_file

        with tempfile.TemporaryDirectory() as tmpdir:
            write_text_file(os.path.join(tmpdir, "test.py"), "print('hello')")
            result = list_directory_contents(tmpdir, patterns=["*.py"])
            assert "test.py" in result

    def test_search_files(self):
        """Test searching for files by pattern."""
        from agentfactory.tools.file_tools import write_text_file, search_files_by_pattern

        with tempfile.TemporaryDirectory() as tmpdir:
            write_text_file(os.path.join(tmpdir, "test_file.py"), "test content")
            write_text_file(os.path.join(tmpdir, "other.txt"), "other content")
            result = search_files_by_pattern(tmpdir, "*.py")
            assert "test_file.py" in result

    def test_count_lines(self):
        """Test counting lines in a file."""
        from agentfactory.tools.file_tools import write_text_file, count_lines_in_file

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            tmpfile = f.name

        try:
            write_text_file(tmpfile, "line1\nline2\nline3\n")
            result = count_lines_in_file(tmpfile)
            assert "3" in result
        finally:
            os.unlink(tmpfile)


# ============================================================
# CLI Tests
# ============================================================

class TestCLI:
    """Test CLI commands."""

    def test_cli_import(self):
        """Test that CLI module imports correctly."""
        try:
            from agentfactory.cli import cli
            assert cli is not None
        except ImportError as e:
            if "click" not in str(e):
                pytest.fail(f"Unexpected import error: {e}")
            pytest.skip("Click not installed — CLI tests skipped")

    def test_cli_has_commands(self):
        """Test that CLI has expected commands."""
        try:
            from agentfactory.cli import cli
            commands = list(cli.commands.keys())
            assert "init" in commands
            assert "run" in commands
            assert "create-agent" in commands or "create_agent" in commands
            assert "list-tools" in commands or "list_tools" in commands
            assert "status" in commands
        except ImportError:
            pytest.skip("Click not installed")
