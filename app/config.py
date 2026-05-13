from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field

# ---------------------------------------------------------------------------
# VFS tracking URL mapping  (country -> encoded URL)
# Keep %2B and %2F as-is; do NOT decode them.
# ---------------------------------------------------------------------------
# VFS_TRACKING_URLS: dict[str, str] = {
#     "india": (
#         "https://visa.vfsglobal.com/ind/en/deu/track-application"
#     ),
#     "germany": (
#         "https://visa.vfsglobal.com/deu/en/ind/track-application"
#     ),
#     "uk": (
#         "https://visa.vfsglobal.com/gbr/en/ind/track-application"
#     ),
#     "usa": (
#         "https://visa.vfsglobal.com/usa/en/ind/track-application"
#     ),
#     "canada": (
#         "https://visa.vfsglobal.com/can/en/ind/track-application"
#     ),
#     "france": (
#         "https://visa.vfsglobal.com/fra/en/ind/track-application"
#     ),
#     "italy": (
#         "https://visa.vfsglobal.com/ita/en/ind/track-application"
#     ),
#     "uae": (
#         "https://visa.vfsglobal.com/are/en/ind/track-application"
#     ),
#     "south_africa": (
#         "https://visa.vfsglobal.com/zaf/en/ind/track-application"
#     ),
# }

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
    """Application settings loaded from environment / .env file."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Browser / Playwright
    headless: bool = True
    browser_timeout: int = Field(default=30_000, description="Playwright timeout in ms")
    captcha_max_retries: int = 3

    # Tesseract
    tesseract_cmd: str | None = None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_settings() -> Settings:
    return Settings()


def get_tracking_url(country: str) -> str | None:
    """Return the VFS tracking URL for the given country key (case-insensitive)."""
    return VFS_TRACKING_URLS.get(country.lower().strip())
