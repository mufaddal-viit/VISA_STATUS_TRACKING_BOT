"""
VFS Global Tracking Bot – FastAPI application.

Run with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

# Playwright's async driver spawns a Node subprocess, which on Windows requires
# the ProactorEventLoop (the Selector loop raises NotImplementedError for
# subprocesses). No-op off Windows (e.g. Vercel/GitHub Linux runners).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from pathlib import Path as _FsPath

import httpx
import structlog
from fastapi import FastAPI, Header, HTTPException, Path, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.config import VFS_TRACKING_URLS, get_settings, get_tracking_url
from app.db import ensure_indexes, sweep_runs, visa_tracking
from app.logging_config import setup_logging
from app.sweep import PENDING, run_sweep
from app.models import (
    ErrorResponse,
    TrackingError,
    TrackingRequest,
    TrackingResponse,
    TrackRequest,
)
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

    # Create the unique (deal_id, reference_number) index at startup. Wrapped so
    # a missing/unreachable MongoDB never blocks the captcha-only endpoints; the
    # watchlist endpoints also re-attempt this lazily on first use.
    try:
        await ensure_indexes()
    except Exception:
        logger.warning("index_setup_skipped", exc_info=True)

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


_STATIC_DIR = _FsPath(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def index():
    """Root → the dashboard (the hub; check-status / add-tracking link from there)."""
    return RedirectResponse(url="/dashboard")


@app.get("/check-status", include_in_schema=False)
async def check_status_page():
    """One-off status check form (does NOT save to the watchlist)."""
    return FileResponse(_STATIC_DIR / "check-status.html")


@app.get("/add-tracking", include_in_schema=False)
async def add_tracking_page():
    """Add-to-watchlist form (4 fields → POST /api/track)."""
    return FileResponse(_STATIC_DIR / "add-tracking.html")


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    """Serve the favicon. Modern browsers prefer SVG and scale it perfectly."""
    return FileResponse(_STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    """Fallback for clients that still hard-request /favicon.ico — serve the
    same SVG. All current browsers accept SVG content under the .ico path."""
    return FileResponse(_STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


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

    # NOTE: vfsvisaonline.com countries (Sweden, Denmark, etc.) use the SAME
    # tracking-page template as vfsglobal.com (same selectors, same image
    # captcha), so they go through the identical flow below. On Vercel's 60s
    # cap a slow check may still time out — the watchlist sweep on GitHub
    # Actions is the reliable path for these.

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
    except PlaywrightTimeoutError as exc:
        # Any Playwright timeout that wasn't caught and converted to a
        # TrackingError inside check_vfs_status — surface as a clean,
        # client-friendly 422 instead of a raw 500.
        log.warning("tracking_timeout", error=str(exc))
        raise HTTPException(
            status_code=422,
            detail=(
                "The VFS tracking site is responding too slowly to complete the check. "
                "Please try again in a few minutes."
            ),
        ) from exc
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
# Watchlist: add-to-track + twice-daily cron sweep
# ---------------------------------------------------------------------------

@app.post("/api/track", status_code=202)
async def track(body: TrackRequest):
    """
    Add an application to the watchlist and return immediately (202).

    No checking happens here — the twice-daily cron does that. Upsert with
    $setOnInsert makes re-submitting the same (deal_id, reference_number) a
    no-op, so the caller can fire this idempotently.
    """
    await ensure_indexes()
    await visa_tracking().update_one(
        {"deal_id": body.deal_id, "reference_number": body.reference_number},
        {
            "$setOnInsert": {
                "deal_id": body.deal_id,
                "reference_number": body.reference_number,
                "last_name": body.last_name,
                "country": body.country.lower().strip(),
                "status": PENDING,
                "last_checked_at": None,
                "created_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    return {"status": "tracking"}


@app.get("/api/cron/check")
async def cron_check(authorization: str | None = Header(default=None)):
    """
    Manual / backup trigger for the watchlist sweep, guarded by CRON_SECRET.

    NOTE: the *primary* trigger is the GitHub Actions workflow
    (`python -m app.sweep`), which has no 60s function limit. On Vercel's Hobby
    plan this endpoint will be killed at 60s, so it only fully clears the
    watchlist when there are very few PENDING rows — it's here for manual
    single-shot runs and debugging, not the scheduled job.
    """
    expected = os.environ.get("CRON_SECRET", "")
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await run_sweep()


# ---------------------------------------------------------------------------
# Dashboard — read-only view of the watchlist
# ---------------------------------------------------------------------------

# The two daily sweep times in UTC. Mirrors the cron in
# .github/workflows/visa-sweep.yml (10:00 & 17:00 Dubai = 06:00 & 13:00 UTC).
# Used only to show "next run" on the dashboard.
SWEEP_UTC_HOURS = (6, 13)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _display_status(status: str, status_text: str | None) -> str:
    """The status shown in the UI. A PENDING row whose last check errored is
    surfaced as ERROR so failures are visible at a glance."""
    if status == PENDING and isinstance(status_text, str) and status_text.startswith("ERROR:"):
        return "ERROR"
    return status


def _next_run_utc(now: datetime) -> datetime:
    """Next scheduled sweep at or after `now`, from SWEEP_UTC_HOURS."""
    candidates = [
        (now + timedelta(days=d)).replace(hour=h, minute=0, second=0, microsecond=0)
        for d in (0, 1)
        for h in SWEEP_UTC_HOURS
    ]
    return min(t for t in candidates if t > now)


@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    """Serve the watchlist dashboard (single-file HTML, fetches /api/watchlist)."""
    return FileResponse(_STATIC_DIR / "dashboard.html")


@app.get("/api/watchlist")
async def watchlist():
    """All watchlist rows + a summary, last sweep run, and next scheduled run."""
    docs = await visa_tracking().find({}).sort("created_at", -1).to_list(length=None)

    rows = []
    counts: dict[str, int] = {}
    for d in docs:
        display = _display_status(d.get("status", PENDING), d.get("status_text"))
        counts[display] = counts.get(display, 0) + 1
        rows.append(
            {
                "deal_id": d.get("deal_id"),
                "reference_number": d.get("reference_number"),
                "last_name": d.get("last_name"),
                "country": d.get("country"),
                "status": d.get("status"),
                "display_status": display,
                "status_text": d.get("status_text"),
                "last_checked_at": _iso(d.get("last_checked_at")),
                "created_at": _iso(d.get("created_at")),
            }
        )

    last_run_doc = await sweep_runs().find_one(sort=[("finished_at", -1)])
    last_run = (
        {
            "started_at": _iso(last_run_doc.get("started_at")),
            "finished_at": _iso(last_run_doc.get("finished_at")),
            "checked": last_run_doc.get("checked"),
            "resolved": last_run_doc.get("resolved"),
            "errors": last_run_doc.get("errors"),
        }
        if last_run_doc
        else None
    )

    now = datetime.now(timezone.utc)
    return {
        "rows": rows,
        "summary": {"total": len(rows), "by_status": counts},
        "last_run": last_run,
        "next_run": _iso(_next_run_utc(now)),
        "server_time": _iso(now),
    }


# ---------------------------------------------------------------------------
# Manually trigger the GitHub Actions sweep (workflow_dispatch)
# ---------------------------------------------------------------------------

# Where the sweep workflow lives. Overridable via env; defaults match this repo.
GITHUB_REPO = os.environ.get("GITHUB_REPO", "mufaddal-viit/VISA_STATUS_TRACKING_BOT")
GITHUB_WORKFLOW_FILE = os.environ.get("GITHUB_WORKFLOW_FILE", "visa-sweep.yml")
GITHUB_WORKFLOW_REF = os.environ.get("GITHUB_WORKFLOW_REF", "captcha-api")


@app.post("/api/run-sweep")
async def run_sweep_dispatch():
    """
    Kick off the GitHub Actions sweep immediately (the same job that runs on
    schedule), via GitHub's workflow_dispatch API.

    Requires a GITHUB_TOKEN env var — a fine-grained PAT with "Actions:
    read and write" on the repo. The workflow file must exist on
    GITHUB_WORKFLOW_REF (the default branch). Returns 202 on dispatch; watch the
    repo's Actions tab for the run.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_TOKEN is not configured on the server, so the sweep "
            "can't be triggered from here. Run it from the GitHub Actions tab instead.",
        )

    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}"
        f"/actions/workflows/{GITHUB_WORKFLOW_FILE}/dispatches"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={"ref": GITHUB_WORKFLOW_REF},
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {exc}") from exc

    # GitHub returns 204 No Content on a successful dispatch.
    if resp.status_code == 204:
        logger.info("sweep_dispatched", ref=GITHUB_WORKFLOW_REF)
        return JSONResponse(
            status_code=202,
            content={"status": "dispatched", "ref": GITHUB_WORKFLOW_REF},
        )
    raise HTTPException(
        status_code=502,
        detail=f"GitHub dispatch failed ({resp.status_code}): {resp.text[:300]}",
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
