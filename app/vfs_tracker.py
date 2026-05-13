"""
Playwright-based VFS tracking automation.

Handles the full flow:
  1. Navigate to the tracking URL.
  2. Fill reference number and last name.
  3. Capture and OCR-solve the CAPTCHA.
  4. Submit the form.
  5. Detect incorrect-CAPTCHA errors and retry.
  6. Extract the application status text.
"""

from __future__ import annotations

import structlog
from playwright.async_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from app.captcha_solver import image_bytes_to_base64, solve_captcha_from_bytes
from app.config import Settings
from app.models import TrackingError
from app.selectors import (
    CAPTCHA_ERROR,
    CAPTCHA_IMAGE,
    CAPTCHA_INPUT,
    LAST_NAME_INPUT,
    REFERENCE_NUMBER_INPUT,
    STATUS_DETAIL,
    STATUS_RESULT,
    SUBMIT_BUTTON,
    SelectorGroup,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Selector resolution helper
# ---------------------------------------------------------------------------

async def _resolve_selector(page: Page, group: SelectorGroup, timeout: int = 5000) -> Locator | None:
    """Try each candidate selector and return the first visible locator found."""
    for selector in group.candidates:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception:
            continue
    return None


async def _resolve_selector_strict(
    page: Page, group: SelectorGroup, name: str, timeout: int = 10000
) -> Locator:
    """Like _resolve_selector but raises if nothing found."""
    locator = await _resolve_selector(page, group, timeout=timeout)
    if locator is None:
        raise TrackingError(
            f"Could not locate element '{name}' on page. "
            f"Tried selectors: {group.candidates}"
        )
    return locator


# ---------------------------------------------------------------------------
# Core automation
# ---------------------------------------------------------------------------

async def check_vfs_status(
    tracking_url: str,
    reference_number: str,
    last_name: str,
    settings: Settings,
) -> dict:
    """
    Perform the full VFS tracking check and return the result dict.

    Returns
    -------
    dict with keys: status, status_details, captcha_b64
    """
    log = logger.bind(reference_number=reference_number)
    log.info("vfs_check_start", url=tracking_url)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=settings.headless)
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(settings.browser_timeout)

            # 1. Navigate
            await page.goto(tracking_url, wait_until="networkidle")
            log.info("page_loaded")

            # 2. Fill form fields
            ref_input = await _resolve_selector_strict(
                page, REFERENCE_NUMBER_INPUT, "reference_number"
            )
            await ref_input.fill(reference_number)

            last_name_input = await _resolve_selector_strict(
                page, LAST_NAME_INPUT, "last_name"
            )
            await last_name_input.fill(last_name)

            log.info("form_filled")

            # 3. CAPTCHA loop (retry on incorrect CAPTCHA)
            captcha_b64: str | None = None

            for attempt in range(1, settings.captcha_max_retries + 1):
                log.info("captcha_attempt", attempt=attempt)

                # Capture CAPTCHA image element
                captcha_img = await _resolve_selector_strict(
                    page, CAPTCHA_IMAGE, "captcha_image"
                )
                captcha_bytes = await captcha_img.screenshot()
                captcha_b64 = image_bytes_to_base64(captcha_bytes)

                # Solve via OCR
                captcha_text = solve_captcha_from_bytes(captcha_bytes)
                log.info("captcha_solved", text=captcha_text, attempt=attempt)

                # Fill CAPTCHA input
                captcha_input = await _resolve_selector_strict(
                    page, CAPTCHA_INPUT, "captcha_input"
                )
                await captcha_input.fill("")  # clear any previous value
                await captcha_input.fill(captcha_text)

                # Submit
                submit_btn = await _resolve_selector_strict(
                    page, SUBMIT_BUTTON, "submit_button"
                )
                await submit_btn.click()

                # Wait for navigation / result
                await page.wait_for_load_state("networkidle")

                # Check for CAPTCHA error
                captcha_err = await _resolve_selector(
                    page, CAPTCHA_ERROR, timeout=3000
                )
                if captcha_err:
                    err_text = (await captcha_err.text_content() or "").strip()
                    if err_text and ("captcha" in err_text.lower() or "incorrect" in err_text.lower() or "invalid" in err_text.lower()):
                        log.warning(
                            "captcha_incorrect",
                            attempt=attempt,
                            error_text=err_text,
                        )
                        if attempt < settings.captcha_max_retries:
                            # Some pages reload CAPTCHA automatically; wait a beat
                            await page.wait_for_timeout(1000)
                            continue
                        raise TrackingError(
                            f"CAPTCHA failed after {settings.captcha_max_retries} attempts"
                        )

                # No CAPTCHA error – we should have a result
                break

            # 4. Extract status
            status_text = await _extract_status(page)
            status_details = await _extract_status_details(page)

            log.info("vfs_check_complete", status=status_text)

            return {
                "status": status_text,
                "status_details": status_details,
                "captcha_b64": captcha_b64,
            }

        except Exception:
            # Capture a full-page screenshot for debugging on failure
            if page:
                try:
                    debug_shot = await page.screenshot(full_page=True)
                    debug_b64 = image_bytes_to_base64(debug_shot)
                    log.error("vfs_check_failed", debug_screenshot_b64=debug_b64[:100] + "...")
                except Exception:
                    pass
            raise

        finally:
            if context:
                await context.close()
            await browser.close()
            log.info("browser_closed")


# ---------------------------------------------------------------------------
# Status extraction helpers
# ---------------------------------------------------------------------------

async def _extract_status(page: Page) -> str:
    """Pull the main status text from the results area."""
    locator = await _resolve_selector(page, STATUS_RESULT, timeout=10000)
    if locator is None:
        # Fallback: try to find any prominent text on the page that looks like a status
        body_text = await page.inner_text("body")
        for keyword in ("Your application status", "Status:", "Application Status"):
            idx = body_text.find(keyword)
            if idx != -1:
                snippet = body_text[idx : idx + 300].strip()
                return snippet
        raise TrackingError("Could not find application status on the page")

    text = (await locator.text_content() or "").strip()
    if not text:
        text = (await locator.inner_text()).strip()
    return text


async def _extract_status_details(page: Page) -> str | None:
    """Pull additional detail text if present."""
    locator = await _resolve_selector(page, STATUS_DETAIL, timeout=3000)
    if locator is None:
        return None
    text = (await locator.text_content() or "").strip()
    return text if text else None
