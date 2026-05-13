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


class TrackingResponse(BaseModel):
    """Successful tracking result."""

    reference_number: str
    last_name: str
    country: str
    status: str = Field(description="Application status text returned by VFS")
    status_details: str | None = Field(
        default=None, description="Extra details if available"
    )


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: str
    detail: str | None = None


class TrackingError(Exception):
    """Raised when browser automation or OCR fails in an expected way (→ 422)."""
