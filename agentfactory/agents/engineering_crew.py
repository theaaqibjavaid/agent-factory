"""
Engineering Crew — Tiered multi-agent orchestrator (Reference Implementation).

Implements a 3-tier hierarchical team:
1. Senior Lead Architect (Supervisor) — researches, plans, proposes
2. Junior Feature Engineer (Worker) — writes code on feature branches
3. QA Security Auditor (Validator) — runs tests, catches failures

NOTE: This is a reference implementation. It demonstrates the tiered team
pattern using AgentFactory's core primitives. For production use, extend
this class with your own verification logic, repo integration, and error handling.

This module defines the coordination logic between agents.
"""

import os
import json
import time
import structlog
from typing import Dict, Any, List, Optional

from agentfactory.base_agent import AgentConfig, AgentFactory, RunnableAgent
from agentfactory.verifier import Verifier, VerificationReport
from agentfactory.llm_manager import FailoverLLMManager
from agentfactory.agents.config_loader import load_crew_config, DEFAULT_REPO_PATHS as REPO_PATHS

logger = structlog.get_logger()


class TieredEngineeringTeam:
    """
    Multi-agent engineering team with strict role isolation.

    Communication flow:
    Senior Architect → proposes plan via FastAPI gate →
    Human approves → Worker executes → QA validates →
    Worker self-corrects (max 2 loops) or escalates back to gate
    """

    def __init__(self, configs: Optional[Dict[str, AgentConfig]] = None, yaml_path: Optional[str] = None):
        if configs is None:
            yaml_path = yaml_path or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "engineer_crew.yaml",
            )
            configs = load_crew_config(yaml_path)

        self.configs = configs
        self.verifier = Verifier()  # Uses default context window

        # Shared tool registry
        from agentfactory.base_tools import ToolRegistry
        self._registry = ToolRegistry()

        # Instantiate agents
        self.senior_architect = self._instantiate_agent(configs.get("Senior_Lead_Architect"))
        self.junior_engineer = self._instantiate_agent(configs.get("Junior_Feature_Engineer"))
        self.qa_auditor = self._instantiate_agent(configs.get("QA_Security_Auditor"))

        logger.info(
            "Engineering team initialized",
            senior=self.senior_architect.name if self.senior_architect else None,
            junior=self.junior_engineer.name if self.junior_engineer else None,
            qa=self.qa_auditor.name if self.qa_auditor else None,
        )

    def _instantiate_agent(self, config: Optional[AgentConfig]) -> Optional[RunnableAgent]:
        """Instantiate a RunnableAgent from config."""
        if config is None:
            return None

        # Create persona from config
        from agentfactory.base_agent import AgentPersona

        persona = AgentPersona(
            rank=config.rank,
            responsibilities=[config.role_description] if config.role_description else [],
            system_instructions=config.system_instructions,
            model_preferences=config.model_preference,
            max_budget_usd_per_day=config.max_budget_usd_per_day,
            allow_delegation=config.allow_delegation,
            max_iterations=20,
        )

        llm_manager = FailoverLLMManager(
            model_preferences=config.model_preference,
            daily_budget_usd=config.max_budget_usd_per_day,
        )

        return RunnableAgent(
            persona=persona,
            tool_registry=self._get_shared_registry(),
            llm_manager=llm_manager,
        )

    def process_request(self, feature_request: str) -> Dict[str, Any]:
        """
        Full pipeline: Senior plans → propose → wait for approval →
        Junior executes → QA validates → return results.

        Args:
            feature_request: Natural language description of the feature

        Returns:
            Dict with plan, blueprint, and execution status
        """
        # Phase 1: Senior Architect analyzes and creates blueprint
        plan = self._run_senior_architect(feature_request)
        blueprint = self._parse_blueprint(plan)

        # Phase 2: Register proposal (human must approve)
        proposal_id = self._register_proposal(feature_request, plan, blueprint)

        # Phase 3: Execution happens in the background worker when approved
        return {
            "proposal_id": proposal_id,
            "plan": plan,
            "blueprint": blueprint,
            "status": "awaiting_approval",
            "instructions": "Wait for human approval via FastAPI server. Worker will execute automatically.",
        }

    def _get_shared_registry(self):
        """Get the shared tool registry."""
        return self._registry

    def _run_senior_architect(self, request: str) -> str:
        """Run the Senior Architect to produce a plan."""
        if self.senior_architect is None:
            return "Senior Architect not initialized"

        prompt = f"""
You are the Senior Lead Architect. Analyze this feature request:

{request}

Your task:
1. Research web trends for relevant tech stack improvements (FastAPI, React, Admin frameworks)
2. Read the codebase structure for backend, frontend, and admin repos
3. Produce a structured JSON blueprint with:
   - feature_name
   - repo_updates: {{"backend": {{"path": "...", "content": "..."}}, "frontend": {{"path": "...", "content": "..."}}, "admin_panel": {{"path": "...", "content": "..."}}}}
   - test_expectations: {{}}
   - migration_notes: "..."

Return ONLY valid JSON, no extra text.
        """

        import asyncio

        async def _run():
            response = await self.senior_architect.think(prompt)
            return response

        response = asyncio.run(_run())

        # Extract JSON from response
        try:
            # Find JSON in the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return response[start:end]
            return response
        except Exception:
            return response

    def _parse_blueprint(self, plan: str) -> Dict[str, Any]:
        """Parse the JSON blueprint from the Senior Architect's response."""
        try:
            start = plan.find("{")
            end = plan.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(plan[start:end])
        except json.JSONDecodeError:
            pass

        # Fallback: minimal blueprint
        return {
            "feature_name": "unnamed",
            "repo_updates": {},
            "test_expectations": {},
            "migration_notes": "No structured plan parsed",
        }

    def _register_proposal(self, feature_name: str, plan: str, blueprint: Dict[str, Any]) -> str:
        """Register the proposal with the FastAPI server."""
        import requests

        server_url = os.getenv("AGENT_SERVER_URL", "http://localhost:8000")
        proposal_id = f"prop-{int(time.time())}"

        try:
            requests.post(
                f"{server_url}/api/agent/propose",
                json={
                    "feature_name": feature_name,
                    "implementation_plan": plan,
                    "blueprint": blueprint,
                },
                timeout=10,
            )
        except requests.exceptions.ConnectionError:
            logger.warning("FastAPI server not running — proposal not registered. Start with: uvicorn app.approval_server:app --port 8000")

        return proposal_id

    async def _verify_content(self, file_path: str, file_content: str):
        """Verify file content and return VerificationResult."""
        return await self.verifier.verify_file(file_path, file_content)

    def execute_approved_feature(
        self,
        feature_name: str,
        blueprint: Dict[str, Any],
        extra_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an approved feature across all repos.

        This is called by the worker when APPROVED status is detected.
        """
        branch_name = f"feature/{feature_name.lower().replace(' ', '-')}"
        updates = blueprint.get("repo_updates", {})

        results = {}

        # Step 1: Junior Engineer writes code
        for repo_key, update in updates.items():
            repo_path = REPO_PATHS.get(repo_key)
            if not repo_path:
                results[repo_key] = {"status": "error", "error": "Repository path not configured"}
                continue

            # Create branch
            success = self._create_branch(repo_path, branch_name)
            if not success:
                results[repo_key] = {"status": "error", "error": "Branch creation failed"}
                continue

            # Write file
            file_path = update.get("path", "")
            content = update.get("content", "")
            full_path = os.path.join(repo_path, file_path)

            try:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

                # Commit and push
                subprocess.run(["git", "-C", repo_path, "add", file_path], check=True)
                subprocess.run(
                    ["git", "-C", repo_path, "commit", "-m", f"feat(agent): {feature_name}"],
                    check=True,
                )
                subprocess.run(["git", "-C", repo_path, "push", "origin", branch_name], check=True)
                results[repo_key] = {"status": "success", "file": file_path}
            except Exception as e:
                results[repo_key] = {"status": "error", "error": str(e)}

        # Step 2: QA Auditor runs verification
        qa_results = {}
        for repo_key in updates:
            # Use verifier to check the written content
            import asyncio

            file_path = updates[repo_key].get("path", "")
            file_content = updates[repo_key].get("content", "")
            verification = asyncio.run(self._verify_content(file_path, file_content))

            report = VerificationReport(
                feature_name=feature_name,
                branch_name=branch_name,
            )
            # Convert verification result to report format
            from agentfactory.verifier import AuditResult
            for check_name in verification.passed_checks:
                report.add_check(AuditResult(
                    name=check_name,
                    passed=True,
                    message="Check passed",
                    file_path=file_path,
                ))
            for failed in verification.failed_checks:
                report.add_check(AuditResult(
                    name=failed.name,
                    passed=False,
                    message=failed.message,
                    file_path=file_path,
                    line_number=failed.line_number,
                ))

            qa_results[repo_key] = report.to_dict()

            # If QA fails, attempt self-correction (max 2 loops)
            if not report.overall_passed:
                corrected = self._attempt_self_correction(
                    repo_key, feature_name, branch_name, report, updates[repo_key]
                )
                if corrected:
                    # Re-verify the corrected content
                    repo_path = REPO_PATHS.get(repo_key, "")
                    corrected_path = os.path.join(repo_path, updates[repo_key].get("path", ""))
                    try:
                        with open(corrected_path, "r", encoding="utf-8") as f:
                            corrected_content = f.read()
                        verification = asyncio.run(self._verify_content(corrected_path, corrected_content))

                        report = VerificationReport(feature_name=feature_name, branch_name=branch_name)
                        from agentfactory.verifier import AuditResult
                        for check_name in verification.passed_checks:
                            report.add_check(AuditResult(name=check_name, passed=True, message="Check passed", file_path=corrected_path))
                        for failed in verification.failed_checks:
                            report.add_check(AuditResult(name=failed.name, passed=False, message=failed.message, file_path=corrected_path, line_number=failed.line_number))
                    except Exception:
                        pass
                    qa_results[repo_key] = report.to_dict()

        results["verification"] = qa_results
        return results

    def _create_branch(self, repo_path: str, branch_name: str) -> bool:
        """Create a feature branch (never main)."""
        import subprocess

        protected = {"main", "master", "production", "prod"}
        if branch_name in protected:
            logger.error(f"Constitutional violation: Cannot create branch '{branch_name}'")
            return False

        try:
            # Check if branch exists
            result = subprocess.run(
                ["git", "-C", repo_path, "branch", "--list", branch_name],
                capture_output=True, text=True, check=True,
            )
            if branch_name in result.stdout:
                subprocess.run(["git", "-C", repo_path, "checkout", branch_name], check=True)
            else:
                subprocess.run(["git", "-C", repo_path, "checkout", "-b", branch_name], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Branch creation failed: {e}")
            return False

    def _attempt_self_correction(
        self,
        repo_key: str,
        feature_name: str,
        branch_name: str,
        report: VerificationReport,
        update: Dict[str, Any],
    ) -> bool:
        """Attempt to fix a failed verification (max 2 loops)."""
        loop_count = getattr(self, "_correction_loop_count", {}).get(repo_key, 0)
        if loop_count >= 2:
            logger.warning(f"Max self-correction loops reached for {repo_key}")
            return False

        self._correction_loop_count = getattr(self, "_correction_loop_count", {})
        self._correction_loop_count[repo_key] = loop_count + 1

        # Extract error details from report
        failed_checks = [c for c in report.checks if not c.passed]
        error_messages = "\n".join(f"- {c.name}: {c.message}" for c in failed_checks)

        prompt = f"""
The QA auditor found the following issues in the {repo_key} repository:

{error_messages}

Fix these issues by modifying the file at:
- Path: {update.get('path', '')}
- Current content needs to be corrected based on the errors above.

Rewrite the file content to address all issues. Return the full corrected file content only.
        """

        try:
            import asyncio

            async def _run_correction():
                response = await self.junior_engineer.think(prompt)
                return response

            response = asyncio.run(_run_correction())
            # Write corrected content
            repo_path = REPO_PATHS.get(repo_key, "")
            file_path = os.path.join(repo_path, update.get("path", ""))

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(response)

            # Re-commit
            import subprocess
            subprocess.run(["git", "-C", repo_path, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repo_path, "commit", "-m", f"fix(agent): {feature_name} - corrected QA issues"],
                check=True,
            )
            subprocess.run(["git", "-C", repo_path, "push", "origin", branch_name], check=True)

            logger.info(f"Self-correction applied for {repo_key}")
            return True
        except Exception as e:
            logger.error(f"Self-correction failed for {repo_key}: {e}")
            return False
