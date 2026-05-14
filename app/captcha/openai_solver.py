"""OpenAI GPT-4o vision captcha solver."""

from __future__ import annotations

import base64

import structlog

from app.captcha.base import CaptchaSolverBase, CaptchaSolverError
from app.captcha.prompts import OPENAI_CAPTCHA_PROMPT

logger = structlog.get_logger(__name__)


class OpenAISolver(CaptchaSolverBase):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def solve(self, image_bytes: bytes) -> str:
        try:
            from openai import AsyncOpenAI, OpenAIError
        except ImportError as exc:
            raise CaptchaSolverError(
                "openai package is not installed. Run: pip install openai"
            ) from exc

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        client = AsyncOpenAI(api_key=self._api_key)

        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                            {"type": "text", "text": OPENAI_CAPTCHA_PROMPT},
                        ],
                    }
                ],
                max_tokens=20,
                temperature=0,
            )
        except OpenAIError as exc:
            raise CaptchaSolverError(f"OpenAI solve failed: {exc}") from exc

        raw = response.choices[0].message.content or ""
        result = "".join(c for c in raw if c.isalnum()).strip()

        logger.debug("openai_raw_response", raw=raw, cleaned=result)

        if not result:
            raise CaptchaSolverError("OpenAI returned empty captcha text")

        return result
