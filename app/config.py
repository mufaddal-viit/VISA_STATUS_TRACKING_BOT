from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# VFS tracking URL mapping  (country -> encoded tracking URL)
# ---------------------------------------------------------------------------

VFS_TRACKING_URLS: dict[str, str] = {
    "austria": (
        "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/B1eRfIlnOB2pWKLJ+6DYKyWgZoHLe2GNbJkZ93iyjElWYM7GLrZJR2lfnxL+DKS6W5vGm4MPWKCs4n8m/hAKqg="
    ),
    "netherlands": (
        "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/GAZMwphNakm2hstnNbT9MeLtMSNCgJ8GiT50RSS4w+IoAskZVw2rQ7iiIFWAOR5njTzbA57yYOCwjAhRqA+rhd+PHxU6cEjEDY3+6KamG/x#CaptchaImage"
    ),
    "czech_republic": (
        "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/Jdf3aByYnqcjO/DruY4vPZfAMLbwkob13WiEvth/SSJfQ80KIaOztETUA08burPeRZpp9Q5MmMLrgiRuXoaXX5ea2a48W4mVOYQCnsCIJ25"
    ),
}


class Settings(BaseSettings):
    """Application settings — all values can be overridden via environment variables or .env."""

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000

    # ------------------------------------------------------------------
    # Browser / Playwright
    # ------------------------------------------------------------------
    headless: bool = True
    browser_timeout: int = Field(default=30_000, description="Playwright default timeout in ms")
    captcha_max_retries: int = Field(default=3, description="Max captcha solve+submit attempts")
    captcha_solver: str = Field(
        default="",
        description=(
            "If set, use only this captcha solver (one of: 'azapi', 'twocaptcha', 'openai'). "
            "If empty, fall back through all configured solvers in order."
        ),
    )

    # ------------------------------------------------------------------
    # Captcha solver — AZAPI.ai  (solver #1)
    # ------------------------------------------------------------------
    azapi_api_key: str = Field(default="", description="AZAPI.ai API key")
    azapi_endpoint: str = Field(
        default="https://api.azapi.ai/t0001c",
        description="AZAPI.ai image-captcha endpoint",
    )

    # ------------------------------------------------------------------
    # Captcha solver — 2captcha.com  (solver #2 fallback)
    # ------------------------------------------------------------------
    twocaptcha_api_key: str = Field(default="", description="2captcha.com API key")

    # ------------------------------------------------------------------
    # Captcha solver — OpenAI GPT-4o vision  (solver #3 fallback)
    # ------------------------------------------------------------------
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model used for captcha vision solving",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = "INFO"
    log_format: str = Field(default="json", description="'json' or 'console'")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_tracking_url(country: str) -> str | None:
    """Return the VFS tracking URL for the given country key (case-insensitive)."""
    return VFS_TRACKING_URLS.get(country.lower().strip())
