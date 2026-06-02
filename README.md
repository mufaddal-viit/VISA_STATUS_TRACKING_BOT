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

## Watchlist & twice-daily sweep

On top of the on-demand `check-status` endpoint, the service keeps a MongoDB
watchlist and re-checks every entry twice a day until it resolves. One
collection, one add endpoint, and a sweep job.

### Why the sweep runs on GitHub Actions (not Vercel cron)

Each row takes ~50–60s of slow browser work. On Vercel's **Hobby** plan that
runs into two hard limits: functions are killed at **60s** (so barely one row
fits), and Hobby cron jobs only fire ~once/day. So the sweep runs as a
**scheduled GitHub Actions workflow** instead — GitHub runners have no 60s cap
(6-hour limit) and it's free. Vercel only hosts the API (`POST /api/track`).

The sweep runs a **local headless Chromium on the runner**, *not* Browserless.
A full VFS check takes ~60s+, but the Browserless plan caps each session at 60s
and kills the check mid-status-read; the GitHub runner has no such limit (and
it's one less paid dependency). The workflow `playwright install`s Chromium and
leaves `BROWSERLESS_WS_ENDPOINT` unset so `check_vfs_status` launches locally.

### How it works

1. `POST /api/track` (on Vercel) upserts one document with `status="PENDING"`
   and returns `202 {"status": "tracking"}` immediately. **No checking here.**
2. Twice a day, the GitHub Actions workflow runs `python -m app.sweep`. It finds
   every `PENDING` document, checks each (≤2 at a time), and writes the resolved
   status back. When a status becomes terminal (`APPROVED`/`REJECTED`) it no
   longer matches the `PENDING` filter, so future sweeps skip it automatically.
3. When a status changes off `PENDING`, a Telegram notification is sent
   (reference number, status, CRM deal link). Separately, **every** check posts
   a one-line log to a second Telegram chat so you can confirm the sweep ran.
4. `GET /api/cron/check` (on Vercel, guarded by `CRON_SECRET`) runs the same
   sweep on demand — handy for a manual single-shot, but on Hobby it's killed at
   60s, so it's a backup trigger, not the scheduled job.

### Endpoints

```bash
# Add to the watchlist (idempotent on deal_id + reference_number)
curl -X POST https://<your-app>.vercel.app/api/track \
  -H "Content-Type: application/json" \
  -d '{
    "deal_id": "1262",
    "reference_number": "INND12345678",
    "last_name": "SHARMA",
    "country": "germany"
  }'
# -> 202 {"status": "tracking"}

# Run the sweep on demand (backup trigger; Bearer token must match CRON_SECRET)
curl https://<your-app>.vercel.app/api/cron/check \
  -H "Authorization: Bearer $CRON_SECRET"
# -> {"checked": 3, "resolved": 1}
```

### Dashboard

A read-only dashboard lives at **`GET /dashboard`** — a table of every tracked
application with its current status, the raw `status_text` (failures show as a
red `ERROR …`), when each row was last checked, plus summary counts and the
**last sweep run** and **next scheduled run**. It auto-refreshes every 30s and
is the app's home (`/` redirects here).

It's backed by **`GET /api/watchlist`** (JSON): `{ rows, summary, last_run,
next_run, server_time }`. The `last_run` data comes from a small **`sweep_runs`**
collection — one tiny document per sweep (start/finish + checked/resolved/errors).

The dashboard header links to **`/check-status`** (a one-off check that does
*not* save — 3 fields) and **`/add-tracking`** (saves to the watchlist via
`POST /api/track` — 4 fields incl. Deal ID), and has **Run sweep now**, which
triggers the GitHub Actions sweep on demand
via **`POST /api/run-sweep`** (GitHub's `workflow_dispatch` API). That endpoint
needs a **`GITHUB_TOKEN`** env var on the server — a fine-grained PAT with
"Actions: read and write" on the repo. Without it the button returns a clear
"not configured" message. Repo/workflow/branch are overridable via
`GITHUB_REPO`, `GITHUB_WORKFLOW_FILE`, `GITHUB_WORKFLOW_REF` (defaults target
this repo's `visa-sweep.yml` on `captcha-api`).

> `next_run` is derived from `SWEEP_UTC_HOURS` in `app/main.py`, which mirrors
> the cron in the workflow — keep the two in sync if you change the schedule.

> ⚠️ The dashboard, `/api/watchlist`, and `/api/run-sweep` are **unauthenticated**.
> The data includes reference numbers + last names (PII), and `run-sweep` starts
> a billable CI run. Put them behind auth before exposing the app publicly.

### Data model — collection `visa_tracking`

A **unique compound index on `(deal_id, reference_number)`** is created at
startup, so re-submitting the same deal is a no-op (`$setOnInsert`).

```jsonc
{
  "deal_id": "1262",
  "reference_number": "INND12345678",
  "last_name": "SHARMA",
  "country": "germany",
  "status": "PENDING",          // PENDING | APPROVED | REJECTED | NOT_FOUND
  "status_text": "Visa Application ... under process",  // raw VFS text (set after first check)
  "last_checked_at": null,      // UTC datetime, null until first check
  "created_at": "2026-06-01T08:00:00Z"
}
```

> **Status mapping:** VFS returns free text that varies by country. It's mapped
> to one of the three states by `classify_status()` in `app/sweep.py` — edit the
> keyword lists there if a country's wording slips through. Unrecognised text
> stays `PENDING` (retried) rather than being wrongly marked terminal.

### Scheduling (GitHub Actions)

The sweep is scheduled by [.github/workflows/visa-sweep.yml](.github/workflows/visa-sweep.yml),
which runs `python -m app.sweep` twice a day:

```yaml
schedule:
  - cron: "0 6 * * *"    # 10:00 Dubai (06:00 UTC)
  - cron: "0 13 * * *"   # 17:00 Dubai (13:00 UTC)
