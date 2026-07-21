import os
from dotenv import load_dotenv

load_dotenv()

# Remote.io API
REMOTEIO_API_BASE = os.getenv("REMOTEIO_API_BASE", "https://remote.io/api/v2/jobs")
JOBS_PER_PAGE = int(os.getenv("JOBS_PER_PAGE", 30))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

# Async scraper tuning
# Max number of page-fetches running simultaneously. Keep ≤ 10 to be polite
# to the target server; raise carefully if you're using rotating proxies.
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", 5))

# Base delay (seconds) for tenacity exponential back-off between retries.
# Actual wait = RETRY_DELAY_BASE * 2^(attempt-1)  → 2s, 4s, 8s …
RETRY_DELAY_BASE = float(os.getenv("RETRY_DELAY_BASE", 2.0))

# CSV
CSV_EXPORT_PATH = os.getenv("CSV_EXPORT_PATH", "exports/jobs_export.csv")