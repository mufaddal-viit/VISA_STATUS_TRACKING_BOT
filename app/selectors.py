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
        "#txtRefNo",
        "input[name='txtRefNo']",
        "input[placeholder*='reference' i]",
        "input[placeholder*='Reference' i]",
        "label:has-text('Reference') >> xpath=../input",
        "text=Reference Number >> xpath=../input",
        "#ApplicationId",
        "input[name='ApplicationId']",
        "input[id*='ref' i]",
        "input[name*='ref' i]",
    ]
)

LAST_NAME_INPUT = SelectorGroup(
    candidates=[
        "#txtLastName",
        "input[name='txtLastName']",
        "input[placeholder*='last name' i]",
        "input[placeholder*='Last Name' i]",
        "input[placeholder*='surname' i]",
        "label:has-text('Last Name') >> xpath=../input",
        "label:has-text('Surname') >> xpath=../input",
        "#LastName",
        "input[name='LastName']",
        "input[id*='last' i]",
        "input[name*='last' i]",
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
        "#txtCaptcha",
        "input[name='txtCaptcha']",
        "input[placeholder*='captcha' i]",
        "input[placeholder*='Captcha' i]",
        "input[placeholder*='code' i]",
        "label:has-text('Captcha') >> xpath=../input",
        "label:has-text('Security') >> xpath=../input",
        "#CaptchaInputText",
        "input[name='CaptchaInputText']",
        "input[id*='captcha' i]",
        "input[name*='captcha' i]",
    ]
)

SUBMIT_BUTTON = SelectorGroup(
    candidates=[
        "#btnSubmit",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Track')",
        "button:has-text('Check Status')",
        "a:has-text('Submit')",
        "#btnTrack",
        ".btn-submit",
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
        "#lblCaptchaError",
        ".captcha-error",
        ".validation-summary-errors",
        ".error-message",
        "[class*='error' i]",
        ".alert-danger",
    ]
)
