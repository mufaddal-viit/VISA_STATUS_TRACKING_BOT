"""
MongoDB access for the visa watchlist.

Serverless note: Vercel reuses a "warm" Python process across many requests but
also spins up new ones freely. A new Motor client per request would open a fresh
connection pool every time and exhaust the Atlas connection limit. So we create
ONE client at module scope and reuse it for the lifetime of the process.
"""

from __future__ import annotations

import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

# Lazily-created singletons. Created on first use rather than at import time so
# importing this module never fails just because MONGODB_URI is unset (e.g. the
# captcha-only dev flow that doesn't touch the watchlist).
_client: AsyncIOMotorClient | None = None
_indexes_ready = False

COLLECTION_NAME = "visa_tracking"


def _get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI", "").strip()
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set")
        # maxPoolSize is deliberately small: serverless functions are
        # single-flight, so a large pool only wastes Atlas connections.
        _client = AsyncIOMotorClient(uri, maxPoolSize=5, tz_aware=True)
    return _client


def visa_tracking() -> AsyncIOMotorCollection:
    """Return the watchlist collection (uses the default DB from MONGODB_URI)."""
    db = _get_client().get_default_database(default="visa_tracker")
    return db[COLLECTION_NAME]


async def ensure_indexes() -> None:
    """
    Create the unique compound index that makes re-submitting the same
    (deal_id, reference_number) idempotent.

    create_index is itself idempotent, but it's still a network round-trip, so
    we guard it with a module flag to run it at most once per warm process.
    """
    global _indexes_ready
    if _indexes_ready:
        return
    await visa_tracking().create_index(
        [("deal_id", 1), ("reference_number", 1)],
        unique=True,
        name="uq_deal_reference",
    )
    _indexes_ready = True
