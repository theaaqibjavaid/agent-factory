"""
Background Worker — Polls for approved proposals and executes them.

Usage:
    python agents/worker.py --watch --poll-interval 5

The worker:
1. Polls the approval server for APPROVED proposals
2. Assigns tasks to Senior/Junior agents
3. Executes code generation and commits changes
4. Marks proposals as COMPLETED when done
"""

import os
import sys
import time
import json
import argparse
import structlog
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentfactory.config import settings
from agentfactory.base_agent import AgentFactory, AgentPersona
from agentfactory.base_tools import ToolRegistry

logger = structlog.get_logger()


class AgentWorker:
    """Background worker that processes approved proposals."""

    def __init__(self, server_url: str = None, poll_interval: int = 5):
        self.server_url = server_url or os.getenv("AGENT_SERVER_URL", "http://localhost:8000")
        self.poll_interval = poll_interval
        self._running = False

        # Optional bearer token for talking to an auth-enabled approval server
        server_token = os.getenv("AGENT_SERVER_TOKEN", "")
        self._headers = {"Authorization": f"Bearer {server_token}"} if server_token else {}

        # Initialize agent factory
        self.factory = AgentFactory()

        # Register available tools
        self._register_tools()

        # Set up MCP config if available
        if Path("mcp.json").exists():
            self.factory.load_mcp_config("mcp.json")

    def _register_tools(self):
        """Register all available tools."""
        registry = self.factory.get_shared_registry()

        # Git tools
        try:
            from agentfactory.tools.git_tools import (
                git_create_branch, git_commit_changes, git_check_status,
                git_create_pull_request, git_get_recent_commits,
                git_switch_branch, git_sync_fork
            )
            for t in [git_create_branch, git_commit_changes, git_check_status,
                      git_create_pull_request, git_get_recent_commits, git_switch_branch, git_sync_fork]:
                registry.register_function(t)
        except ImportError as e:
            logger.warning(f"Could not load git tools: {e}")

        # File tools
        try:
            from agentfactory.tools.file_tools import (
                write_text_file, read_text_file, list_directory_contents,
                create_directory, search_files_by_pattern, count_lines_in_file
            )
            for t in [write_text_file, read_text_file, list_directory_contents,
                      create_directory, search_files_by_pattern, count_lines_in_file]:
                registry.register_function(t)
        except ImportError as e:
            logger.warning(f"Could not load file tools: {e}")

        # Web tools
        try:
            from agentfactory.tools.web_tools import web_search, web_fetch, web_scrape_links
            for t in [web_search, web_fetch, web_scrape_links]:
                registry.register_function(t)
        except ImportError as e:
            logger.warning(f"Could not load web tools: {e}")

        # Notify tools
        try:
            from agentfactory.tools.notify_tools import send_discord_notification, send_gmail_notification
            for t in [send_discord_notification, send_gmail_notification]:
                registry.register_function(t)
        except ImportError as e:
            logger.warning(f"Could not load notify tools: {e}")

    def run(self):
        """Start the worker loop."""
        self._running = True
        logger.info("Agent worker started", server=self.server_url, poll_interval=self.poll_interval)

        print(f"🔄 Worker started — polling {self.server_url} every {self.poll_interval}s")
        print("Press Ctrl+C to stop.\n")

        try:
            while self._running:
                self._process_pending_proposals()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("\n🛑 Worker stopped.")
            self._running = False

    def _process_pending_proposals(self):
        """Check for and process approved proposals."""
        import requests

        try:
            response = requests.get(f"{self.server_url}/api/agent/status", headers=self._headers, timeout=10)
            if response.status_code != 200:
                return

            data = response.json()
            status = data.get("status", "IDLE")

            if status == "APPROVED":
                self._execute_proposal(data)
            elif status == "PENDING":
                logger.debug("Proposal pending approval")
            elif status == "IDLE":
                pass  # No active proposal
            elif status == "COMPLETED":
                pass  # Already completed
            elif status == "REJECTED":
                logger.info("Proposal was rejected by human")
            elif status == "MODIFIED":
                logger.info("Proposal was modified by human")

        except requests.exceptions.ConnectionError:
            # Server not running yet — wait for it
            pass
        except Exception as e:
            logger.error(f"Error checking proposals: {e}")

    def _execute_proposal(self, proposal_data):
        """Execute an approved proposal."""
        feature_name = proposal_data.get("feature_name", "unknown-feature")
        plan = proposal_data.get("plan", "")
        blueprint = proposal_data.get("blueprint") or {}
        extra_instructions = proposal_data.get("extra_instructions")

        logger.info(f"Executing approved proposal: {feature_name}")

        # Determine target repository
        repo_path = self._resolve_repo_path(feature_name, blueprint)

        # Create agent from config for this repo
        from agentfactory.agents.config_loader import load_crew_config, get_config_path

        # Load crew config to get the proper agent tier
        try:
            configs = load_crew_config(get_config_path("engineer_crew.yaml"))
            junior_config = configs.get("Junior_Feature_Engineer")
        except Exception:
            junior_config = None

        if junior_config:
            from agentfactory.base_agent import AgentPersona, RunnableAgent
            from agentfactory.llm_manager import FailoverLLMManager

            persona = AgentPersona(
                rank=junior_config.rank,
                responsibilities=[junior_config.role_description] if junior_config.role_description else [],
                system_instructions=junior_config.system_instructions,
                model_preferences=junior_config.model_preference,
                max_budget_usd_per_day=junior_config.max_budget_usd_per_day,
                allow_delegation=junior_config.allow_delegation,
            )
            llm_manager = FailoverLLMManager(
                model_preferences=junior_config.model_preference,
                daily_budget_usd=junior_config.max_budget_usd_per_day,
            )
            agent = RunnableAgent(
                persona=persona,
                tool_registry=self.factory.get_shared_registry(),
                llm_manager=llm_manager,
            )
        else:
            agent = self.factory.create_agent("Junior")

        # Build execution task
        task = self._build_execution_task(feature_name, plan, blueprint, extra_instructions)

        # Run the agent asynchronously
        import asyncio

        async def _run():
            result = await agent.run(
                task_description=task,
                max_iterations=30,
            )
            return result

        try:
            result = asyncio.run(_run())
            logger.info(f"Proposal execution completed: {feature_name}")

            # Mark as completed on the server
            import requests
            try:
                requests.post(f"{self.server_url}/api/agent/executed", headers=self._headers, timeout=10)
            except Exception as e:
                logger.warning(f"Could not mark proposal as completed: {e}")

            # Send completion notification
            self._send_completion_notification(feature_name, result)

        except Exception as e:
            logger.error(f"Error executing proposal {feature_name}: {e}", exc_info=True)
            self._send_error_notification(feature_name, str(e))

    def _resolve_repo_path(self, feature_name: str, blueprint: dict) -> str:
        """Resolve which repository this feature belongs to."""
        # Check blueprint for repo hint
        if blueprint and blueprint.get("repo"):
            return blueprint["repo"]

        # Check feature name for hints
        feature_lower = feature_name.lower()
        if "backend" in feature_lower or "api" in feature_lower:
            return os.getenv("BACKEND_PATH", ".")
        elif "frontend" in feature_lower or "ui" in feature_lower or "react" in feature_lower:
            return os.getenv("FRONTEND_PATH", ".")
        elif "admin" in feature_lower:
            return os.getenv("ADMIN_PATH", ".")

        return os.getenv("BACKEND_PATH", ".")

    def _build_execution_task(self, feature_name: str, plan: str, blueprint: dict, extra_instructions: str) -> str:
        """Build the task description for the agent."""
        task = f"""
## Feature Implementation Task: {feature_name}

### Implementation Plan
{plan}

### Blueprint
{json.dumps(blueprint, indent=2) if blueprint else 'No blueprint provided'}

### Extra Instructions
{extra_instructions or 'No additional instructions'}

### Requirements
1. Implement the feature following the plan
2. Write clean, production-ready code
3. Include appropriate error handling
4. Run verification checks (syntax, patterns, security)
5. Self-correct any verification failures using pruned context

### Output
Provide a summary of what was implemented, including:
- Files created or modified
- Any breaking changes
- Testing recommendations
"""
        return task

    def _send_completion_notification(self, feature_name: str, result: dict):
        """Send notification that a proposal was completed."""
        try:
            from agentfactory.tools.notify_tools import send_discord_notification

            summary = result.get("stats", {})
            message = (
                f"Feature '{feature_name}' completed!\n\n"
                f"Stats:\n"
                f"- Iterations: {summary.get('iterations', 0)}\n"
                f"- Tool calls: {summary.get('tool_calls_made', 0)}\n"
                f"- Duration: {summary.get('duration_seconds', 0):.1f}s\n"
                f"- Errors: {summary.get('errors', 0)}"
            )

            send_discord_notification(
                title="✅ Feature Implementation Complete",
                message=message,
                color=0x00ff00,
            )
        except Exception as e:
            logger.warning(f"Could not send completion notification: {e}")

    def _send_error_notification(self, feature_name: str, error: str):
        """Send notification that a proposal failed."""
        try:
            from agentfactory.tools.notify_tools import send_discord_notification

            send_discord_notification(
                title="❌ Feature Implementation Failed",
                message=f"Feature '{feature_name}' encountered an error:\n{error}",
                color=0xff0000,
            )
        except Exception as e:
            logger.warning(f"Could not send error notification: {e}")


def main():
    """CLI entry point for the worker."""
    parser = argparse.ArgumentParser(description="AgentFactory Background Worker")
    parser.add_argument(
        "--watch", action="store_true",
        help="Watch for approved proposals continuously"
    )
    parser.add_argument(
        "--poll-interval", type=int, default=5,
        help="Polling interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--server", default=None,
        help="Approval server URL (default: env AGENT_SERVER_URL or http://localhost:8000)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process pending proposals once and exit"
    )

    args = parser.parse_args()

    worker = AgentWorker(
        server_url=args.server,
        poll_interval=args.poll_interval,
    )

    if args.once:
        worker._process_pending_proposals()
        print("Worker completed single check.")
    else:
        worker.run()


if __name__ == "__main__":
    main()
