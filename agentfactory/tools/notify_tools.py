"""
Notification Tools — Send alerts via Discord, Gmail, and webhooks.

These tools are used by the Senior Architect to notify the human
operator when proposals are ready for review.
"""

import os
import json
import requests
from typing import Optional, Dict, List
from agentfactory.base_tools import tool, SafetyLevel


@tool("send_discord_notification", category="notify", cost_per_call_usd=0.001, tags=["notify", "discord"])
def send_discord_notification(
    title: str,
    message: str,
    color: int = 0x00aaff,
    fields: Optional[List[Dict[str, str]]] = None,
    channel: Optional[str] = None,
) -> str:
    """
    Send a rich embed notification to Discord via webhook.

    Args:
        title: Notification title
        message: Main message content
        color: Embed color (as integer, e.g., 0x00ff00 for green)
        fields: Optional list of {name, value} fields for the embed
        channel: Optional channel override (uses DEV_NOTIF_WEBHOOK_URL by default)

    Returns:
        Status message
    """
    webhook_url = channel or os.getenv("DEV_NOTIF_WEBHOOK_URL")

    if not webhook_url:
        return "Error: No Discord webhook configured. Set DEV_NOTIF_WEBHOOK_URL."

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "timestamp": _get_timestamp(),
    }

    if fields:
        embed["fields"] = fields

    payload = {
        "username": "AgentFactory",
        "avatar_url": "https://avatars.githubusercontent.com/u/173870359",
        "embeds": [embed],
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 204:
            return "Discord notification sent successfully."
        else:
            return f"Discord error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error sending Discord notification: {str(e)}"


@tool("send_gmail_notification", category="notify", cost_per_call_usd=0.001, tags=["notify", "email"])
def send_gmail_notification(
    subject: str,
    message_body: str,
    recipient: Optional[str] = None,
    cc: Optional[str] = None,
) -> str:
    """
    Send an email notification via Gmail SMTP.

    Args:
        subject: Email subject
        message_body: HTML or text body
        recipient: Recipient email (defaults to ADMIN_EMAIL or GMAIL_USER)
        cc: CC recipients

    Returns:
        Status message
    """
    import smtplib
    from email.message import EmailMessage

    sender = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    admin_email = recipient or os.getenv("ADMIN_EMAIL", sender)

    if not sender or not password:
        return "Error: Gmail credentials not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD."

    msg = EmailMessage()
    msg.set_content(message_body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = admin_email
    if cc:
        msg["Cc"] = cc

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.send_message(msg)
        return f"Gmail notification sent to {admin_email}."
    except Exception as e:
        return f"Error sending Gmail notification: {str(e)}"


@tool("send_webhook_notification", category="notify", tags=["notify", "webhook"])
def send_webhook_notification(
    url: str,
    payload: Dict,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    Send an arbitrary webhook notification.

    Args:
        url: Webhook URL
        payload: JSON payload to send
        method: HTTP method (default: POST)
        headers: Optional HTTP headers

    Returns:
        Status message with response info
    """
    if not headers:
        headers = {"Content-Type": "application/json"}

    try:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            headers=headers,
            timeout=10,
        )

        return (
            f"Webhook sent to {url}\n"
            f"Status: {response.status_code}\n"
            f"Response: {response.text[:500]}"
        )
    except Exception as e:
        return f"Error sending webhook: {str(e)}"


def _get_timestamp() -> str:
    """Get current ISO timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
