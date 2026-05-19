"""
Playwright-based VFS tracking automation.

Handles the full flow:
  1. Navigate to the tracking URL.
  2. Fill reference number and last name.
  3. Capture the CAPTCHA and solve it via the configured solver chain.
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
    async_playwright,
)

from app.captcha_solver import image_bytes_to_base64, solve_captcha_from_bytes
from app.config import Settings
from app.models import TrackingError
from app.selectors import (
    CAPTCHA_ERROR,
    CAPTCHA_IMAGE,
    CAPTCHA_INPUT,
    INVALID_INPUTS_ERROR,
    LAST_NAME_INPUT,
    RECAPTCHA_WIDGET,
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
        # Connect to a remote browser (Browserless.io) when configured —
        # required on serverless hosts (Vercel) that cannot run local Chromium.
        # Otherwise launch a local Chromium for dev / VPS deployments.
        if settings.use_remote_browser:
            log.info("connecting_remote_browser")
            browser = await pw.chromium.connect_over_cdp(
                settings.browserless_ws_endpoint,
                timeout=settings.browser_timeout,
            )
        else:
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

            # 2. Fill form fields (1s pause between fields to mimic human input)
            ref_input = await _resolve_selector_strict(
                page, REFERENCE_NUMBER_INPUT, "reference_number"
            )
            await ref_input.fill(reference_number)
            await page.wait_for_timeout(1000)

            last_name_input = await _resolve_selector_strict(
                page, LAST_NAME_INPUT, "last_name"
            )
            await last_name_input.fill(last_name)
            await page.wait_for_timeout(1000)

            log.info("form_filled")

            # 3. CAPTCHA loop (retry on incorrect CAPTCHA)
            captcha_b64: str | None = None
            debug_attempts: list[dict] = []

            for attempt in range(1, settings.captcha_max_retries + 1):
                log.info("captcha_attempt", attempt=attempt)
                attempt_rec: dict = {"attempt": attempt}
                debug_attempts.append(attempt_rec)

                # Capture CAPTCHA image element
                captcha_img = await _resolve_selector_strict(
                    page, CAPTCHA_IMAGE, "captcha_image"
                )
                captcha_bytes = await captcha_img.screenshot()
                captcha_b64 = image_bytes_to_base64(captcha_bytes)
                attempt_rec["captcha_b64"] = captcha_b64

                # Solve via configured solver (single if CAPTCHA_SOLVER is set,
                # otherwise chain: azapi → 2captcha → openai)
                try:
                    captcha_text = await solve_captcha_from_bytes(captcha_bytes, settings)
                except Exception as exc:
                    attempt_rec["error"] = f"solver error: {exc}"
                    raise
                attempt_rec["solved_text"] = captcha_text
                log.info("captcha_solved", text=captcha_text, attempt=attempt)

                # Fill CAPTCHA input
                captcha_input = await _resolve_selector_strict(
                    page, CAPTCHA_INPUT, "captcha_input"
                )
                await captcha_input.fill("")  # clear any previous value
                await captcha_input.fill(captcha_text)
                await page.wait_for_timeout(1000)

                # Submit
                submit_btn = await _resolve_selector_strict(
                    page, SUBMIT_BUTTON, "submit_button"
                )
                await submit_btn.click()

                # Wait for navigation / result
                await page.wait_for_load_state("networkidle")

                # Check for "Invalid Inputs." — wrong reference/last name. The page
                # also shows a reCAPTCHA v2 widget here which we cannot auto-solve,
                # so fail fast instead of retrying.
                invalid_inputs = await _resolve_selector(
                    page, INVALID_INPUTS_ERROR, timeout=500
                )
                if invalid_inputs:
                    has_recaptcha = await _resolve_selector(
                        page, RECAPTCHA_WIDGET, timeout=200
                    )
                    log.error(
                        "invalid_inputs_detected",
                        attempt=attempt,
                        recaptcha_present=bool(has_recaptcha),
                    )
                    raise TrackingError(
                        "Invalid Inputs: the reference number / last name combination "
                        "was rejected by VFS."
                        + (
                            " A reCAPTCHA challenge was also presented, which cannot "
                            "be solved automatically."
                            if has_recaptcha
                            else ""
                        )
                    )

                # Check for CAPTCHA error (element is rendered with the page, not async)
                captcha_err = await _resolve_selector(
                    page, CAPTCHA_ERROR, timeout=500
                )
                if captcha_err:
                    err_text = (await captcha_err.text_content() or "").strip()
                    if err_text and ("captcha" in err_text.lower() or "incorrect" in err_text.lower() or "invalid" in err_text.lower()):
                        attempt_rec["accepted"] = False
                        attempt_rec["error"] = err_text
                        log.warning(
                            "captcha_attempt_failed",
                            attempt=attempt,
                            submitted=captcha_text,
                            error_text=err_text,
                        )
                        if attempt < settings.captcha_max_retries:
                            # Some pages reload CAPTCHA automatically; wait a beat
                            await page.wait_for_timeout(1000)
                            continue
                        raise TrackingError(
                            f"CAPTCHA failed after {settings.captcha_max_retries} attempts",
                            debug_attempts=debug_attempts,
                        )

                # No CAPTCHA error – this attempt's captcha was accepted
                attempt_rec["accepted"] = True
                log.info(
                    "captcha_attempt_passed",
                    attempt=attempt,
                    submitted=captcha_text,
                )
                break

            # 4. Extract status
            status_text = await _extract_status(page)
            status_details = await _extract_status_details(page)

            log.info("vfs_check_complete", status=status_text)

            return {
                "status": status_text,
                "status_details": status_details,
                "captcha_b64": captcha_b64,
                "debug_attempts": debug_attempts,
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
# Debug helper — capture the captcha image only (no solving / no submit)
# ---------------------------------------------------------------------------

async def capture_captcha_image(tracking_url: str, settings: Settings) -> bytes:
    """Open the tracking page and return raw PNG bytes of the captcha image.

    Used by the debug endpoint to inspect exactly what the solver sees.
    """
    log = logger.bind(url=tracking_url)
    log.info("capture_captcha_start")

    async with async_playwright() as pw:
        if settings.use_remote_browser:
            browser = await pw.chromium.connect_over_cdp(
                settings.browserless_ws_endpoint, timeout=settings.browser_timeout
            )
        else:
            browser = await pw.chromium.launch(headless=settings.headless)

        context: BrowserContext | None = None
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            page.set_default_timeout(settings.browser_timeout)
            await page.goto(tracking_url, wait_until="networkidle")

            captcha_img = await _resolve_selector_strict(
                page, CAPTCHA_IMAGE, "captcha_image"
            )
            return await captcha_img.screenshot()
        finally:
            if context:
                await context.close()
            await browser.close()


async def inspect_captcha_dom(tracking_url: str, settings: Settings) -> dict:
    """Open the tracking page and report every <img> on it + the captcha selector hit.

    Used to figure out the correct captcha selector when the captured screenshot
    looks wrong (e.g. it captured a container div instead of the image).
    """
    log = logger.bind(url=tracking_url)
    log.info("inspect_captcha_dom_start")

    async with async_playwright() as pw:
        if settings.use_remote_browser:
            browser = await pw.chromium.connect_over_cdp(
                settings.browserless_ws_endpoint, timeout=settings.browser_timeout
            )
        else:
            browser = await pw.chromium.launch(headless=settings.headless)

        context: BrowserContext | None = None
        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            page.set_default_timeout(settings.browser_timeout)
            await page.goto(tracking_url, wait_until="networkidle")

            # Report every <img> on the page: tag, id, src, size, outer HTML.
            images = await page.eval_on_selector_all(
                "img",
                """els => els.map(e => ({
                    id: e.id,
                    src: (e.getAttribute('src') || '').slice(0, 120),
                    alt: e.alt,
                    width: e.width,
                    height: e.height,
                    naturalWidth: e.naturalWidth,
                    naturalHeight: e.naturalHeight,
                    outerHTML: e.outerHTML.slice(0, 300)
                }))""",
            )

            # What the current CAPTCHA_IMAGE selector chain resolves to.
            resolved: dict | None = None
            for selector in CAPTCHA_IMAGE.candidates:
                loc = page.locator(selector).first
                try:
                    await loc.wait_for(state="visible", timeout=2000)
                    box = await loc.bounding_box()
                    tag = await loc.evaluate("e => e.tagName")
                    html = await loc.evaluate("e => e.outerHTML.slice(0, 300)")
                    resolved = {
                        "matched_selector": selector,
                        "tag": tag,
                        "bounding_box": box,
                        "outerHTML": html,
                    }
                    break
                except Exception:
                    continue

            return {
                "tracking_url": tracking_url,
                "all_images": images,
                "captcha_selector_resolved": resolved,
            }
        finally:
            if context:
                await context.close()
            await browser.close()


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
