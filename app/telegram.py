"""
Telegram notifications.

Two distinct channels share one bot token:
  * TELEGRAM_CHAT_ID      — applicant-facing notifications, sent ONLY when a
                            tracked status resolves (PENDING -> APPROVED/REJECTED).
  * TELEGRAM_LOG_CHAT_ID  — operational log, sent for EVERY status check so you
                            can confirm the Vercel cron is actually running.

All sends are best-effort: a Telegram failure must never break the cron sweep,
so callers wrap these in try/except (and they also swallow config-missing).
"""

from __future__ import annotations

import os

import httpx
import structlog

logger = structlog.get_logger(__name__)

_API = "https://api.telegram.org"


async def _send(chat_id: str, text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not chat_id:
        logger.warning("telegram_not_configured", has_token=bool(token), has_chat=bool(chat_id))
        return
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_API}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
        )
        resp.raise_for_status()


async def send_status_notification(reference_number: str, status: str, deal_id: str) -> None:
    """Notify that a tracked application resolved. Includes the CRM deal link."""
    deal_link = f"https://crm.travnook.com/crm/deal/details/{deal_id}"
    text = f"reference no : {reference_number}\nstatus : {status}\ndeal : {deal_link}"
    await _send(os.environ.get("TELEGRAM_CHAT_ID", "").strip(), text)


async def send_log(text: str) -> None:
    """Send an operational log line to the log channel."""
    await _send(os.environ.get("TELEGRAM_LOG_CHAT_ID", "").strip(), text)
