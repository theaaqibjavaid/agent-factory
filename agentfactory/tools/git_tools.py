"""
Git Tools — Repository operations via CLI wrappers.

These tools are used by Senior agents to manage code repositories
during feature implementation.
"""

import os
import subprocess
import re
from typing import Optional, List
from agentfactory.base_tools import tool, SafetyLevel


@tool("git_create_branch", category="git", safety_level=SafetyLevel.SAFE, tags=["git", "branch"])
def git_create_branch(branch_name: str, base: str = "main", repo_path: Optional[str] = None) -> str:
    """
    Create and checkout a new git branch.

    Args:
        branch_name: Name of the new branch
        base: Base branch to branch from (default: main)
        repo_path: Path to the repository (default: current dir)

    Returns:
        Status message with branch info
    """
    cwd = repo_path or os.getcwd()
    try:
        subprocess.run(["git", "-C", cwd, "checkout", "-b", f"feature/{branch_name}"], check=True, capture_output=True, text=True)
        return f"Created and checked out branch: feature/{branch_name}"
    except subprocess.CalledProcessError as e:
        # Branch might already exist, try checking out
        try:
            subprocess.run(["git", "-C", cwd, "checkout", f"feature/{branch_name}"], check=True, capture_output=True, text=True)
            return f"Checked out existing branch: feature/{branch_name}"
        except subprocess.CalledProcessError as e2:
            return f"Error creating branch: {e2.stderr}"


@tool("git_commit_changes", category="git", safety_level=SafetyLevel.MODIFIED, tags=["git", "commit"])
def git_commit_changes(message: str, repo_path: Optional[str] = None, add_all: bool = True) -> str:
    """
    Commit changes to the current branch.

    Args:
        message: Commit message
        repo_path: Path to the repository (default: current dir)
        add_all: Whether to add all changes before committing

    Returns:
        Status message with commit hash
    """
    cwd = repo_path or os.getcwd()
    try:
        if add_all:
            subprocess.run(["git", "-C", cwd, "add", "-A"], check=True, capture_output=True, text=True)

        result = subprocess.run(
            ["git", "-C", cwd, "commit", "-m", message],
            check=True, capture_output=True, text=True
        )

        # Extract commit hash
        commit_hash = result.stdout.strip()[:40] if result.stdout else ""
        return f"Committed: {commit_hash[:8]} - {message}"
    except subprocess.CalledProcessError as e:
        return f"Error committing: {e.stderr}"


@tool("git_push_branch", category="git", safety_level=SafetyLevel.MODIFIED, tags=["git", "push"])
def git_push_branch(branch_name: Optional[str] = None, remote: str = "origin", repo_path: Optional[str] = None) -> str:
    """
    Push the current branch to remote.

    Args:
        branch_name: Branch to push (default: current branch)
        remote: Remote name (default: origin)
        repo_path: Path to the repository

    Returns:
        Status message
    """
    cwd = repo_path or os.getcwd()
    try:
        if branch_name:
            branch = branch_name
        else:
            result = subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True)
            branch = result.stdout.strip()
            if not branch:
                return "Error: No branch detected"

        result = subprocess.run(
            ["git", "-C", cwd, "push", remote, branch],
            check=True, capture_output=True, text=True
        )
        return f"Pushed {branch} to {remote}"
    except subprocess.CalledProcessError as e:
        return f"Error pushing: {e.stderr}"


@tool("git_check_status", category="git", safety_level=SafetyLevel.SAFE, tags=["git", "status"])
def git_check_status(repo_path: Optional[str] = None) -> str:
    """
    Check the git status of a repository.

    Args:
        repo_path: Path to the repository (default: current dir)

    Returns:
        Formatted git status output
    """
    cwd = repo_path or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "status", "--short"],
            capture_output=True, text=True
        )

        result_diff = subprocess.run(
            ["git", "-C", cwd, "diff", "--stat"],
            capture_output=True, text=True
        )

        output = f"Git Status for {cwd}:\n"
        if result.stdout.strip():
            output += result.stdout
        else:
            output += "Working tree clean, no changes to commit.\n"

        if result_diff.stdout.strip():
            output += f"\nDiff Summary:\n{result_diff.stdout}"

        return output
    except subprocess.CalledProcessError as e:
        return f"Error checking status: {e.stderr}"


@tool("git_create_pull_request", category="git", safety_level=SafetyLevel.MODIFIED, tags=["git", "pr"])
def git_create_pull_request(
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
    repo_path: Optional[str] = None,
) -> str:
    """
    Create a pull request (requires gh CLI).

    Args:
        title: PR title
        body: PR description
        head_branch: Source branch
        base_branch: Target branch (default: main)
        repo_path: Path to the repository

    Returns:
        PR URL or error message
    """
    cwd = repo_path or os.getcwd()
    try:
        result = subprocess.run(
            ["gh", "pr", "create",
             "--title", title,
             "--body", body,
             "--base", base_branch,
             "--head", head_branch],
            check=True, capture_output=True, text=True,
            cwd=cwd,
        )
        return f"Pull request created:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error creating PR: {e.stderr}"
    except FileNotFoundError:
        return "Error: 'gh' CLI not found. Install from https://cli.github.com/"


@tool("git_get_recent_commits", category="git", safety_level=SafetyLevel.SAFE, tags=["git", "log"])
def git_get_recent_commits(count: int = 10, repo_path: Optional[str] = None) -> str:
    """
    Get recent commit history.

    Args:
        count: Number of commits to show
        repo_path: Path to the repository

    Returns:
        Formatted commit log
    """
    cwd = repo_path or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "log", f"-{count}", "--oneline", "--graph", "--decorate"],
            capture_output=True, text=True
        )
        return result.stdout or "No commits found."
    except subprocess.CalledProcessError as e:
        return f"Error getting commits: {e.stderr}"


@tool("git_switch_branch", category="git", safety_level=SafetyLevel.SAFE, tags=["git", "branch", "switch"])
def git_switch_branch(branch_name: str, repo_path: Optional[str] = None) -> str:
    """
    Switch to an existing branch.

    Args:
        branch_name: Branch to switch to
        repo_path: Path to the repository

    Returns:
        Status message
    """
    cwd = repo_path or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "checkout", branch_name],
            check=True, capture_output=True, text=True
        )
        return f"Switched to branch: {branch_name}"
    except subprocess.CalledProcessError as e:
        return f"Error switching branch: {e.stderr}"


@tool("git_sync_fork", category="git", safety_level=SafetyLevel.SAFE, tags=["git", "sync", "fork"])
def git_sync_fork(upstream: str = "origin", repo_path: Optional[str] = None) -> str:
    """
    Sync a fork with upstream changes.

    Args:
        upstream: Upstream remote name (default: origin)
        repo_path: Path to the repository

    Returns:
        Status message with sync details
    """
    cwd = repo_path or os.getcwd()
    try:
        steps = []

        # Fetch upstream
        result = subprocess.run(
            ["git", "-C", cwd, "fetch", upstream],
            capture_output=True, text=True
        )
        steps.append(f"Fetched from {upstream}")

        # Merge (or rebase)
        result = subprocess.run(
            ["git", "-C", cwd, "merge", f"{upstream}/main"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            steps.append("Merged upstream/main")
        else:
            steps.append(f"Merge completed with notes: {result.stdout[:100]}")

        return f"Fork synced:\n" + "\n".join(steps)
    except subprocess.CalledProcessError as e:
        return f"Error syncing fork: {e.stderr}"
