"""Abstract base for all captcha solver backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CaptchaSolverBase(ABC):
    """All solvers implement this interface."""

    name: str  # human-readable name used in logs

    @abstractmethod
    async def solve(self, image_bytes: bytes) -> str:
        """
        Solve the captcha from raw image bytes.

        Returns the solved text string.
        Raises CaptchaSolverError on any failure.
        """

    def is_configured(self) -> bool:
        """Return False if required credentials are missing (solver will be skipped)."""
        return True


class CaptchaSolverError(Exception):
    """Raised by any solver when it cannot produce a result."""
