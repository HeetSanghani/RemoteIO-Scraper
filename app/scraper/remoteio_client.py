"""
remoteio_client.py
------------------
HTTP layer for the Remote.io job API.

Two surfaces are provided:

  SYNC  - fetch_page(page, filters, proxy)
    * Used by: /scrape/metadata endpoint, unit tests, one-off CLI calls.
    * Uses curl_cffi for browser impersonation.
    * Wrapped with tenacity retries.

  ASYNC - fetch_page_async(page, filters, client, proxy)
    * Used by: pagination.get_all_pages_async() -> concurrent batch fetching.
    * Uses a shared curl_cffi AsyncSession.
    * Wrapped with tenacity async retries.

Both surfaces share the same HEADERS block and parameter-building logic.
"""

import asyncio
import os
from curl_cffi import requests as curl_requests
from curl_cffi.requests.errors import RequestsError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

from app.utils.constants import (
    REMOTEIO_API_BASE,
    JOBS_PER_PAGE,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY_BASE,
)
from app.utils.logger import logger

# -- tenacity uses stdlib logging for its before_sleep hook -------------------
_tenacity_logger = logging.getLogger("tenacity")

# -- Retry-worthy HTTP/network exceptions -------------------------------------
_SYNC_RETRY_EXCEPTIONS = (RequestsError,)
_ASYNC_RETRY_EXCEPTIONS = (RequestsError,)

# -- Shared browser-like headers -----------------------------------------------
HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://remote.io/",
    "Origin": "https://remote.io",
    "sec-ch-ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def _build_params(page: int, filters: dict | None) -> dict:
    """Build the query-param dict common to both sync and async fetches."""
    params: dict = {"page": page, "limit": JOBS_PER_PAGE}
    if filters:
        for k, v in filters.items():
            if v is not None and v != "":
                params[k] = v
    return params


def get_random_proxy() -> str | None:
    """Select a random proxy from PROXY_URL (supports comma-separated list)."""
    import random
    proxy_env = os.getenv("PROXY_URL")
    if not proxy_env:
        return None
    proxies = [p.strip() for p in proxy_env.split(",") if p.strip()]
    if not proxies:
        return None
    return random.choice(proxies)


def _is_retryable_status(status_code: int) -> bool:
    """Return True for server-side transient errors we should retry."""
    return status_code in {429, 500, 502, 503, 504}


# ============================================================================
#  SYNC CLIENT  (curl_cffi + tenacity)
# ============================================================================

@retry(
    retry=retry_if_exception_type(_SYNC_RETRY_EXCEPTIONS),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=RETRY_DELAY_BASE, min=RETRY_DELAY_BASE, max=30),
    before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING),
    reraise=False,
)
def fetch_page(page: int, filters: dict = None, proxy: str = None) -> dict:
    """
    SYNC - Fetch a single page from the Remote.io API.

    Returns the parsed JSON dict on success, or {} on unrecoverable failure.
    Automatically retries on Timeout / ConnectionError with exponential back-off.
    """
    params = _build_params(page, filters)
    used_proxy = proxy if proxy is not None else get_random_proxy()
    try:
        response = curl_requests.get(
            REMOTEIO_API_BASE,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            impersonate="chrome",
            proxy=used_proxy,
        )
        
        if _is_retryable_status(response.status_code):
            raise RequestsError(f"Retryable HTTP {response.status_code}", response=response)
            
        response.raise_for_status()
        logger.debug(f"[sync] page {page} raw: {response.text[:200]}")
        data = response.json()
        logger.info(f"[sync] page {page} -> {len(data.get('data', []))} jobs")
        return data

    except RequestsError as e:
        if e.response is not None and _is_retryable_status(e.response.status_code):
            raise
        logger.error(f"[sync] Request error page {page}: {e}")
        return {}
    except Exception as e:
        logger.error(f"[sync] Unexpected error page {page}: {e}")
        return {}


# ============================================================================
#  ASYNC CLIENT  (curl_cffi AsyncSession + tenacity async)
# ============================================================================

@retry(
    retry=retry_if_exception_type(_ASYNC_RETRY_EXCEPTIONS),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=RETRY_DELAY_BASE, min=RETRY_DELAY_BASE, max=30),
    before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING),
    reraise=False,
)
async def fetch_page_async(
    page: int,
    filters: dict | None,
    client,  # curl_cffi.requests.AsyncSession
    proxy: str = None,
) -> dict:
    """
    ASYNC - Fetch a single page using a shared curl_cffi.requests.AsyncSession.

    The client is created once per scrape run so the underlying connection
    pool is shared across all concurrent requests - this avoids opening a new
    TCP connection for every page.
    """
    params = _build_params(page, filters)
    used_proxy = proxy if proxy is not None else get_random_proxy()
    try:
        response = await client.get(
            REMOTEIO_API_BASE,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            proxy=used_proxy,
        )

        if _is_retryable_status(response.status_code):
            logger.warning(
                f"[async] page {page} got HTTP {response.status_code} - will retry"
            )
            raise RequestsError(
                f"Retryable HTTP {response.status_code}",
                response=response,
            )

        response.raise_for_status()
        logger.debug(f"[async] page {page} raw: {response.text[:200]}")
        data = response.json()
        logger.info(f"[async] page {page} -> {len(data.get('data', []))} jobs")
        return data

    except RequestsError as e:
        if e.response is not None and _is_retryable_status(e.response.status_code):
            raise
        logger.error(f"[async] Request error page {page}: {e}")
        return {}
    except Exception as e:
        logger.error(f"[async] Unexpected error page {page}: {e}")
        return {}
