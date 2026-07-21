"""
scraper_service.py
──────────────────
Public entry-point for the scraping pipeline.

  run_scraper(filters, max_jobs)   ← sync wrapper — called by Celery tasks
  run_scraper_async(filters, max_jobs)  ← native async coroutine

Celery workers are synchronous Python threads, so they call the sync wrapper
which uses asyncio.run() to execute the async pipeline inside a fresh event
loop.  FastAPI async endpoints can await run_scraper_async() directly.

Pipeline:
  get_all_pages_async()  →  parse_jobs()  →  [list of clean job dicts]
"""

import asyncio
from app.scraper.pagination import get_all_pages_async, get_all_pages
from app.scraper.parser import parse_jobs
from app.utils.logger import logger


# ─── ASYNC (preferred) ────────────────────────────────────────────────────────

async def run_scraper_async(
    filters: dict = None,
    max_jobs: int = None,
    proxy_url: str = None,
) -> list[dict]:
    """
    Async scrape pipeline.
    Fetches pages concurrently then parses results.
    """
    logger.info(
        f"=== [async] Scraper start | filters={filters} max_jobs={max_jobs} proxy_url={proxy_url} ==="
    )
    raw_jobs = await get_all_pages_async(filters=filters, max_jobs=max_jobs, proxy_url=proxy_url)
    parsed_jobs = parse_jobs(raw_jobs)
    logger.info(
        f"=== [async] Scraper done  | {len(parsed_jobs)} jobs ready to save ==="
    )
    return parsed_jobs


# ─── SYNC WRAPPER (for Celery / non-async callers) ───────────────────────────

def run_scraper(
    filters: dict = None,
    max_jobs: int = None,
    proxy_url: str = None,
) -> list[dict]:
    """
    Sync wrapper around run_scraper_async().

    Uses asyncio.run() so this can be called from Celery worker threads
    (which have no running event loop).  If an event loop is already
    running (e.g. inside a Jupyter notebook or a test using pytest-asyncio),
    it falls back to the sequential sync pipeline to avoid 'loop already
    running' errors.
    """
    logger.info(
        f"=== [sync] Scraper start | filters={filters} max_jobs={max_jobs} proxy_url={proxy_url} ==="
    )
    try:
        # Normal path — no running event loop (Celery worker, CLI)
        parsed_jobs = asyncio.run(
            run_scraper_async(filters=filters, max_jobs=max_jobs, proxy_url=proxy_url)
        )
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            # Fallback: use the old sequential sync pipeline
            logger.warning(
                "Event loop already running — falling back to sync scraper pipeline."
            )
            raw_jobs = get_all_pages(filters=filters, max_jobs=max_jobs, proxy_url=proxy_url)
            parsed_jobs = parse_jobs(raw_jobs)
        else:
            raise

    logger.info(
        f"=== [sync] Scraper done  | {len(parsed_jobs)} jobs ready to save ==="
    )
    return parsed_jobs