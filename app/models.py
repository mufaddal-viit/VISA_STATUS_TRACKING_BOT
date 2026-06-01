from __future__ import annotations

from pydantic import BaseModel, Field


class TrackingRequest(BaseModel):
    """Payload for the VFS tracking check endpoint."""

    reference_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="VFS application reference number",
        examples=["INND12345678"],
    )
    last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Applicant last name as on the application",
        examples=["SHARMA"],
    )
    debug: bool = Field(
        default=False,
        description="If true, the response includes captcha images and per-attempt solver output.",
    )


class TrackRequest(BaseModel):
    """Payload for adding an application to the twice-daily watchlist."""

    deal_id: str = Field(..., min_length=1, max_length=100, description="CRM deal id (used in the deal link)")
    reference_number: str = Field(..., min_length=1, max_length=100, description="VFS application reference number")
    last_name: str = Field(..., min_length=1, max_length=100, description="Applicant last name as on the application")
    country: str = Field(..., min_length=1, max_length=50, description="Country key, see /v1/vfs-tracking/supported-countries")


class CaptchaAttempt(BaseModel):
    """Debug record for a single captcha solve attempt."""

    attempt: int
    captcha_b64: str | None = Field(
        default=None, description="Base64 PNG of the captcha image shown this attempt"
    )
    solved_text: str | None = Field(
        default=None, description="Text the solver returned for this attempt"
    )
    accepted: bool = Field(
        default=False, description="Whether VFS accepted this captcha"
    )
    error: str | None = Field(default=None, description="Error for this attempt, if any")


class TrackingResponse(BaseModel):
    """Successful tracking result."""

    reference_number: str
    last_name: str
    country: str
    status: str = Field(description="Application status text returned by VFS")
    status_details: str | None = Field(
        default=None, description="Extra details if available"
    )
    debug_attempts: list[CaptchaAttempt] | None = Field(
        default=None,
        description="Per-attempt captcha debug info — only present when debug=true.",
    )


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: str
    detail: str | None = None


class TrackingError(Exception):
    """Raised when browser automation or OCR fails in an expected way (→ 422)."""

    def __init__(self, message: str, debug_attempts: list[dict] | None = None) -> None:
        super().__init__(message)
        # Per-attempt captcha debug info, attached so the endpoint can surface
        # it even when the check ultimately fails.
        self.debug_attempts = debug_attempts or []
