"""
VFS Global Tracking Bot – FastAPI application.

Run with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Playwright requires SelectorEventLoop on Windows; uvicorn defaults to ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse, Response

from app.config import VFS_TRACKING_URLS, get_settings, get_tracking_url
from app.logging_config import setup_logging
from app.models import ErrorResponse, TrackingError, TrackingRequest, TrackingResponse
from app.vfs_tracker import (
    capture_captcha_image,
    check_vfs_status,
    inspect_captcha_dom,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifespan – initialise logging
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, log_format=settings.log_format)

    logger.info(
        "app_startup",
        headless=settings.headless,
        supported_countries=list(VFS_TRACKING_URLS.keys()),
    )
    yield
    logger.info("app_shutdown")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VFS Tracking Bot",
    description="Check VFS Global passport/visa application tracking status via browser automation.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/v1/vfs-tracking/supported-countries")
async def supported_countries():
    """List all supported country keys."""
    return {"countries": list(VFS_TRACKING_URLS.keys())}


@app.get(
    "/v1/vfs-tracking/debug-captcha/{country}",
    responses={
        200: {"content": {"image/png": {}}, "description": "Raw captcha PNG"},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def debug_captcha(
    country: str = Path(..., description="Country key. See /supported-countries."),
    full: bool = Query(
        False,
        description="If true, return a FULL-PAGE screenshot instead of just the captcha.",
    ),
):
    """
    DEBUG: Open the country's tracking page and return a PNG image.

    - Default: just the captcha image the solver would see.
    - ?full=true: a full-page screenshot of whatever the browser rendered —
      use this to debug why the remote (Browserless) browser differs from local.

    Open this URL directly in a browser to eyeball the result.
    """
    settings = get_settings()
    tracking_url = get_tracking_url(country)
    if tracking_url is None:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{country}' is not supported. "
            f"Supported: {list(VFS_TRACKING_URLS.keys())}",
        )

    try:
        png_bytes = await capture_captcha_image(
            tracking_url, settings, full_page=full
        )
    except Exception as exc:
        logger.exception("debug_captcha_failed", country=country)
        raise HTTPException(
            status_code=500, detail=f"Failed to capture captcha: {exc}"
        ) from exc

    return Response(content=png_bytes, media_type="image/png")


@app.get("/v1/vfs-tracking/inspect-captcha/{country}")
async def inspect_captcha(
    country: str = Path(..., description="Country key. See /supported-countries."),
):
    """
    DEBUG: List every <img> on the country's tracking page and show which
    element the CAPTCHA_IMAGE selector currently resolves to.

    Use this to find the correct captcha selector when the captured
    screenshot looks wrong.
    """
    settings = get_settings()
    tracking_url = get_tracking_url(country)
    if tracking_url is None:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{country}' is not supported.",
        )

    try:
        return await inspect_captcha_dom(tracking_url, settings)
    except Exception as exc:
        logger.exception("inspect_captcha_failed", country=country)
        raise HTTPException(
            status_code=500, detail=f"Failed to inspect captcha: {exc}"
        ) from exc


@app.post(
    "/v1/vfs-tracking/check-status/{country}",
    response_model=TrackingResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def check_status(
    body: TrackingRequest,
    country: str = Path(
        ...,
        description="Country key (e.g. india, germany, uk). See /v1/vfs-tracking/supported-countries.",
    ),
):
    """
    Submit VFS application data and retrieve the tracking status.

    The backend will:
    1. Open the VFS tracking page for the given country.
    2. Fill in the reference number and last name.
    3. Solve the CAPTCHA via the configured solver chain (azapi → 2captcha → openai).
    4. Submit and return the status.
    """
    settings = get_settings()

    # Resolve country URL
    tracking_url = get_tracking_url(country)
    if tracking_url is None:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{country}' is not supported. "
            f"Supported: {list(VFS_TRACKING_URLS.keys())}",
        )

    log = logger.bind(country=country, reference_number=body.reference_number)
    log.info("tracking_request_received")

    try:
        result = await check_vfs_status(
            tracking_url=tracking_url,
            reference_number=body.reference_number,
            last_name=body.last_name,
            settings=settings,
        )
    except TrackingError as exc:
        log.warning("tracking_automation_error", error=str(exc))
        # When debug is requested, return 422 with the per-attempt captcha info
        # so the caller can see exactly what the solver read.
        if body.debug and getattr(exc, "debug_attempts", None):
            raise HTTPException(
                status_code=422,
                detail={"error": str(exc), "debug_attempts": exc.debug_attempts},
            ) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("tracking_unexpected_error")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during tracking check: {exc}",
        ) from exc

    return TrackingResponse(
        reference_number=body.reference_number,
        last_name=body.last_name,
        country=country.lower(),
        status=result["status"],
        status_details=result.get("status_details"),
        debug_attempts=result.get("debug_attempts") if body.debug else None,
    )


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("unhandled_exception", path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Entrypoint (for running directly: python -m app.main)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, loop="asyncio")
