"""
Configuration — Pydantic settings with .env loading and type validation.

All configuration is loaded from environment variables with sensible defaults.
The `.env` file is loaded automatically if present.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Optional


class Settings(BaseSettings):
    """
    Central configuration for AgentFactory.

    All values are read from environment variables (or .env file).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # ============================================================
    # LLM Provider API Keys
    # ============================================================
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # ============================================================
    # LLM Failover & Budget
    # ============================================================
    llm_pipeline: List[str] = Field(
        default_factory=lambda: ["gemini-2.5-flash", "gpt-4o", "claude-3-5-sonnet-20241022"],
        alias="LLM_PIPELINE",
    )
    daily_budget_usd: float = Field(default=5.0, alias="AGENT_DAILY_BUDGET_USD")
    default_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")

    # ============================================================
    # Observability (Langfuse / OpenTelemetry)
    # ============================================================
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    otel_endpoint: Optional[str] = Field(default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    # ============================================================
    # Repository Paths (for multi-repo engineering team)
    # ============================================================
    backend_path: Optional[str] = Field(default=None, alias="BACKEND_PATH")
    frontend_path: Optional[str] = Field(default=None, alias="FRONTEND_PATH")
    admin_path: Optional[str] = Field(default=None, alias="ADMIN_PATH")

    # ============================================================
    # Notification (Discord, Gmail)
    # ============================================================
    dev_notif_webhook_url: Optional[str] = Field(default=None, alias="DEV_NOTIF_WEBHOOK_URL")
    gmail_user: Optional[str] = Field(default=None, alias="GMAIL_USER")
    gmail_app_password: Optional[str] = Field(default=None, alias="GMAIL_APP_PASSWORD")
    admin_email: Optional[str] = Field(default=None, alias="ADMIN_EMAIL")

    # ============================================================
    # Approval Server
    # ============================================================
    approval_server_port: int = Field(default=8000, alias="APPROVAL_SERVER_PORT")
    approval_server_host: str = Field(default="0.0.0.0", alias="APPROVAL_SERVER_HOST")

    # ============================================================
    # MCP Configuration
    # ============================================================
    mcp_config_file: str = Field(default="mcp.json", alias="MCP_CONFIG_FILE")
    mcp_servers_dir: str = Field(default="mcp_servers", alias="MCP_SERVERS_DIR")

    @field_validator("daily_budget_usd")
    @classmethod
    def validate_budget(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Daily budget must be positive")
        return v

    @property
    def has_gemini(self) -> bool:
        return self.gemini_api_key is not None

    @property
    def has_openai(self) -> bool:
        return self.openai_api_key is not None

    @property
    def has_anthropic(self) -> bool:
        return self.anthropic_api_key is not None

    @property
    def has_langfuse(self) -> bool:
        return self.langfuse_secret_key is not None and self.langfuse_public_key is not None

    def get_repo_paths(self) -> dict:
        """Return the configured repo paths."""
        return {
            "backend": self.backend_path or "",
            "frontend": self.frontend_path or "",
            "admin_panel": self.admin_path or "",
        }

    def get_mcp_config_path(self) -> str:
        """Resolve the MCP config file path."""
        if os.path.isabs(self.mcp_config_file):
            return self.mcp_config_file
        return os.path.join(os.getcwd(), self.mcp_config_file)


# Singleton settings instance
settings = Settings()
