#!/usr/bin/env python3
"""
GitHub CLI helper for AgentFactory.

A lightweight command-line tool for GitHub operations using the GitHub REST API.
No external `gh` CLI dependency required — uses urllib + GITHUB_TOKEN.

Usage:
    python scripts/gh-cli.py repo-create [--private] [--description ""]
    python scripts/gh-cli.py repo-push [--branch main]
    python scripts/gh-cli.py repo-status
    python scripts/gh-cli.py pr-create [--title] [--base main]

Requires: GITHUB_TOKEN or GH_TOKEN environment variable set.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error


def get_token() -> str:
    """Get GitHub token from environment."""
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        print("ERROR: Set GH_TOKEN or GITHUB_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)
    return token


def api_call(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a GitHub API call."""
    token = get_token()
    url = f"https://api.github.com{endpoint}"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "agentfactory-gh-cli",
    }

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode()
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"GitHub API error ({e.code}): {err}", file=sys.stderr)
        sys.exit(1)


def get_owner_repo() -> str:
    """Get owner/repo from git remote."""
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        print("ERROR: No git remote 'origin' configured", file=sys.stderr)
        sys.exit(1)

    # Parse: git@github.com:owner/repo.git or https://github.com/owner/repo.git
    parts = remote.replace(".git", "").replace(":", "/")
    if "github.com/" in parts:
        parts = parts.split("github.com/")[-1]
    return parts.strip("/")


def cmd_repo_create(args):
    """Create a new GitHub repository."""
    name = args.name or os.path.basename(os.getcwd())

    data = {
        "name": name,
        "description": args.description or "AgentFactory universal AI agent template",
        "private": args.private,
        "auto_init": False,
    }

    result = api_call("POST", "/user/repos", data)
    owner = result.get("owner", {}).get("login", "unknown")

    print(f"Created repository: {owner}/{name}")
    print(f"  URL: {result.get('html_url', 'https://github.com/' + owner + '/' + name)}")

    # Set remote
    remote_url = f"git@github.com:{owner}/{name}.git"
    subprocess.run(["git", "remote", "add", "origin", remote_url], check=False)


def cmd_repo_push(args):
    """Push to GitHub."""
    branch = args.branch or "main"
    subprocess.run(["git", "branch", "-m", branch], check=False)

    print(f"Pushing to origin/{branch}...")
    result = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"Pushed to origin/{branch}")
    else:
        print(f"Push failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def cmd_repo_status(args):
    """Show GitHub repository status."""
    owner_repo = get_owner_repo()
    result = api_call("GET", f"/repos/{owner_repo}")

    print(f"Repository: {owner_repo}")
    print(f"  Visibility: {'private' if result.get('private') else 'public'}")
    print(f"  Default branch: {result.get('default_branch')}")
    print(f"  Stars: {result.get('stargazers_count', 0)}")
    print(f"  Forks: {result.get('forks_count', 0)}")
    print(f"  Open issues: {result.get('open_issues_count', 0)}")
    print(f"  URL: {result.get('html_url', '')}")

    commits = api_call("GET", f"/repos/{owner_repo}/commits?per_page=5")
    print(f"\nRecent commits:")
    for c in commits:
        msg = c["commit"]["message"].split("\n")[0]
        print(f"  {c['sha'][:8]} {msg}")


def cmd_pr_create(args):
    """Create a pull request."""
    owner_repo = get_owner_repo()
    head = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()

    data = {
        "title": args.title or f"Feature: {head}",
        "head": head,
        "base": args.base or "main",
        "body": args.body or "Automated PR from AgentFactory",
    }

    result = api_call("POST", f"/repos/{owner_repo}/pulls", data)
    print(f"Created PR #{result.get('number')}: {result.get('html_url')}")


def main():
    parser = argparse.ArgumentParser(
        description="AgentFactory GitHub CLI — lightweight GitHub operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # repo-create
    p = subparsers.add_parser("repo-create", help="Create a new GitHub repo")
    p.add_argument("--name", help="Repository name (default: current dir name)")
    p.add_argument("--private", action="store_true", help="Private repository")
    p.add_argument("--description", help="Repository description")
    p.set_defaults(func=cmd_repo_create)

    # repo-push
    p = subparsers.add_parser("repo-push", help="Push to GitHub")
    p.add_argument("--branch", default="main", help="Branch to push (default: main)")
    p.set_defaults(func=cmd_repo_push)

    # repo-status
    p = subparsers.add_parser("repo-status", help="Show repository status")
    p.set_defaults(func=cmd_repo_status)

    # pr-create
    p = subparsers.add_parser("pr-create", help="Create a pull request")
    p.add_argument("--title", help="PR title")
    p.add_argument("--base", default="main", help="Base branch")
    p.add_argument("--body", help="PR body/description")
    p.set_defaults(func=cmd_pr_create)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
