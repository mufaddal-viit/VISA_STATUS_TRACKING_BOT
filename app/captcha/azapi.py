"""AZAPI.ai image captcha solver."""

from __future__ import annotations

import httpx
import structlog

from app.captcha.base import CaptchaSolverBase, CaptchaSolverError

logger = structlog.get_logger(__name__)


class AzapiSolver(CaptchaSolverBase):
    name = "azapi"

    def __init__(self, api_key: str, endpoint: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._api_key and self._endpoint)

    async def solve(self, image_bytes: bytes) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._endpoint,
                    content=image_bytes,
                    headers={
                        "Authorization": self._api_key,
                        "content-type": "image/jpeg",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CaptchaSolverError(
                f"AZAPI returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise CaptchaSolverError(f"AZAPI request error: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise CaptchaSolverError(
                f"AZAPI returned non-JSON response: {response.text[:200]}"
            ) from exc

        logger.debug("azapi_raw_response", data=data)

        if str(data.get("status", "")).lower() != "success":
            msg = data.get("message") or data.get("error") or str(data)
            raise CaptchaSolverError(f"AZAPI solve failed: {msg}")

        # Response shape: {"status": "Success", "output": {"captcha": "<text>", ...}, ...}
        # Fall back to top-level "result" for forward compatibility.
        output = data.get("output") or {}
        result = (output.get("captcha") or data.get("result") or "").strip()

        # AZAPI returns the literal string "Empty" when it cannot read the captcha.
        if not result or result.lower() == "empty":
            raise CaptchaSolverError(f"AZAPI returned empty result (response: {data})")

        return result
