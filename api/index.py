"""
Vercel serverless entrypoint.

Vercel's Python runtime discovers an ASGI/WSGI `app` object exported from a
file inside the `api/` directory. We simply re-export the FastAPI app defined
in `app/main.py`.
"""

from app.main import app  # noqa: F401
