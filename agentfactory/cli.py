"""
AgentFactory CLI — Developer tooling command line interface.

Commands:
    init      - Configure .env, check directory mappings, validate setup
    run       - Start FastAPI server + background worker
    create-agent  - Generate a new agent config from template
    list-tools  - List all registered tools
    status    - Check current approval server status
"""

import os
import sys
import click
import subprocess
import structlog
from pathlib import Path

logger = structlog.get_logger()

# Fix encoding for Windows (emoji support)
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer) if hasattr(sys.stdout, "buffer") else sys.stdout


# ============================================================
# CLI Entry Point
# ============================================================

@click.group()
@click.version_option(version="1.0.0", prog_name="agentfactory")
def cli():
    """AgentFactory — Universal AI Agent Template System"""
    pass


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing .env file")
def init(force: bool):
    """
    Initialize AgentFactory configuration.

    Creates .env file with required variables,
    checks directory mappings, and validates setup.
    """
    click.echo("🚀 AgentFactory Initialization\n")

    # Check for existing .env
    env_path = Path(".env")
    if env_path.exists() and not force:
        click.echo("⚠️  .env file already exists. Use --force to overwrite.")
        return

    # Create .env from template
    env_content = _create_env_template()
    with open(env_path, "w") as f:
        f.write(env_content)
    click.echo(f"✓ Created .env file")

    # Create mcp.json
    config_path = Path("mcp.json")
    if not config_path.exists():
        from agentfactory.mcp_integration import create_mcp_config_template
        create_mcp_config_template(str(config_path))
        click.echo("✓ Created mcp.json (MCP server configuration)")

    # Create example agent configs
    examples_dir = Path("agents/examples")
    examples_dir.mkdir(parents=True, exist_ok=True)
    from agentfactory.agents.config_loader import create_default_configs
    written = create_default_configs(str(examples_dir))
    click.echo(f"✓ Created {len(written)} example agent configs in {examples_dir}")

    # Validate setup
    click.echo("\n🔍 Validating setup...")

    # Check Python
    py_version = sys.version.split()[0]
    click.echo(f"  Python: {py_version} ✓")

    # Check dependencies
    required_packages = ["langchain", "fastapi", "uvicorn", "yaml", "structlog"]
    missing = []
    for pkg in required_packages:
        try:
            mod_name = "yaml" if pkg == "yaml" else pkg
            __import__(mod_name)
            click.echo(f"  {pkg}: ✓")
        except ImportError:
            missing.append(pkg)
            click.echo(f"  {pkg}: ✗ MISSING")

    if missing:
        click.echo(f"\n⚠️  Missing packages: {', '.join(missing)}")
        click.echo("  Install with: pip install -r requirements.txt")
    else:
        click.echo("\n✅ Setup validation complete! All dependencies found.")

    # Check for API keys
    click.echo("\n🔐 API Key Status:")
    api_keys = {
        "GEMINI_API_KEY": "Google Gemini (free tier)",
        "OPENAI_API_KEY": "OpenAI (paid fallback)",
        "ANTHROPIC_API_KEY": "Anthropic (premium fallback)",
    }
    for env_var, description in api_keys.items():
        value = os.getenv(env_var)
        if value:
            masked = value[:8] + "..." if len(value) > 8 else "***"
            click.echo(f"  {env_var} ({description}): ✓ {masked}")
        else:
            click.echo(f"  {env_var} ({description}): not set")

    # Check repo paths
    click.echo("\n📁 Repository Paths:")
    for path_env in ["BACKEND_PATH", "FRONTEND_PATH", "ADMIN_PATH"]:
        value = os.getenv(path_env, "")
        if value and os.path.exists(value):
            click.echo(f"  {path_env}: ✓ {value}")
        else:
            click.echo(f"  {path_env}: ✗ not set or doesn't exist")

    click.echo("\n📝 Next steps:")
    click.echo("  1. Edit .env file with your API keys and repo paths")
    click.echo("  2. Run: agentfactory run")
    click.echo("  3. Or run separately:")
    click.echo("     uvicorn agentfactory.app.approval_server:app --port 8000")
    click.echo("     python -m agentfactory.agents.worker --watch")


@cli.command()
@click.option("--port", default=8000, help="Port for the FastAPI server (default: 8000)")
@click.option("--reload", is_flag=True, default=True, help="Enable auto-reload")
@click.option("--worker-only", is_flag=True, help="Start only the background worker")
@click.option("--server-only", is_flag=True, help="Start only the FastAPI server")
def run(port: int, reload: bool, worker_only: bool, server_only: bool):
    """
    Start the FastAPI control plane and background polling worker.

    Runs both simultaneously in separate processes by default.
    """
    if server_only and worker_only:
        click.echo("Error: Cannot specify both --server-only and --worker-only")
        sys.exit(1)

    processes = []

    if not worker_only:
        # Start FastAPI server
        click.echo(f"🚀 Starting FastAPI approval server on port {port}...")
        server_proc = subprocess.Popen([
            sys.executable, "-m", "uvicorn",
            "agentfactory.app.approval_server:app",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--reload" if reload else "--no-reload",
        ])
        processes.append(server_proc)
        click.echo(f"   ✓ Server started (PID: {server_proc.pid})")
        click.echo(f"   📋 API docs: http://localhost:{port}/docs")

    if not server_only:
        # Start background worker
        click.echo("🔄 Starting background worker...")
        worker_proc = subprocess.Popen([
            sys.executable, "-m", "agentfactory.agents.worker",
            "--watch",
            "--poll-interval", "5",
        ])
        processes.append(worker_proc)
        click.echo(f"   ✓ Worker started (PID: {worker_proc.pid})")

    click.echo("\n🎯 AgentFactory is running. Press Ctrl+C to stop.")

    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        click.echo("\n🛑 Shutting down...")
        for proc in processes:
            proc.terminate()
            proc.wait()


