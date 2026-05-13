# VFS Tracking Bot

A production-ready Python backend service that checks VFS Global passport/visa tracking status through browser automation with OCR-based CAPTCHA solving.

## Architecture

```
app/
  main.py            # FastAPI application & endpoints
  config.py          # Environment settings & VFS URL mappings
  models.py          # Pydantic request/response schemas
  selectors.py       # Centralized page selectors (prioritized fallbacks)
  captcha_solver.py  # OCR-based CAPTCHA solving (Tesseract + Pillow)
  vfs_tracker.py     # Playwright browser automation
  logging_config.py  # Structured logging (structlog)
```

## Prerequisites

- Python 3.11+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
  - **Windows**: Download installer from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
  - **macOS**: `brew install tesseract`
  - **Linux**: `sudo apt install tesseract-ocr`

## Setup

```bash
# 1. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Create .env from example
cp .env.example .env
# Edit .env with your settings
```

## Environment Variables

| Variable             | Default                              | Description                              |
|----------------------|--------------------------------------|------------------------------------------|
| `HOST`               | `0.0.0.0`                           | Server bind address                      |
| `PORT`               | `8000`                               | Server port                              |
| `HEADLESS`           | `true`                               | Run browser headless (`true`/`false`)    |
| `BROWSER_TIMEOUT`    | `30000`                              | Playwright timeout in milliseconds       |
| `CAPTCHA_MAX_RETRIES`| `3`                                  | Max CAPTCHA solve attempts per request   |
| `TESSERACT_CMD`      | *(system default)*                   | Full path to Tesseract binary            |
| `LOG_LEVEL`          | `INFO`                               | Logging level (DEBUG, INFO, WARNING, etc)|
| `LOG_FORMAT`         | `json`                               | `json` for structured, `console` for dev |

## Running Locally

```bash
# Option A: via uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Option B: direct
python -m app.main
```

The API docs are available at: `http://localhost:8000/docs`

## Debugging with HEADLESS=false

To see the browser in action (useful for debugging selectors):

```bash
HEADLESS=false uvicorn app.main:app --reload
```

On Windows:
```powershell
$env:HEADLESS="false"
uvicorn app.main:app --reload
```

This opens a visible Chromium window so you can watch the automation fill forms and interact with the page.

## API Examples

### Health Check

```bash
curl http://localhost:8000/health
```

### List Supported Countries

```bash
curl http://localhost:8000/v1/vfs-tracking/supported-countries
```

### Check Tracking Status

```bash
curl -X POST http://localhost:8000/v1/vfs-tracking/check-status/india \
  -H "Content-Type: application/json" \
  -d '{
    "reference_number": "INND12345678",
    "last_name": "SHARMA"
  }'
```

**Response (success):**
```json
{
  "reference_number": "INND12345678",
  "last_name": "SHARMA",
  "country": "india",
  "status": "Your application is under process",
  "status_details": null
}
```

**Response (unsupported country):**
```json
{
  "detail": "Country 'xyz' is not supported. Supported: ['india', 'germany', 'uk', ...]"
}
```

## VFS Selector Maintenance

VFS Global periodically updates their website HTML. When the page structure changes, the automation may fail to locate form elements.

**How selectors work:**

All selectors are centralized in `app/selectors.py`. Each element has an ordered list of candidates tried in priority order:

1. **input ID** (most stable) - e.g., `#txtRefNo`
2. **input name** - e.g., `input[name='txtRefNo']`
3. **placeholder text** - e.g., `input[placeholder*='reference' i]`
4. **label association** - e.g., `label:has-text('Reference') >> xpath=../input`
5. **CSS/XPath fallback** - broader patterns as last resort

**When selectors break:**

1. Set `HEADLESS=false` and run a request to see the page.
2. Open browser DevTools (F12) and inspect the target element.
3. Update the selector candidates in `app/selectors.py` — add the new selector at the top of the list for highest priority.
4. Keep old selectors in the list as fallbacks (VFS may have different markup per country).

## Adding a New Country

Edit `VFS_TRACKING_URLS` in `app/config.py`:

```python
VFS_TRACKING_URLS["new_country"] = "https://visa.vfsglobal.com/xxx/en/yyy/track-application"
```

No code changes needed — the new country is immediately available via the API.
