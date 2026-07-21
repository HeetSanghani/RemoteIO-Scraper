"""
pagination.py
─────────────
Handles page-count discovery and multi-page fetching for the Remote.io API.

Two surfaces:

  SYNC  — get_all_pages(filters, max_jobs)
    • Original sequential implementation kept for backward compatibility.
    • Used as a fallback if the async path fails.

  ASYNC — get_all_pages_async(filters, max_jobs)
    • Creates a single shared httpx.AsyncClient for the full scrape run.
    • Fetches pages in concurrent batches of CONCURRENT_REQUESTS size.
    • Typically 5–8× faster than the sequential sync version.
"""

import asyncio
import math
import os
from curl_cffi.requests import AsyncSession

from app.scraper.remoteio_client import fetch_page, fetch_page_async
from app.utils.logger import logger
from app.utils.constants import JOBS_PER_PAGE, CONCURRENT_REQUESTS, REQUEST_TIMEOUT


# ════════════════════════════════════════════════════════════════════════════
#  Page-count discovery  (sync — always called first to know total pages)
# ════════════════════════════════════════════════════════════════════════════

def get_total_pages_with_data(filters: dict = None, proxy_url: str = None) -> tuple[int, list[dict]]:
    """Fetch page 1 to read pagination metadata and return jobs."""
    data = fetch_page(1, filters, proxy=proxy_url)
    pagination = data.get("pagination", {})
    total_pages = int(pagination.get("totalPages", 1))
    total_jobs  = int(pagination.get("total", 0))
    logger.info(f"Remote.io reports {total_jobs} jobs across {total_pages} pages")
    return total_pages, data.get("data", [])


def get_total_pages(filters: dict = None, proxy_url: str = None) -> int:
    """Fetch page 1 to read pagination metadata. Returns total page count."""
    total_pages, _ = get_total_pages_with_data(filters, proxy_url=proxy_url)
    return total_pages


# ════════════════════════════════════════════════════════════════════════════
#  SYNC  (sequential — legacy, kept for compatibility / fallback)
# ════════════════════════════════════════════════════════════════════════════

def get_all_pages(filters: dict = None, max_jobs: int = None, proxy_url: str = None) -> list[dict]:
    """
    Sequential page fetcher (original implementation).
    Fetches one page at a time; slower but simpler.
    """
    total_pages = get_total_pages(filters, proxy_url=proxy_url)

    if max_jobs:
        pages_to_fetch = math.ceil(max_jobs / JOBS_PER_PAGE)
        total_pages = min(total_pages, pages_to_fetch)

    all_jobs: list[dict] = []

    for page in range(1, total_pages + 1):
        data = fetch_page(page, filters, proxy=proxy_url)
        jobs = data.get("data", [])
        all_jobs.extend(jobs)
        logger.info(f"[sync] page {page}/{total_pages} — running total: {len(all_jobs)}")

        if max_jobs and len(all_jobs) >= max_jobs:
            all_jobs = all_jobs[:max_jobs]
            logger.info(f"[sync] hit max_jobs cap ({max_jobs}). Stopping.")
            break

    logger.info(f"[sync] Scraping complete. {len(all_jobs)} jobs fetched.")
    return all_jobs


# ════════════════════════════════════════════════════════════════════════════
#  ASYNC  (concurrent batched — the fast path used by run_scraper_async)
# ════════════════════════════════════════════════════════════════════════════

async def _fetch_batch(
    pages: list[int],
    filters: dict | None,
    client,
    proxy_url: str | None = None,
) -> list[dict]:
    """
    Fire all pages in `pages` concurrently using asyncio.gather.
    Returns a flat list of raw job dicts in page-order.
    """
    tasks = [fetch_page_async(p, filters, client, proxy=proxy_url) for p in pages]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs: list[dict] = []
    for page_num, outcome in zip(pages, results):
        if isinstance(outcome, Exception):
            logger.error(f"[async] page {page_num} permanently failed: {outcome}")
            continue
        all_jobs.extend(outcome.get("data", []))

    return all_jobs


async def get_all_pages_async(
    filters: dict = None,
    max_jobs: int = None,
    proxy_url: str = None,
) -> list[dict]:
    """
    Concurrent page fetcher.

    Algorithm:
      1. Fetch page 1 synchronously to discover total_pages.
      2. Build the full page list [2 … total_pages].
      3. Fire pages in batches of CONCURRENT_REQUESTS using asyncio.gather.
      4. Stop early if the max_jobs cap is hit after any batch.

    The httpx.AsyncClient is created once here so all concurrent requests
    share a single TCP connection pool — this avoids the overhead of opening
    a new connection per page.
    """
    total_pages, page_1_jobs = get_total_pages_with_data(filters, proxy_url=proxy_url)

    if max_jobs:
        pages_needed = math.ceil(max_jobs / JOBS_PER_PAGE)
        total_pages = min(total_pages, pages_needed)

    logger.info(
        f"[async] Will fetch {total_pages} pages "
        f"(batch size={CONCURRENT_REQUESTS}, max_jobs={max_jobs})"
    )

    all_jobs: list[dict] = []
    if total_pages >= 1:
        if max_jobs and len(page_1_jobs) >= max_jobs:
            logger.info(f"[async] Page 1 jobs ({len(page_1_jobs)}) satisfies max_jobs cap ({max_jobs}). Stopping.")
            return page_1_jobs[:max_jobs]
        all_jobs.extend(page_1_jobs)

    # Exclude page 1 since we already have its jobs
    all_page_nums = list(range(2, total_pages + 1))

    if not all_page_nums:
        logger.info(f"[async] Scraping complete. {len(all_jobs)} jobs fetched.")
        return all_jobs

    import random
    from app.scraper.remoteio_client import get_random_proxy
    proxy = proxy_url if proxy_url is not None else get_random_proxy()
    async with AsyncSession(impersonate="chrome", proxy=proxy) as client:
        # Slice the page list into batches and process one batch at a time
        for batch_start in range(0, len(all_page_nums), CONCURRENT_REQUESTS):
            batch = all_page_nums[batch_start : batch_start + CONCURRENT_REQUESTS]
            batch_jobs = await _fetch_batch(batch, filters, client, proxy_url=proxy_url)
            all_jobs.extend(batch_jobs)

            logger.info(
                f"[async] batch pages {batch[0]}–{batch[-1]} done — "
                f"running total: {len(all_jobs)}"
            )

            # Early exit if we hit the cap
            if max_jobs and len(all_jobs) >= max_jobs:
                all_jobs = all_jobs[:max_jobs]
                logger.info(f"[async] hit max_jobs cap ({max_jobs}). Stopping.")
                break

            # Sleep jitter between batches to look like a human reader
            if batch_start + CONCURRENT_REQUESTS < len(all_page_nums):
                jitter = random.uniform(1.5, 4.0)
                logger.info(f"[async] Sleeping for {jitter:.2f}s (jitter delay) before fetching next batch...")
                await asyncio.sleep(jitter)

    logger.info(f"[async] Scraping complete. {len(all_jobs)} jobs fetched.")
    return all_jobs