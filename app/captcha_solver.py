"""
Thin shim: builds the solver chain from settings and delegates to it.
Import surface used by vfs_tracker.py.
"""

from __future__ import annotations

import base64

from app.captcha import solve_captcha as _solve_captcha
from app.captcha.azapi import AzapiSolver
from app.captcha.base import CaptchaSolverBase
from app.captcha.openai_solver import OpenAISolver
from app.captcha.twocaptcha import TwoCaptchaSolver
from app.config import Settings
from app.models import TrackingError


def _build_all_solvers(settings: Settings) -> list[CaptchaSolverBase]:
    return [
        AzapiSolver(
            api_key=settings.azapi_api_key,
            endpoint=settings.azapi_endpoint,
        ),
        TwoCaptchaSolver(api_key=settings.twocaptcha_api_key),
        OpenAISolver(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        ),
    ]


async def solve_captcha_from_bytes(image_bytes: bytes, settings: Settings) -> str:
    """Build solver chain from settings and solve the captcha.

    If ``settings.captcha_solver`` is set, only that solver is used (no fallback).
    Otherwise every configured solver is tried in order.
    """
    all_solvers = _build_all_solvers(settings)

    selected = (settings.captcha_solver or "").strip().lower()
    if selected:
        by_name = {s.name: s for s in all_solvers}
        if selected not in by_name:
            raise TrackingError(
                f"Unknown CAPTCHA_SOLVER='{selected}'. "
                f"Valid options: {', '.join(by_name)}"
            )
        solver = by_name[selected]
        if not solver.is_configured():
            raise TrackingError(
                f"CAPTCHA_SOLVER='{selected}' is selected but its API key is not configured."
            )
        return await _solve_captcha(image_bytes, [solver])

    return await _solve_captcha(image_bytes, all_solvers)


def image_bytes_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")
