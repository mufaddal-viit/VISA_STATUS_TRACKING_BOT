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
        "#AppRefNo",
        "input[name='AppRefNo']",
        "input[placeholder='Application Reference Number']",
    ]
)

LAST_NAME_INPUT = SelectorGroup(
    candidates=[
        "input[name='LastName']",
        "input[placeholder='Last Name']",
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
        "#lblStatus",
        ".application-status",
        "[class*='status' i]",
        "#divResult",
        ".result",
        ".tracking-result",
        ".panel-body",
        "table.table tr",
        "#result",
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
