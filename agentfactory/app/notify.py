"""
Notification dispatcher (Phase 5.4) — Discord / Gmail / webhook wiring.

Workspace owners configure ``workspace.settings.notifications``:

.. code-block:: json

    {
      "notifications": {
        "on_run_complete": true,
        "on_proposal": true,
        "discord_webhook_url": "https://discord.com/api/webhooks/...",
        "webhook_url": "https://hooks.example.com/agentfactory",
        "email": "ops@example.com"
      }
    }

When an event fires (run completed, gated proposal created), the dispatcher
reuses the SDK's built-in notification tools (``notify_tools``) with the
configured destinations, running fire-and-forget in a daemon thread so the
run loop is never blocked by a slow webhook.

Destinations are optional: only channels that are configured AND enabled fire.
"""

import json
import threading
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


def _notification_config(workspace_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the notifications block from workspace settings (always a dict)."""
    settings = workspace_settings or {}
    notifications = settings.get("notifications")
    if not isinstance(notifications, dict):
        return {}
    return notifications


def _fire(target, *args, **kwargs) -> None:
    """Run a notify call in a daemon thread (fire-and-forget)."""

    def runner():
        try:
            target(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — notifications must never break runs
            logger.warning("Notification dispatch failed", error=str(e))

    threading.Thread(target=runner, daemon=True, name="agentfactory-notify").start()


def notify_run_complete(workspace_settings: Dict[str, Any], run: Dict[str, Any], agent_name: str) -> None:
    """Notify configured channels that a run finished (Phase 5.4 exit: run completion)."""
    config = _notification_config(workspace_settings)
    if not config.get("on_run_complete"):
        return
    status = run.get("status", "completed")
    stats = run.get("stats")
    cost = None
    if isinstance(stats, str):
        try:
            stats = json.loads(stats)
        except json.JSONDecodeError:
            stats = None
    if isinstance(stats, dict):
        cost = stats.get("total_cost_usd")

    message = (
        f"Agent **{agent_name}** finished run `{run.get('id', '')[:8]}` with status **{status}**"
        + (f" — cost ${cost:.4f}" if cost is not None else "")
    )
    title = "✅ Run completed" if status == "completed" else f"⚠️ Run {status}"

    if config.get("discord_webhook_url"):
        from agentfactory.tools.notify_tools import send_discord_notification

        color = 0x00FF00 if status == "completed" else 0xFFAA00
        _fire(send_discord_notification, title=title, message=message[:4000],
              color=color, channel=config["discord_webhook_url"])

    if config.get("webhook_url"):
        from agentfactory.tools.notify_tools import send_webhook_notification

        _fire(send_webhook_notification, url=config["webhook_url"], payload={
            "event": "run.complete",
            "run_id": run.get("id"),
            "agent": agent_name,
            "status": status,
            "task": (run.get("task") or "")[:2000],
            "result": (run.get("result") or "")[:4000],
            "cost_usd": cost,
        })

    if config.get("email"):
        from agentfactory.tools.notify_tools import send_gmail_notification

        _fire(send_gmail_notification, subject=f"[AgentFactory] Run {status}: {agent_name}",
              message_body=message, recipient=config["email"])


def notify_proposal_created(workspace_settings: Dict[str, Any], proposal: Dict[str, Any], agent_name: str) -> None:
    """Notify configured channels that a gated proposal is awaiting review (Phase 5.4)."""
    config = _notification_config(workspace_settings)
    if not config.get("on_proposal"):
        return

    title = "🧍 Human approval required"
    message = (
        f"Agent **{agent_name}** submitted a proposal awaiting review:\n"
        f"**{(proposal.get('title') or '')[:200]}**\n"
        f"`{proposal.get('id', '')[:8]}`"
    )

    if config.get("discord_webhook_url"):
        from agentfactory.tools.notify_tools import send_discord_notification

        _fire(send_discord_notification, title=title, message=message[:4000],
              color=0x0088FF, channel=config["discord_webhook_url"])

    if config.get("webhook_url"):
        from agentfactory.tools.notify_tools import send_webhook_notification

        _fire(send_webhook_notification, url=config["webhook_url"], payload={
            "event": "proposal.created",
            "proposal_id": proposal.get("id"),
            "agent": agent_name,
            "title": proposal.get("title"),
            "plan": (proposal.get("plan") or "")[:4000],
        })

    if config.get("email"):
        from agentfactory.tools.notify_tools import send_gmail_notification

        _fire(send_gmail_notification, subject=f"[AgentFactory] Proposal: {(proposal.get('title') or '')[:80]}",
              message_body=message, recipient=config["email"])
