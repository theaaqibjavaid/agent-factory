# Tools

AgentFactory ships with 28 built-in tools across 4 categories. You can also write custom tools using the `@tool` decorator.

## Built-in Tools

### Git Tools (`tools/git_tools.py`)

| Tool | Description | Safety |
|------|-------------|--------|
| `git_create_branch` | Create a new git branch | MODIFIED |
| `git_commit_changes` | Commit changes with a message | MODIFIED |
| `git_push_branch` | Push branch to remote | MODIFIED |
| `git_check_status` | Check working tree status | SAFE |
| `git_create_pull_request` | Create a PR via GitHub CLI | MODIFIED |
| `git_get_recent_commits` | Get recent commit history | SAFE |
| `git_switch_branch` | Switch to a different branch | MODIFIED |
| `git_sync_fork` | Sync fork with upstream | MODIFIED |

### Web Tools (`tools/web_tools.py`)

| Tool | Description | Safety |
|------|-------------|--------|
| `web_search` | Search the web (Tavily) | SAFE |
| `web_fetch` | Fetch a webpage's content | SAFE |
| `web_scrape_links` | Extract links from a URL | SAFE |

### File Tools (`tools/file_tools.py`)

| Tool | Description | Safety |
|------|-------------|--------|
| `read_text_file` | Read a file's contents | SAFE |
| `write_text_file` | Write content to a file | MODIFIED |
| `list_directory_contents` | List files in a directory | SAFE |
| `delete_file` | Delete a file | DESTRUCTIVE |
| `create_directory` | Create a directory | MODIFIED |
| `search_files_by_pattern` | Search files by glob pattern | SAFE |
| `count_lines_in_file` | Count lines in a file | SAFE |

### Notification Tools (`tools/notify_tools.py`)

| Tool | Description | Safety |
|------|-------------|--------|
| `send_discord_notification` | Send a Discord webhook message | MODIFIED |
| `send_gmail_notification` | Send an email via Gmail | MODIFIED |
| `send_webhook_notification` | Send a POST to a webhook URL | MODIFIED |

## Legacy Alias Compatibility

For backward compatibility, the following aliases are registered automatically:

| Alias | Maps to |
|-------|---------|
| `analyze_codebase_files` | `list_directory_contents` |
| `research_web_for_upgrades` | `web_search` |
| `fetch_webpage_content` | `web_fetch` |
| `read_file_lines` | `read_text_file` |
| `write_file_to_repo` | `write_text_file` |
| `git_add_commit_push` | `git_commit_changes` |
| `create_feature_branch` | `git_create_branch` |

## Writing Custom Tools

Use the `@tool` decorator:

```python
from agentfactory.base_tools import tool, SafetyLevel

@tool(
    name="parse_pdf",
    description="Parse a PDF file and extract text",
    category="document",
    cost_per_call_usd=0.01,
    safety_level=SafetyLevel.SAFE,
    tags=["pdf", "parsing"],
)
def parse_pdf(file_path: str) -> str:
    """Parse a PDF file and return extracted text."""
    # Your implementation
    return extracted_text
```

### Decorator Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | function name | Tool name |
| `description` | str | docstring | Tool description |
| `category` | str | `"generic"` | Category for organization |
| `cost_per_call_usd` | float | `0.0` | USD cost per call |
| `safety_level` | SafetyLevel | `SAFE` | Risk classification |
| `tags` | list[str] | `[]` | Tags for filtering |

### Automatic Registration

Importing `agentfactory.tools` auto-registers all built-in tools in the global registry. The registration is **idempotent** — re-importing won't create duplicates.

### Using Tools

```python
from agentfactory.base_tools import get_tool, list_tools, to_langchain_tools

# Get a tool
tool_def = get_tool("web_search")
result = tool_def.func(query="latest AI news")

# List all tools
print(list_tools())

# Convert to LangChain tools
lc_tools = to_langchain_tools(["web_search", "read_text_file"])
```
