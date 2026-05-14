"""
Captcha solver chain.

Tries each configured solver in order. If one fails, logs the error and
falls through to the next. Raises TrackingError only when all solvers fail.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from app.captcha.base import CaptchaSolverBase, CaptchaSolverError
from app.models import TrackingError

logger = structlog.get_logger(__name__)

DEBUG_DIR = Path("debug_captcha")


async def solve_captcha(image_bytes: bytes, solvers: list[CaptchaSolverBase]) -> str:
    """
    Try each solver in order and return the first successful result.

    Saves the raw image to debug_captcha/ for inspection.
    Raises TrackingError if all solvers fail or none are configured.
    """
    DEBUG_DIR.mkdir(exist_ok=True)
    (DEBUG_DIR / "captcha_raw.png").write_bytes(image_bytes)

    active = [s for s in solvers if s.is_configured()]
    if not active:
        raise TrackingError(
            "No captcha solvers are configured. "
            "Set at least one of: AZAPI_API_KEY, TWOCAPTCHA_API_KEY, OPENAI_API_KEY"
        )

    errors: list[str] = []
    for solver in active:
        try:
            logger.info("captcha_solver_attempt", solver=solver.name)
            result = await solver.solve(image_bytes)
            logger.info("captcha_solver_success", solver=solver.name, text=result)
            return result
        except CaptchaSolverError as exc:
            logger.warning("captcha_solver_failed", solver=solver.name, error=str(exc))
            errors.append(f"{solver.name}: {exc}")

    raise TrackingError(
        f"All captcha solvers failed. Errors: {' | '.join(errors)}"
    )
