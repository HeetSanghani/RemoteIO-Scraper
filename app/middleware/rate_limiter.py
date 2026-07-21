"""
Rate Limiting — powered by SlowAPI (wraps the `limits` library).

Strategy (per IP address):
  - General read endpoints  : 60 requests / minute
  - Search / filter queries : 30 requests / minute
  - Export downloads        : 10 requests / minute
  - Scrape trigger (POST)   : 5  requests / minute   ← expensive, protect hard
  - Health check            : 120 requests / minute  ← monitoring tools need headroom

Usage in a route:
    from app.middleware.rate_limiter import limiter
    from fastapi import Request

    @router.get("/my-endpoint")
    @limiter.limit("30/minute")
    def my_view(request: Request, ...):
        ...

NOTE: `request: Request` must be the FIRST parameter in every rate-limited
      route for SlowAPI to correctly extract the client IP.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared limiter instance — imported by main.py and all route files
limiter = Limiter(
    key_func=get_remote_address,   # identify clients by IP
    default_limits=["60/minute"],  # fallback limit for any un-decorated endpoint
)

# ── Named limit constants (use these in decorators for clarity) ──────────────
LIMIT_READ      = "60/minute"    # GET list / detail endpoints
LIMIT_SEARCH    = "30/minute"    # GET search / filter
LIMIT_EXPORT    = "10/minute"    # GET CSV / Excel download
LIMIT_SCRAPE    = "5/minute"     # POST /scrape  (most expensive)
LIMIT_HEALTH    = "120/minute"   # GET /health
