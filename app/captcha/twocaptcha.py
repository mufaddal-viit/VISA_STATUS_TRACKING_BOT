"""2captcha.com image captcha solver."""

from __future__ import annotations

import asyncio
import base64

import structlog

from app.captcha.base import CaptchaSolverBase, CaptchaSolverError

logger = structlog.get_logger(__name__)


class TwoCaptchaSolver(CaptchaSolverBase):
    name = "2captcha"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def solve(self, image_bytes: bytes) -> str:
        # 2captcha SDK is blocking (long-polls the result endpoint).
        # Offload to a thread so we don't stall the event loop.
        return await asyncio.to_thread(self._solve_sync, image_bytes)

    def _solve_sync(self, image_bytes: bytes) -> str:
        try:
            from twocaptcha import TwoCaptcha, ApiException, NetworkException, ValidationException, TimeoutException
        except ImportError as exc:
            raise CaptchaSolverError(
                "2captcha-python is not installed. Run: pip install 2captcha-python"
            ) from exc

        # 2captcha.normal() accepts a base64 string positionally
        # (its get_method() detects base64 by: no '.' present AND len > 50).
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        solver = TwoCaptcha(self._api_key)

        try:
            result = solver.normal(b64)
        except (ApiException, NetworkException, ValidationException, TimeoutException) as exc:
            raise CaptchaSolverError(f"2captcha solve failed: {exc}") from exc
        except Exception as exc:
            raise CaptchaSolverError(f"2captcha unexpected error: {exc}") from exc

        logger.debug("twocaptcha_raw_response", result=result)

        # Library returns {"captchaId": "...", "code": "<text>"}
        text = (result.get("code", "") if isinstance(result, dict) else str(result)).strip()
        if not text:
            raise CaptchaSolverError("2captcha returned empty result")

        return text