```

Cron is **UTC** (Dubai is UTC+4, no DST) and may be delayed a few minutes under GitHub load. You can also
run it on demand from the repo's **Actions** tab (`workflow_dispatch`).

> ⚠️ Scheduled workflows only run from the repository's **default branch**, so
> this file must be committed there for the schedule to fire.

### Env vars / secrets

The same variables are needed in two places — Vercel (for the API) and GitHub
Actions secrets (for the sweep):

| Variable                  | Where                    | Notes                                                        |
|---------------------------|--------------------------|--------------------------------------------------------------|
| `MONGODB_URI`             | Vercel + GitHub          | Include the DB name, e.g. `mongodb+srv://…/visa_tracker`      |
| `BROWSERLESS_WS_ENDPOINT` | Vercel only              | Remote browser for Vercel (can't run Chromium). The GitHub sweep uses a local Chromium, so **don't** set it there. |
| `TELEGRAM_BOT_TOKEN`      | Vercel + GitHub          | One bot, used for both chats                                  |
| `TELEGRAM_CHAT_ID`        | Vercel + GitHub          | Status-resolved notifications                                 |
| `TELEGRAM_LOG_CHAT_ID`    | Vercel + GitHub          | Per-check operational log                                     |
| `AZAPI_API_KEY` / `TWOCAPTCHA_API_KEY` / `OPENAI_API_KEY` | Vercel + GitHub | At least one captcha solver |
| `CRON_SECRET`             | Vercel only (auto-set)   | Guards the manual `/api/cron/check` trigger                  |

Add the GitHub ones under **Repo → Settings → Secrets and variables → Actions →
Secrets**. (`CAPTCHA_SOLVER` is optional — add it as a repo *Variable* if you
want to pin a single solver.)

> `CRON_SECRET` is **auto-set by Vercel** for the deployment. To call
> `/api/cron/check` manually, read its value from the Vercel dashboard and pass
> `Authorization: Bearer <value>` yourself. The GitHub sweep doesn't use it (it
> talks to Mongo/Browserless directly, not through the API).

### Deploy

```bash
# --- Vercel (API only) ---
npm i -g vercel && vercel login
vercel --prod
vercel env add MONGODB_URI            # + BROWSERLESS_WS_ENDPOINT, TELEGRAM_*, captcha keys

# --- GitHub Actions (the sweep) ---
# 1. Add the secrets above under Repo Settings → Secrets and variables → Actions.
# 2. Commit .github/workflows/visa-sweep.yml to the DEFAULT branch and push.
# 3. Confirm it works: Actions tab → "Visa status sweep" → Run workflow.
```

> **maxDuration:** `vercel.json` keeps `maxDuration: 60` — the Hobby max, enough
> for `POST /api/track` and the on-demand single-shot. The bulk sweep runs on
> GitHub Actions precisely because it can't fit in 60s.

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
