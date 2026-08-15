"""
Tests for AgentFactory modules.
"""

import os
import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentfactory.llm_manager import FailoverLLMManager, LLMConfig
from agentfactory.base_agent import AgentFactory, AgentConfig
from agentfactory.base_tools import list_tools, get_tool
from agentfactory.verifier import Verifier, VerificationReport, AuditResult
# ============================================================
# LLM Manager Tests
# ============================================================

class TestFailoverLLMManager:
    def test_init_default_pipeline(self):
        """Test default pipeline initialization."""
        manager = FailoverLLMManager()
        assert len(manager.pipeline) == 3
        assert manager.pipeline[0].provider == "google"
        assert manager.pipeline[0].model == "gemini-2.5-flash"

    def test_init_custom_pipeline(self):
        """Test custom pipeline."""
        pipeline = [
            LLMConfig(provider="google", model="gemini-1.5-flash", api_key_env="GEMINI_API_KEY"),
        ]
        manager = FailoverLLMManager(pipeline=pipeline, daily_budget_usd=10.0)
        assert len(manager.pipeline) == 1
        assert manager.daily_budget_usd == 10.0

    def test_handle_rate_limit_failover(self):
        """Test rate limit failover."""
        manager = FailoverLLMManager()
        initial_index = manager.current_index
        manager.handle_rate_limit_failover()
        assert manager.current_index == initial_index + 1

    def test_reset(self):
        """Test reset."""
        manager = FailoverLLMManager()
        manager.current_index = 2
        manager.reset()
        assert manager.current_index == 0
        assert manager.current_spend_usd == 0.0


# ============================================================
# Base Tools Tests
# ============================================================

class TestBaseTools:
    def test_tool_registration(self):
        """Test that built-in tools are registered."""
        tools = list_tools()
        assert "research_web_for_upgrades" in tools
        assert "analyze_codebase_files" in tools
        assert "send_discord_notification" in tools

    def test_get_tool(self):
        """Test retrieving a tool."""
        tool_def = get_tool("analyze_codebase_files")
        assert tool_def is not None
        # Alias maps to list_directory_contents internally
        assert "directory" in tool_def.description.lower() or tool_def.name == "list_directory_contents"

    def test_get_tool_not_found(self):
        """Test that missing tool raises KeyError."""
        with pytest.raises(KeyError):
            get_tool("nonexistent_tool")


# ============================================================
# Base Agent Tests
# ============================================================

class TestAgentFactory:
    def test_create_agent_config(self):
        """Test creating an agent config."""
        config = AgentConfig(
            name="TestAgent",
            rank="Junior",
            role_description="Test role",
            tools=["analyze_codebase_files"],
            model_preference=["gemini-2.5-flash"],
            system_instructions="Test instructions",
        )
        assert config.name == "TestAgent"
        assert config.rank == "Junior"

    def test_build_system_prompt(self):
        """Test system prompt construction."""
        config = AgentConfig(
            name="TestAgent",
            rank="Senior",
            role_description="Test role",
            system_instructions="Test instructions",
            tools=["analyze_codebase_files"],
            constitutional_boundaries={"never_touch_main": True},
            allow_delegation=True,
        )
        prompt = AgentFactory._build_system_prompt(config)
        assert "Test instructions" in prompt
        assert "Senior" in prompt
        assert "allow_delegation" in prompt.lower() or "authorized to delegate" in prompt


# ============================================================
# Verifier Tests
# ============================================================

class TestVerifier:
    def test_verification_report_creation(self):
        """Test VerificationReport creation."""
        report = VerificationReport(
            feature_name="test-feature",
            branch_name="feature/test-feature",
        )
        assert report.feature_name == "test-feature"
        assert report.overall_passed is True

    def test_add_check_pass(self):
        """Test adding a passing check."""
        report = VerificationReport(feature_name="test", branch_name="feature/test")
        check = AuditResult(
            name="pytest",
            passed=True,
            message="All tests passed",
        )
        report.add_check(check)
        assert len(report.checks) == 1
        assert report.overall_passed is True

    def test_add_check_fail(self):
        """Test adding a failing check."""
        report = VerificationReport(feature_name="test", branch_name="feature/test")
        check = AuditResult(
            name="pytest",
            passed=False,
            message="1 test failed",
        )
        report.add_check(check)
        assert len(report.checks) == 1
        assert report.overall_passed is False

    def test_to_dict(self):
        """Test report serialization."""
        report = VerificationReport(feature_name="test", branch_name="feature/test")
        report.add_check(AuditResult(name="lint", passed=True, message="Clean"))

        d = report.to_dict()
        assert d["feature_name"] == "test"
        assert d["branch_name"] == "feature/test"
        assert len(d["checks"]) == 1
        assert d["checks"][0]["name"] == "lint"


# ============================================================
# Config Loader Tests
# ============================================================

class TestConfigLoader:
    def test_load_agent_config(self):
        """Test loading an agent config from YAML."""
        from agentfactory.agents.config_loader import load_agent_config, get_config_path

        yaml_path = get_config_path("engineer_crew.yaml")
        assert os.path.exists(yaml_path)

    def test_default_repo_paths(self):
        """Test default repo paths."""
        from agentfactory.agents.config_loader import DEFAULT_REPO_PATHS
        assert "backend" in DEFAULT_REPO_PATHS
        assert "frontend" in DEFAULT_REPO_PATHS
        assert "admin_panel" in DEFAULT_REPO_PATHS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
