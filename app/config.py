from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Populate os.environ from a local .env so the modules that read env vars
# directly (app/db.py, app/telegram.py, the CRON_SECRET check) work in local
# dev. No-op in production: Vercel and GitHub Actions supply real env vars and
# ship no .env file, and load_dotenv() never overrides an existing variable.
load_dotenv()

# ---------------------------------------------------------------------------
# VFS tracking URL mapping  (country -> encoded tracking URL)
# ---------------------------------------------------------------------------

VFS_TRACKING_URLS: dict[str, str] = {
    "austria": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/B1eRfIlnOB2pWKLJ+6DYKyWgZoHLe2GNbJkZ93iyjElWYM7GLrZJR2lfnxL+DKS6W5vGm4MPWKCs4n8m/hAKqg=",
    "belgium": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/ELG1mvuWayHa7D4+drYSCNPUotMvQQcOfI6+GRTL8i6zCC9agt1XwXtWAvsE73L+35+PUKN4IDZIyTBjDiT4XQ=",
    "bulgaria": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/AoKGAVyoVK/e8oAZk1pB9ed+n4cBnpujmSr+kOjjctvLBs34kSyNOTRhqlywuUm055aWioJ/g+1L0fgTfI4OznOU7hrU4o+L0v5ZTbAK9Rj",
    "croatia": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/AxlGb0+mKNoQbLfeca8M1c912vJaP/ext/Z5XkUET9rDj46gjYIY/i/s1vX/1yc4XgALVBkBaPBurbw+F5UJrQ=",
    "czech_republic": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/Jdf3aByYnqcjO/DruY4vPZfAMLbwkob13WiEvth/SSJfQ80KIaOztETUA08burPeRZpp9Q5MmMLrgiRuXoaXX5ea2a48W4mVOYQCnsCIJ25",
    "denmark": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/Ey/UM5rKPMuPWoM9so6dErw9MlQ/wjq9lJGkU959vsBFWfywW4EnqsZjqhFfeUL/ZhpTV9h949cWoQRR4ULwSI=",
    "estonia": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/CbH0A9wGBx658I5hrzrIX1gbnQaKHsBo/ZKbK61qsclcEP97gUKuW40l/0O19m3qqEqFaPCj3ldmUpJfi/WHBE=",
    "finland": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/K3TR28D6QZe7ZMQ849/GyMRu9oyBCGJ+NHqcGb/3GtVfQgqkOOVD5gkTUip1u2GeOb5i1vyc9R/5h/HGxyqUw4=",
    "france": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/APnFmGO26yoncx/v5lsUb/wVhluA+MrsaR4qhJ36RK6lZReGM4OWlGeOaIjmCpDK8J5PzwZ6/HKK030NcXZIR8=",
    "germany": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/D51sQDPM3iX33nhV8ZVx5LMbcNWdvYdJSEHvBABOCM04d1vJy/c8BTWqIGdxXWw0+0v/2VV1ABNOZ13kjanqq4=",
    "greece": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/EN7CXLp+WuxKISDPoeYsik4IagdOROxmzICHC69gIwcqVtMT225Gdbdc/lfIyGZJn22kt3x+JvPgSH25/crF1o=",
    "hungary": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/FVWGkYuENF3aj/jI+9gY9pE83UEf2P6x9Sl8cvMqFf4RqjI2ph0hMd0kpF1IDYymMhifrNiz0XJp0a4ie6BYWs=",
    "iceland": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/LZichRNvadRezZVFEYcVI60hn/qmtP4d3S1GWHyZTsibhIqWlsDm1rEPZbRXPW1z7KrWJx5YAc93TPDL3yQ8vg=",
    "italy": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/NBWviHzkZm/Vty3IMuNZFf56G+QTtO86CLB7+plquVaHrFd0ZevBpiA2DZyzWNsUw==",
    "latvia": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/H4U4Yoxvegz1LFctYtWZRfI62JQCrj2NXrFipZADwMY9sDjbXnkQOdKvIFaJB1bot/z0fXtpuPmmc3NmFuZj4Y=",
    "lithuania": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=",
    "luxembourg": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/Kd1F6s3re+hCX/0P4gAq8dza8YZ0Cuj8jgFzk/mZbpem1o2RTsMWzHqGYlc70gjCkTAjc077Gfg9DGSyqvHJ9I=",
    "maltaLS": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/OVMz2fDVFo4HOHOD9+ZsS2aHQ5OzxnlPZonjofTOFmXYjYZNB/WcybRu22/pkuUnPy3m9t88oUBEcQpT0qRopVJU9MCU6qsx82CKbm6/fuq",
    "maltaSS":"https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/Ax78BwNOVdHIB9TfH0Prkk6tYGVZccJwS5aZlRMwZ9ID09X/A+DlU97cf/yVfG62g==",
    "netherlands": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/GAZMwphNakm2hstnNbT9MeLtMSNCgJ8GiT50RSS4w+IoAskZVw2rQ7iiIFWAOR5njTzbA57yYOCwjAhRqA+rhd+PHxU6cEjEDY3+6KamG/x#CaptchaImage",
    "norway": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/MMWoQ2u/1NQd8ht0KuMDeqNJEBHzf/pf00e1uZwPSD2/LNngwrKj94y0V6cXSB5qxMleaBM8etOdiFjekcDG9s=",
    "portugal": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/NNL8oYEDVviiH9LFkvyoJmx/fXKYWsKwvlIATddMeXNaVw6YNwyTP4kWTXZf1aExOhJJm50XEwU+QGn5de2ZiLW1ei+WuTzHGa3dGgr3b55",
    "slovakia": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/DvZXWdya6EfmJxmvJVsEUMxZHqV9nn9V3AUe/G9ScmRwS65SPlDJffl4uZyDL6EApHA56dD99Dho8cugR49l1s=",
    "sweden": "https://www.vfsvisaonline.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/A9+3ayKh2o6XUmXfdhngCYC/kCmfJDiXAWQ8RzLfkkZqcSSyudKLdnOWS1Y0NfXXoeiTv8WgA8uFsKJdE78qIhibkPkewOMis7C542G4e5D",
    "switzerland": "https://visatracking.vfsglobal.com/Global-Passporttracking/Track/Index?q=shSA0YnE4pLF9Xzwon/x/JldnEmQkhedF2EE/dpQUaSZd5MKQ2Boncv2lH5vcJyBPB4zJwAsn3gqXfSXBOrlTvTixZ8O9TQ28hsBUPeEo9g=",
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

    # ------------------------------------------------------------------
    # Remote browser (Browserless.io) — required for serverless hosts
    # like Vercel that cannot run a local Chromium binary.
    # ------------------------------------------------------------------
    browserless_ws_endpoint: str = Field(
        default="",
        description=(
            "Browserless.io WebSocket endpoint, e.g. "
            "wss://production-sfo.browserless.io?token=YOUR_TOKEN. "
            "If set, connect to this remote browser instead of launching a local one."
        ),
    )
    captcha_max_retries: int = Field(default=3, description="Max captcha solve+submit attempts")

    @property
    def use_remote_browser(self) -> bool:
        """True when a Browserless endpoint is configured (serverless deployment)."""
        return bool(self.browserless_ws_endpoint.strip())
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
