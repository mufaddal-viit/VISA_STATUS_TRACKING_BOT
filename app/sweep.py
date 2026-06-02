"""
The watchlist sweep — find every PENDING application, check it, write the result
back, and fire Telegram notifications.

This is the heart of the twice-daily job. It lives in its own module so it can
run in TWO places from ONE implementation:

  * `GET /api/cron/check` (app/main.py) — an auth'd manual/backup trigger.
  * `python -m app.sweep` — the primary trigger, run by GitHub Actions, which
    has no 60s function limit (Vercel's Hobby cap can't fit even one ~55s row
    reliably, let alone many).

Concurrency is capped at MAX_CONCURRENCY because Browserless.io only allows a
small number of simultaneous browser sessions on our plan; exceeding it just
gets connections rejected.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from app import telegram
from app.config import get_settings, get_tracking_url
from app.db import ensure_indexes, sweep_runs, visa_tracking
from app.models import TrackingError
from app.vfs_tracker import check_vfs_status

logger = structlog.get_logger(__name__)

# Watchlist states. Only PENDING docs are re-checked every sweep; all the other
# (terminal) states drop out of the PENDING filter so they're never checked
# again. NOT_FOUND means VFS doesn't recognise the reference (usually a typo) —
# terminal so a bad reference doesn't loop forever; surfaces for a human to fix.
PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
NOT_FOUND = "NOT_FOUND"

# How many rows to check at once. The sweep runs local headless Chromium on the
# GitHub runner (2 vCPUs), so keep this small; 2 is comfortable. (If a run ever
# uses Browserless instead, this must also stay within that plan's session cap.)
MAX_CONCURRENCY = 2


def classify_status(status_text: str) -> str:
    """
    Map the free-text status returned by VFS into one of our watchlist states.

    VFS phrasing varies by country, so this is intentionally keyword-based and
    lives in one place — tweak the marker lists here if a country's wording
    slips through. Unrecognised text stays PENDING so it's retried rather than
    wrongly marked terminal.
    """
    t = (status_text or "").lower()
    # "NO RECORDS FOUND" — VFS doesn't know this reference (usually a typo).
    # Terminal so it stops being re-checked every sweep.
    if "no record" in t:
        return NOT_FOUND
    # Order matters: "not approved" contains "approved", so check rejection first.
    if any(m in t for m in ("reject", "refus", "not approved", "declin")):
        return REJECTED
    if any(
        m in t
        for m in ("under process", "in process", "is under", "being processed", "submitted")
    ):
        return PENDING
    if any(
        m in t
        for m in (
            "approved",
            "ready for collection",
            "ready to collect",
            "available for collection",
            "dispatched",
            "decision has been made",
            "completed",
        )
    ):
        return APPROVED
    return PENDING


async def _check_one(doc, settings, coll, counters: dict, sem: asyncio.Semaphore) -> None:
    """Check a single watchlist row. Never raises — one bad row must not abort the sweep."""
    async with sem:  # bound concurrent browserless sessions
        ref = doc["reference_number"]
        country = doc.get("country", "")
        log = logger.bind(reference_number=ref, country=country)
        # Safe to mutate without a lock: asyncio is single-threaded and there's
        # no await between the read and the write.
        counters["checked"] += 1
        try:
            tracking_url = get_tracking_url(country)
            if tracking_url is None:
                raise TrackingError(f"Unsupported country '{country}'")

            result = await check_vfs_status(
                tracking_url=tracking_url,
                reference_number=ref,
                last_name=doc["last_name"],
                settings=settings,
            )
            status_text = result["status"]
            new_status = classify_status(status_text)

            await coll.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "status": new_status,
                        "status_text": status_text,
                        "last_checked_at": datetime.now(timezone.utc),
                    }
                },
            )

            log.info("sweep_checked", new_status=new_status, status_text=status_text)
            # Operational log to Telegram for EVERY check, so you can see the sweep ran.
            await _safe_log(f"checked {ref} ({country}) -> {new_status}: {status_text}")

            if new_status != PENDING:
                counters["resolved"] += 1
                await _safe_notify(ref, status_text, doc["deal_id"])

        except Exception as exc:  # noqa: BLE001 — contain failures to this one row
            # Record the error in status_text (prefixed + truncated) and stamp the
            # attempt, so a failing row is visible. Status stays PENDING so it's
            # retried next sweep — most check failures (slow site, captcha miss,
            # timeout) are transient and shouldn't permanently stop tracking.
            log.warning("sweep_check_failed", error=str(exc))
            try:
                await coll.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "status_text": f"ERROR: {str(exc)[:500]}",
                            "last_checked_at": datetime.now(timezone.utc),
                        }
                    },
                )
            except Exception:  # noqa: BLE001 — e.g. Mongo write itself failed
                logger.warning("sweep_error_write_failed", exc_info=True)
            counters["errors"] += 1
            await _safe_log(f"error checking {ref} ({country}): {exc}")


async def run_sweep() -> dict:
    """Check every PENDING row (≤ MAX_CONCURRENCY at a time) and return a summary."""
    await ensure_indexes()
    settings = get_settings()
    coll = visa_tracking()

    started_at = datetime.now(timezone.utc)
    pending = await coll.find({"status": PENDING}).to_list(length=None)
    counters = {"checked": 0, "resolved": 0, "errors": 0}
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    await asyncio.gather(
        *(_check_one(doc, settings, coll, counters, sem) for doc in pending)
    )

    # Record this run so the dashboard can show "last run / last successful run".
    # Best-effort: never let a history-write failure fail the sweep itself.
    run = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc),
        "checked": counters["checked"],
        "resolved": counters["resolved"],
        "errors": counters["errors"],
    }
    try:
        await sweep_runs().insert_one(dict(run))
    except Exception:  # noqa: BLE001
        logger.warning("sweep_run_record_failed", exc_info=True)

    logger.info("sweep_complete", **counters)
    return {
        "checked": counters["checked"],
        "resolved": counters["resolved"],
        "errors": counters["errors"],
    }


async def _safe_log(text: str) -> None:
    """Best-effort Telegram log — a notification failure must not break the sweep."""
    try:
        await telegram.send_log(text)
    except Exception:
        logger.warning("telegram_log_failed", exc_info=True)


async def _safe_notify(reference_number: str, status: str, deal_id: str) -> None:
    """Best-effort Telegram status notification."""
    try:
        await telegram.send_status_notification(reference_number, status, deal_id)
    except Exception:
        logger.warning("telegram_notify_failed", exc_info=True)


def _main() -> None:
    """Entry point for `python -m app.sweep` (used by GitHub Actions)."""
    import sys

    # Playwright's async driver spawns a Node subprocess, which on Windows needs
    # the ProactorEventLoop (no-op on the Linux GitHub Actions runner).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    from app.logging_config import setup_logging

    settings = get_settings()
    setup_logging(log_level=settings.log_level, log_format=settings.log_format)

    result = asyncio.run(run_sweep())
    logger.info("sweep_result", **result)
    print(result)


if __name__ == "__main__":
    _main()
