from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
import socket
import urllib.parse
import os
from contextlib import asynccontextmanager

from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database.database import run_migrations
from app.middleware.rate_limiter import limiter

from app.api.routes.jobs import router as jobs_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.health import router as health_router
from app.api.routes.companies import router as companies_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")
    
    # Wait for the database host to be resolvable and reachable
    if not wait_for_db(database_url, timeout=60):
        raise Exception("Database host could not be resolved or reached via TCP.")

    # Run database migrations once database is verified reachable
    max_retries = 5
    migration_success = False
    for attempt in range(max_retries):
        try:
            print(f"Attempting to run database migrations (attempt {attempt + 1}/{max_retries})...")
            run_migrations()
            migration_success = True
            break
        except Exception as e:
            print(f"Failed to run database migrations: {e}")
            time.sleep(3)

    if not migration_success:
        raise Exception("Could not initialize PostgreSQL tables.")
        
    yield


app = FastAPI(
    title="RemoteIO Job Scraper API",
    description="Production-grade job scraper for remote.io",
    version="1.0.0",
    lifespan=lifespan
)

# ── Rate Limiting (SlowAPI) ───────────────────────────────────────────────────
# Attach the shared limiter and register the 429 exception handler.
# SlowAPIMiddleware reads app.state.limiter on every request.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production set CORS_ORIGINS to your exact Render domain, e.g.:
#   CORS_ORIGINS=https://remoteio-api.onrender.com
# Leave blank or set to * to allow all origins (useful during initial deploy).
_cors_env = os.getenv("CORS_ORIGINS", "").strip()

if not _cors_env or _cors_env == "*":
    # Allow all origins — useful during initial Render deploy
    _CORS_ORIGINS = ["*"]
    _allow_credentials = False  # credentials not allowed with wildcard
else:
    _CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)



def wait_for_db(db_url: str, timeout: int = 60) -> bool:
    """
    Waits for the database to become reachable using a direct TCP connection.
    This separates DNS resolution/network checks from SQLAlchemy/psycopg2
    instantiation, avoiding potential state locking or DNS caching issues in the driver.
    """
    if not db_url:
        print("DATABASE_URL environment variable is not set.")
        return False

    try:
        # Handle cases where URL might not have a scheme prefix
        if "://" not in db_url:
            db_url = "postgresql://" + db_url
        parsed = urllib.parse.urlparse(db_url)
        host = parsed.hostname
        port = parsed.port or 5432
    except Exception as e:
        print(f"Failed to parse DATABASE_URL '{db_url}': {e}")
        return False

    print(f"Waiting for database host '{host}' on port {port} to be reachable...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # Check DNS resolution first
            socket.getaddrinfo(host, port)
            # Try TCP connection
            with socket.create_connection((host, port), timeout=2):
                print(f"Database host '{host}' is reachable on port {port}!")
                return True
        except (socket.gaierror, socket.timeout, ConnectionRefusedError) as e:
            print(f"Database at '{host}:{port}' not reachable yet: {e}")
            time.sleep(2)
            
    return False




from fastapi.responses import HTMLResponse
import os

app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(analytics_router)
app.include_router(companies_router)


@app.get("/", response_class=HTMLResponse)
def root():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="""
        <html>
            <head><title>RemoteIO Job Scraper API</title></head>
            <body style="font-family: sans-serif; background: #0f1117; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                <h1>RemoteIO Job Scraper API</h1>
                <p>API is running. Place <code>index.html</code> in the root folder to view the dashboard.</p>
                <a href="/docs" style="color: #6366f1; text-decoration: none; font-weight: bold; border: 1px solid #6366f1; padding: 10px 20px; border-radius: 5px; margin-top: 15px;">View API Docs</a>
            </body>
        </html>
    """)

