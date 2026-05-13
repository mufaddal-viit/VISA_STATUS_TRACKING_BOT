"""
OCR-based CAPTCHA solver.

Extracts text from a CAPTCHA image using Tesseract OCR with image
pre-processing (grayscale, contrast boost, thresholding) to improve
recognition accuracy.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import structlog
from PIL import Image, ImageFilter, ImageOps

from app.models import TrackingError

logger = structlog.get_logger(__name__)

# Directory where debug images are saved (created on first use)
DEBUG_DIR = Path("debug_captcha")


def _preprocess_image(img: Image.Image) -> Image.Image:
    """
    Preprocess for blue-text-on-white-noise CAPTCHAs (VFS Global style).

    Strategy: isolate the blue channel (letters are dark-blue, background is
    light/white) then invert so letters become dark on white for Tesseract.
    """
    img = img.convert("RGB")

    # Extract the blue channel — blue letters have high B relative to R/G
    # Use (B - max(R,G)) to isolate blue-dominant pixels
    r, g, b = img.split()

    import PIL.ImageChops as chops
    # blue_dominance = B channel minus the max of R,G channels
    # high value → blue pixel (letter); low/negative → background noise
    max_rg = chops.lighter(r, g)
    blue_dominance = chops.difference(b, max_rg)  # bright where blue dominates

    # Scale up for better character recognition
    blue_dominance = blue_dominance.resize(
        (blue_dominance.width * 3, blue_dominance.height * 3), Image.LANCZOS
    )

    # Boost contrast so letter pixels separate cleanly from noise
    blue_dominance = ImageOps.autocontrast(blue_dominance, cutoff=2)

    # Smooth salt-and-pepper noise
    blue_dominance = blue_dominance.filter(ImageFilter.MedianFilter(size=3))

    # Binarize: blue-dominant pixels are bright → invert so letters are black
    threshold = 80
    blue_dominance = blue_dominance.point(lambda p: 0 if p > threshold else 255, mode="L")

    # Dilate: expand dark pixels so dotted letter strokes merge into solid shapes.
    # MaxFilter on inverted image = dilation of dark regions.
    blue_dominance = ImageOps.invert(blue_dominance)
    blue_dominance = blue_dominance.filter(ImageFilter.MaxFilter(size=3))
    blue_dominance = blue_dominance.filter(ImageFilter.MaxFilter(size=3))
    blue_dominance = ImageOps.invert(blue_dominance)

    # Erode once to shrink isolated noise dots back to nothing while
    # preserving the now-solid letter strokes.
    blue_dominance = ImageOps.invert(blue_dominance)
    blue_dominance = blue_dominance.filter(ImageFilter.MinFilter(size=3))
    blue_dominance = ImageOps.invert(blue_dominance)

    return blue_dominance


def _clean_ocr_text(raw: str) -> str:
    """Strip whitespace and keep only alphanumeric characters."""
    return re.sub(r"[^A-Za-z0-9]", "", raw).strip()


def solve_captcha_from_bytes(image_bytes: bytes) -> str:
    """
    Solve a CAPTCHA given its raw image bytes.

    Saves the raw and preprocessed images to debug_captcha/ for inspection.
    Returns the cleaned OCR text.
    Raises TrackingError if OCR produces no usable text.
    """
    try:
        import pytesseract
    except ImportError as exc:
        raise TrackingError(
            "pytesseract is not installed. Run: pip install pytesseract"
        ) from exc

    img = Image.open(io.BytesIO(image_bytes))

    # Save raw image for debugging
    DEBUG_DIR.mkdir(exist_ok=True)
    img.save(DEBUG_DIR / "captcha_raw.png")

    processed = _preprocess_image(img)
    processed.save(DEBUG_DIR / "captcha_processed.png")

    # PSM 7 = single text line; OEM 3 = default (LSTM)
    custom_config = r"--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    raw_text = pytesseract.image_to_string(processed, config=custom_config)

    result = _clean_ocr_text(raw_text)
    logger.info("captcha_ocr_result", raw=raw_text.strip(), cleaned=result)

    if not result:
        raise TrackingError("OCR returned empty text for CAPTCHA image")

    return result


def solve_captcha_from_base64(b64_image: str) -> str:
    """Convenience wrapper that accepts a base64-encoded PNG string."""
    image_bytes = base64.b64decode(b64_image)
    return solve_captcha_from_bytes(image_bytes)


def image_bytes_to_base64(image_bytes: bytes) -> str:
    """Encode raw image bytes to a base64 string."""
    return base64.b64encode(image_bytes).decode("utf-8")