@cli.command()
@click.argument("agent_name")
@click.option("--rank", default="Junior", help="Agent rank (Senior, Junior, QA, Manager)")
@click.option("--output", "-o", help="Output file path")
def create_agent(agent_name: str, rank: str, output: str):
    """
    Create a new agent configuration from template.

    Example:
        agentfactory create-agent my_code_reviewer --rank QA
    """
    import yaml

    config = {
        "agent_name": agent_name,
        "rank": rank,
        "model_preference": {
            "Senior": ["gemini-2.5-flash", "gpt-4o"],
            "Junior": ["gemini-2.5-flash", "gpt-4o-mini"],
            "QA": ["gpt-4o-mini"],
            "Manager": ["gpt-4o", "claude-3-5-sonnet-20241022"],
        }.get(rank, ["gemini-2.5-flash"]),
        "responsibilities": f"[CUSTOM] Describe the {agent_name} agent's responsibility here",
        "tools": [],
        "system_instructions": f"[CUSTOM] Write system instructions for the {agent_name} agent here.",
        "constitutional_boundaries": {
            "max_budget_usd_per_day": 5.00,
        },
        "allow_delegation": rank in ["Senior", "Manager"],
    }

    output_path = output or f"agents/{agent_name.lower().replace(' ', '_')}.yaml"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    click.echo(f"✅ Created agent config: {output_path}")
    click.echo(f"   Name: {agent_name}")
    click.echo(f"   Rank: {rank}")
    click.echo(f"\n📝 Edit {output_path} to customize:")
    click.echo(f"   - responsibilities: what this agent does")
    click.echo(f"   - tools: list of registered tool names")
    click.echo(f"   - system_instructions: agent behavior description")
    click.echo(f"   - model_preference: preferred LLM models (free→paid order)")


@cli.command()
def list_tools():
    """List all registered tools."""
    click.echo("🔧 Registered Tools\n")

    # Import tools to trigger registration
    try:
        import agentfactory.tools  # noqa: F401 — triggers tool registration on import
    except ImportError as e:
        click.echo(f"Warning: Could not load tools: {e}")

    from agentfactory.base_tools import list_tools_detailed

    # Get tools from global registry
    tools = list_tools_detailed()

    if not tools:
        click.echo("No tools registered. Import tools modules to register them.")
        return

    click.echo(f"{'NAME':<30} {'CATEGORY':<15} {'COST':>10} {'SAFETY':<12} TAGS")
    click.echo("-" * 80)
    for t in tools:
        tags = ",".join(t["tags"]) if t["tags"] else "-"
        click.echo(f"{t['name']:<30} {t['category']:<15} ${t['cost_per_call_usd']:<9.4f} {t['safety_level']:<12} {tags}")

    click.echo(f"\nTotal: {len(tools)} tools")


@cli.command()
def status():
    """Check the current approval server status."""
    import requests

    server_url = os.getenv("AGENT_SERVER_URL", "http://localhost:8000/api/agent/status")

    try:
        response = requests.get(server_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            click.echo("📡 Approval Server Status\n")
            click.echo(f"  Connection: ✓ Online")
            click.echo(f"  Status: {data.get('status', 'unknown')}")
            if data.get("feature_name"):
                click.echo(f"  Active Proposal: {data.get('feature_name')}")
            if data.get("branch_name"):
                click.echo(f"  Branch: {data.get('branch_name')}")
            click.echo(f"  Last Updated: {data.get('updated_at', 'N/A')}")
        else:
            click.echo(f"  Connection: ✗ HTTP {response.status_code}")
    except requests.exceptions.ConnectionError:
        click.echo("📡 Approval Server Status")
        click.echo("  Connection: ✗ Offline")
        click.echo("  Start with: agentfactory run --server-only")


# ============================================================
# Helper Functions
# ============================================================

def _create_env_template() -> str:
    """Create the .env template content."""
    return f"""# ============================================================
# AgentFactory Configuration
# Copy this file, fill in your values, and save as .env
# ============================================================

# --- LLM API Keys ---
# Gemini (free tier) -- recommended default
GEMINI_API_KEY=your-gemini-api-key-here

# OpenAI (paid fallback)
OPENAI_API_KEY=your-openai-api-key-here

# Anthropic (premium fallback)
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# --- Search (optional) ---
# Tavily for web research (free tier available)
TAVILY_API_KEY=your-tavily-api-key-here

# --- Observability (optional) ---
LANGFUSE_SECRET_KEY=your-langfuse-secret-key
LANGFUSE_PUBLIC_KEY=your-langfuse-public-key
LANGFUSE_HOST=https://cloud.langfuse.com

# --- Repository Paths ---
# Configure paths to your separate repos
BACKEND_PATH=/absolute/path/to/your/fastapi-backend
FRONTEND_PATH=/absolute/path/to/your/react-frontend
ADMIN_PATH=/absolute/path/to/your/admin-panel

# --- Notifications ---
# Discord webhook URL for approval notifications
DEV_NOTIF_WEBHOOK_URL=https://discord.com/api/webhooks/your-webhook-id/your-webhook-token

# Gmail (for email notifications)
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
ADMIN_EMAIL=recipient@example.com

# --- Approval Server ---
APPROVAL_SERVER_HOST=0.0.0.0
APPROVAL_SERVER_PORT=8000

# --- LLM Configuration ---
AGENT_DAILY_BUDGET_USD=5.00
LLM_TEMPERATURE=0.2
"""


if __name__ == "__main__":
    cli()
