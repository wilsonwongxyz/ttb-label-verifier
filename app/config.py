from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["anthropic", "fixture"]


class Settings(BaseSettings):
    """App settings, read from ``LV_``-prefixed environment variables (or a ``.env`` file).

    The prefix keeps the app's credentials separate from any ``ANTHROPIC_*`` variables the
    surrounding environment sets for other tools.
    """

    model_config = SettingsConfigDict(env_prefix="LV_", env_file=".env", extra="ignore")

    provider: Provider = "anthropic"
    anthropic_api_key: SecretStr | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    model: str = "claude-haiku-5-5"
    effort: Literal["low", "medium", "high"] = "low"
    max_output_tokens: int = 2048
    extract_timeout_s: float = 8.0
    extract_max_retries: int = 1

    fixtures_dir: Path = Path(__file__).parent / "samples"

    max_image_bytes: int = 10 * 1024 * 1024

    batch_concurrency: int = 8
    batch_max_files: int = 300
    batch_max_bytes: int = 300 * 1024 * 1024
    batch_ttl_s: float = 3600.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
