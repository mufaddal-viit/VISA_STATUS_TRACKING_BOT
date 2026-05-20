"""
Centralized VFS page selectors.

Each selector is a list ordered by priority (most reliable first).
The automation helper tries each in order until one resolves on the page.

Selector strategies (in priority order):
  1. input id
  2. input name
  3. placeholder text
  4. label text
  5. CSS / XPath fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SelectorGroup:
    """An ordered list of Playwright-compatible selectors for a single element."""

    candidates: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# VFS tracking-page selectors
# ---------------------------------------------------------------------------

REFERENCE_NUMBER_INPUT = SelectorGroup(
    candidates=[
        # New (current) VFS markup, e.g.
        #   <input id="RefNo" name="RefNo" placeholder="Reference Number" ...>
        "#RefNo",
        "input[name='RefNo']",
        "input[placeholder='Reference Number']",
        # Legacy markup — kept as fallback in case some country pages
        # are still on the older template.
        "#AppRefNo",
        "input[name='AppRefNo']",
        "input[placeholder='Application Reference Number']",
    ]
)

LAST_NAME_INPUT = SelectorGroup(
    candidates=[
        # name='LastName' is the most stable across VFS country pages and
        # has no whitespace gotcha — try it first so the fast path is O(1).
        "input[name='LastName']",
        # Current markup uses id="Last Name" (with a literal space — yes,
        # VFS really did that). `#LastName` will NOT match this; we need
        # an attribute selector or a CSS-escaped id.
        "input[id='Last Name']",
        "#LastName",  # legacy markup, kept as fallback
        "input[placeholder='Last Name']",
        # Common alternates seen on a few country sites.
        "input[name='Surname']",
        "#Surname",
        "input[placeholder='Surname']",
    ]
)

CAPTCHA_IMAGE = SelectorGroup(
    candidates=[
        "#CaptchaImage",
        "img[id*='captcha' i]",
        "img[id*='Captcha' i]",
        "img[alt*='captcha' i]",
        "img[src*='captcha' i]",
        "img[src*='Captcha' i]",
        ".captcha-image img",
        "#captcha img",
        ".captcha img",
    ]
)

CAPTCHA_INPUT = SelectorGroup(
    candidates=[
        "#CaptchaInputText",
        "input[name='CaptchaInputText']",
    ]
)

SUBMIT_BUTTON = SelectorGroup(
    candidates=[
        "#submitButton",
        "input[type='submit'][value='Submit']",
        "input[type='submit']",
    ]
)

STATUS_RESULT = SelectorGroup(
    candidates=[
        # VFS renders the result as a blue, bold one-liner, e.g.
        #   <div style="color: blue;">
        #     <b>Visa Application has been submitted and is under process
        #        at the Visa Application Centre.</b>
        #   </div>
        # We target the <b> directly so text_content() yields just the
        # status message (no stray whitespace from the wrapping div).
        # The "Invalid Inputs." error uses the same blue-bold pattern, so
        # we exclude it explicitly to avoid mis-classifying a rejection
        # as a status.
        "div[style*='color: blue'] > b:not(:has-text('Invalid Inputs'))",
        "div[style*='color:blue'] > b:not(:has-text('Invalid Inputs'))",
        # Looser fall-backs in case VFS tweaks the markup but keeps the wording.
        "b:has-text('Visa Application')",
        "b:has-text('under process')",
        "b:has-text('Application has been')",
        # Legacy / other-country layouts (kept last — none of these were
        # ever observed in production but they are cheap to try).
        "#lblStatus",
        ".application-status",
        "#divResult",
        ".tracking-result",
    ]
)

STATUS_DETAIL = SelectorGroup(
    candidates=[
        "#lblStatusDetail",
        ".status-detail",
        ".application-detail",
        "#divResultDetail",
        ".tracking-detail",
    ]
)

CAPTCHA_ERROR = SelectorGroup(
    candidates=[
        ".validation-summary-errors",
    ]
)

# Shown when the reference number / last name combination is rejected.
# Page renders: <div style="color: blue;"><b>Invalid Inputs.</b>...</div>
# A reCAPTCHA v2 widget also appears alongside this — we cannot solve it,
# so detect and fail fast instead of retrying.
INVALID_INPUTS_ERROR = SelectorGroup(
    candidates=[
        "div:has(> b:has-text('Invalid Inputs'))",
        "b:has-text('Invalid Inputs')",
    ]
)

RECAPTCHA_WIDGET = SelectorGroup(
    candidates=[
        ".g-recaptcha",
        "iframe[src*='recaptcha']",
    ]
)
