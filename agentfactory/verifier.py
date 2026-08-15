"""
Verifier — Context pruning for self-correction loops.

Key principle: NEVER include entire file contents in verification context.
Only extract failing lines and their immediate ±N context lines.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
import structlog
import re

logger = structlog.get_logger()


@dataclass
class AuditResult:
    """Result of a single audit/verification check."""
    name: str
    passed: bool
    message: str = ""
    file_path: Optional[str] = None
    line_number: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }


@dataclass
class VerificationReport:
    """Full verification report for a feature implementation."""
    feature_name: str
    branch_name: str = ""
    checks: List[AuditResult] = field(default_factory=list)
    _overall_passed: bool = True

    def __post_init__(self):
        self._overall_passed = True

    def add_check(self, check: AuditResult) -> None:
        """Add a check result to the report."""
        self.checks.append(check)
        if not check.passed:
            self._overall_passed = False

    @property
    def overall_passed(self) -> bool:
        """Recalculate overall pass status."""
        self._overall_passed = all(c.passed for c in self.checks) if self.checks else True
        return self._overall_passed

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "branch_name": self.branch_name,
            "overall_passed": self.overall_passed,
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class FailedCheck:
    """Result of a verification check that failed."""
    name: str
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    line_content: Optional[str] = None
    context_snippet: Optional[str] = None
    error_type: str = "verification_failed"


@dataclass
class VerificationResult:
    """Result of running all verification checks."""
    passed: bool = True
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[FailedCheck] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""

    @property
    def has_failures(self) -> bool:
        return len(self.failed_checks) > 0


class Verifier:
    """
    Verifier with strict context pruning.

    The get_pruned_context() method only extracts failing lines
    with ±N context lines — never full file contents.
    """

    def __init__(self, context_window: int = 5):
        self.context_window = context_window
        self._last_result: Optional[VerificationResult] = None

    async def verify_all(self, content: str) -> VerificationResult:
        """
        Run all verification checks on the given content.

        Args:
            content: The generated code/content to verify

        Returns:
            VerificationResult with all check results
        """
        result = VerificationResult()

        # Run syntax checks — capture failures
        syntax_passed, syntax_failed = await self._check_python_syntax(content)
        result.passed_checks.extend(syntax_passed)
        result.failed_checks.extend(syntax_failed)

        # Run pattern checks
        result.passed_checks.extend(await self._check_patterns(content))

        # Run security checks
        security_issues = await self._check_security(content)
        if security_issues:
            result.failed_checks.extend(security_issues)

        # Run placeholder checks
        placeholder_issues = await self._check_placeholders(content)
        if placeholder_issues:
            result.failed_checks.extend(placeholder_issues)

        result.passed = not result.has_failures
        result.summary = (
            f"Passed {len(result.passed_checks)} checks, "
            f"failed {len(result.failed_checks)} checks, "
            f"warnings {len(result.warnings)}"
        )

        self._last_result = result
        return result

    async def verify_file(self, file_path: str, content: str) -> VerificationResult:
        """
        Verify a specific file's content.

        Args:
            file_path: Path to the file (for reporting)
            content: File content to verify

        Returns:
            VerificationResult
        """
        result = VerificationResult()

        # Python syntax check for .py files
        if file_path.endswith(".py"):
            syntax_errors = await self._check_python_file_syntax(file_path, content)
            if syntax_errors:
                result.failed_checks.extend(syntax_errors)

        # Generic checks
        result.passed_checks.extend(await self._check_patterns(content))

        # Security checks
        security_issues = await self._check_security(content, file_path)
        if security_issues:
            result.failed_checks.extend(security_issues)

        # Placeholder checks
        placeholder_issues = await self._check_placeholders(content, file_path)
        if placeholder_issues:
            result.failed_checks.extend(placeholder_issues)

        result.passed = not result.has_failures
        result.summary = (
            f"File {file_path}: {len(result.passed_checks)} passed, "
            f"{len(result.failed_checks)} failed"
        )

        self._last_result = result
        return result

    def get_pruned_context(self) -> str:
        """
        Get strict pruned context for self-correction.

        ONLY includes:
        - Failing line numbers and their content
        - ±N context lines around each failure
        - Check names and error messages

        NEVER includes:
        - Full file contents
        - Irrelevant code sections
        - Complete function bodies (unless directly involved in failure)

        Returns:
            Pruned context string for self-correction
        """
        if not self._last_result or not self._last_result.failed_checks:
            return ""

        context_parts = []

        for check in self._last_result.failed_checks:
            context_parts.append(f"=== Check: {check.name} ===")
            context_parts.append(f"Error: {check.message}")
            context_parts.append(f"Type: {check.error_type}")

            if check.context_snippet:
                # STRICT: only the pruned snippet, never full file
                context_parts.append(f"Context:\n{check.context_snippet}")

        return "\n".join(context_parts)

    def get_failing_checks(self) -> List[FailedCheck]:
        """Return only the failing checks from the last verification."""
        if not self._last_result:
            return []
        return self._last_result.failed_checks

    # ============================================================
    # Internal Check Methods
    # ============================================================

    async def _check_python_syntax(self, content: str) -> tuple:
        """
        Check Python syntax validity.

        Returns:
            Tuple of (passed_check_names, failed_checks)
        """
        passed = []
        failed = []

        try:
            compile(content, "<string>", "exec")
            passed.append("python_syntax")
        except SyntaxError as e:
            # Record as a failed check with pruned context
            failed_check = FailedCheck(
                name="python_syntax",
                message=f"Syntax error at line {e.lineno}: {e.msg}",
                line_number=e.lineno,
                error_type="syntax_error",
            )
            # Get the specific failing line and context
            lines = content.split("\n")
            if e.lineno and 0 < e.lineno <= len(lines):
                start = max(0, e.lineno - self.context_window - 1)
                end = min(len(lines), e.lineno + self.context_window)
                context_lines = lines[start:end]
                snippet_parts = []
                for i, line in enumerate(context_lines, start=start + 1):
                    marker = ">>> " if i == e.lineno else "  "
                    snippet_parts.append(f"{marker}{i}: {line}")
                failed_check.context_snippet = "\n".join(snippet_parts)

            failed.append(failed_check)

        return passed, failed

    async def _check_python_file_syntax(self, file_path: str, content: str) -> List[FailedCheck]:
        """Check Python file syntax and return failed checks."""
        failed_checks = []

        try:
            compile(content, file_path, "exec")
        except SyntaxError as e:
            check = FailedCheck(
                name="python_syntax",
                message=f"Syntax error in {file_path} at line {e.lineno}: {e.msg}",
                file_path=file_path,
                line_number=e.lineno,
                error_type="syntax_error",
            )

            # Prune context to only the failing area
            lines = content.split("\n")
            if e.lineno and 0 < e.lineno <= len(lines):
                start = max(0, e.lineno - self.context_window - 1)
                end = min(len(lines), e.lineno + self.context_window)
                context_lines = lines[start:end]
                snippet_parts = []
                for i, line in enumerate(context_lines, start=start + 1):
                    marker = ">>> " if i == e.lineno else "  "
                    snippet_parts.append(f"{marker}{i}: {line}")
                check.context_snippet = "\n".join(snippet_parts)

            failed_checks.append(check)

        return failed_checks

    async def _check_patterns(self, content: str) -> List[str]:
        """Check for common patterns."""
        passed = []

        # Check for code blocks
        if "```python" in content or "```python\n" in content:
            passed.append("has_python_blocks")

        # Check for imports
        if re.search(r'^import |^from .+ import ', content, re.MULTILINE):
            passed.append("has_imports")

        # Check for functions
        if re.search(r'^def |^async def ', content, re.MULTILINE):
            passed.append("has_functions")

        return passed

    async def _check_security(self, content: str, file_path: Optional[str] = None) -> List[FailedCheck]:
        """Check for common security issues."""
        failed_checks = []

        # Check for dangerous eval
        if re.search(r'\beval\s*\(', content):
            line_num = self._find_line_number(content, "eval(")
            failed_checks.append(FailedCheck(
                name="security_eval",
                message="Use of eval() detected — potential security risk",
                file_path=file_path,
                line_number=line_num,
                error_type="security",
                context_snippet=self._get_context_snippet(content, line_num),
            ))

        # Check for dangerous exec
        if re.search(r'\bexec\s*\(', content) and "compile(" not in content:
            line_num = self._find_line_number(content, "exec(")
            failed_checks.append(FailedCheck(
                name="security_exec",
                message="Use of exec() detected — potential security risk",
                file_path=file_path,
                line_number=line_num,
                error_type="security",
                context_snippet=self._get_context_snippet(content, line_num),
            ))

        # Check for subprocess with shell=True
        if re.search(r'subprocess\..*\(.*shell\s*=\s*True', content):
            line_num = self._find_line_number(content, "shell=True")
            failed_checks.append(FailedCheck(
                name="security_shell_injection",
                message="subprocess with shell=True — potential injection risk",
                file_path=file_path,
                line_number=line_num,
                error_type="security",
                context_snippet=self._get_context_snippet(content, line_num),
            ))

        # Check for hardcoded passwords
        if re.search(r'password\s*=\s*["\'][^"\']{3,}["\']', content, re.IGNORECASE):
            line_num = self._find_line_number(content, "password=")
            failed_checks.append(FailedCheck(
                name="security_hardcoded_password",
                message="Potential hardcoded password detected",
                file_path=file_path,
                line_number=line_num,
                error_type="security",
                context_snippet=self._get_context_snippet(content, line_num),
            ))

        return failed_checks

    async def _check_placeholders(self, content: str, file_path: Optional[str] = None) -> List[FailedCheck]:
        """Check for placeholder content."""
        failed_checks = []

        placeholders = [
            ("TODO", "todo_marker"),
            ("FIXME", "fixme_marker"),
            ("HACK", "hack_marker"),
            ("PASS", "pass_statement"),
            ("[CUSTOM]", "custom_placeholder"),
            ("[IMPLEMENT]", "implement_placeholder"),
            ("[PLACEHOLDER]", "placeholder_marker"),
            ("NotImplemented", "not_implemented"),
            ("\"\"\"", "empty_docstring"),
        ]

        for marker, check_name in placeholders:
            matches = list(re.finditer(re.escape(marker), content))
            for match in matches:
                line_num = content[:match.start()].count("\n") + 1
                failed_checks.append(FailedCheck(
                    name=check_name,
                    message=f"Placeholder/temporary marker found: '{marker}'",
                    file_path=file_path,
                    line_number=line_num,
                    error_type="incomplete",
                    context_snippet=self._get_context_snippet(content, line_num),
                ))

        return failed_checks

    def _find_line_number(self, content: str, pattern: str) -> int:
        """Find the line number of the first occurrence of a pattern."""
        match = re.search(re.escape(pattern), content)
        if match:
            return content[:match.start()].count("\n") + 1
        return 0

    def _get_context_snippet(self, content: str, line_num: int) -> str:
        """
        Get a pruned context snippet around a specific line.

        STRICT: Only returns ±N lines, never the full file.
        """
        lines = content.split("\n")
        if not line_num or line_num < 1 or line_num > len(lines):
            return ""

        start = max(0, line_num - self.context_window - 1)
        end = min(len(lines), line_num + self.context_window)

        snippet_parts = []
        for i in range(start, end):
            marker = ">>> " if (i + 1) == line_num else "  "
            snippet_parts.append(f"{marker}{i + 1}: {lines[i]}")

        return "\n".join(snippet_parts)
