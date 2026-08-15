"""
Tools subpackage — Built-in tools for AgentFactory agents.

Importing this module auto-registers all tools in the global registry.
"""

# Re-export tools with their canonical names
from agentfactory.tools.git_tools import (
    git_create_branch,
    git_commit_changes,
    git_push_branch,
    git_check_status,
    git_create_pull_request,
    git_get_recent_commits,
    git_switch_branch,
    git_sync_fork,
)

from agentfactory.tools.web_tools import (
    web_search,
    web_fetch,
    web_scrape_links,
)

from agentfactory.tools.file_tools import (
    write_text_file,
    read_text_file,
    list_directory_contents,
    delete_file,
    create_directory,
    search_files_by_pattern,
    count_lines_in_file,
)

from agentfactory.tools.notify_tools import (
    send_discord_notification,
    send_gmail_notification,
    send_webhook_notification,
)

# Legacy alias names for backward compatibility
# Create proper ToolDef copies with alias names
from agentfactory.base_tools import _TOOL_REGISTRY, ToolDef

for _alias, _target in [
    ("analyze_codebase_files", "list_directory_contents"),
    ("research_web_for_upgrades", "web_search"),
    ("fetch_webpage_content", "web_fetch"),
    ("read_file_lines", "read_text_file"),
    ("write_file_to_repo", "write_text_file"),
    ("git_add_commit_push", "git_commit_changes"),
    ("create_feature_branch", "git_create_branch"),
]:
    if _target in _TOOL_REGISTRY and _alias not in _TOOL_REGISTRY:
        _orig = _TOOL_REGISTRY[_target]
        _alias_def = ToolDef(
            name=_alias,
            func=_orig.func,
            description=_orig.description,
            args_schema=_orig.args_schema,
            category=_orig.category,
            cost_per_call_usd=_orig.cost_per_call_usd,
            safety_level=_orig.safety_level,
            tags=_orig.tags,
        )
        _TOOL_REGISTRY[_alias] = _alias_def

# Convenience: make alias functions available as attributes
research_web_for_upgrades = web_search
analyze_codebase_files = list_directory_contents
fetch_webpage_content = web_fetch
read_file_lines = read_text_file
write_file_to_repo = write_text_file
git_add_commit_push = git_commit_changes
create_feature_branch = git_create_branch

__all__ = [
    # Git tools
    "git_create_branch",
    "git_commit_changes",
    "git_push_branch",
    "git_check_status",
    "git_create_pull_request",
    "git_get_recent_commits",
    "git_switch_branch",
    "git_sync_fork",

    # Web tools
    "web_search",
    "web_fetch",
    "web_scrape_links",

    # Legacy aliases
    "research_web_for_upgrades",
    "analyze_codebase_files",
    "fetch_webpage_content",
    "read_file_lines",
    "write_file_to_repo",
    "git_add_commit_push",
    "create_feature_branch",

    # File tools
    "write_text_file",
    "read_text_file",
    "list_directory_contents",
    "delete_file",
    "create_directory",
    "search_files_by_pattern",
    "count_lines_in_file",

    # Notification tools
    "send_discord_notification",
    "send_gmail_notification",
    "send_webhook_notification",
]
