"""Application configuration via pydantic-settings.

All settings are read from environment variables (prefix ``VISUAL_``) and an
optional ``.env`` file. They are all optional: offline, mock-first defaults are
applied when nothing is supplied, so the service runs with no GPU, no network
and no docker.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for visual-studio.

    Attributes are populated from ``VISUAL_*`` environment variables. Passing
    keyword arguments directly (e.g. in tests) overrides the environment.
    """

    model_config = SettingsConfigDict(
        env_prefix="visual_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = "data/visual_studio.db"
    output_dir: str = "outputs"
    provider: str = "mock"
    # JSON map: image_type -> provider name.
    provider_route: str = '{"main":"mock","scene":"mock","detail":"mock"}'
    webhook_url: str | None = None
    host: str = "0.0.0.0"
    port: int = 8011

    # -- real provider: Alibaba DashScope (百炼) -------------------------
    # Empty => fall back to the DASHSCOPE_API_KEY env var at construction time.
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com"
    image_model: str = "qwen-image-3.0"
    image_timeout: float = 120.0

    # -- real provider: Seedream (Volcengine) ---------------------------
    seedream_api_key: str = ""

    @property
    def provider_route_map(self) -> dict[str, str]:
        """Parsed provider route map (image_type -> provider name)."""
        import json

        try:
            data = json.loads(self.provider_route)
        except (json.JSONDecodeError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {str(k): str(v) for k, v in data.items()}


def get_settings() -> Settings:
    """Construct a :class:`Settings` instance from the environment."""
    return Settings()
