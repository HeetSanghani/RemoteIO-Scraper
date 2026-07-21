from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from celery.result import AsyncResult
import redis, os, json, csv, io

from app.middleware.rate_limiter import limiter, LIMIT_READ, LIMIT_SEARCH, LIMIT_EXPORT, LIMIT_SCRAPE

from app.database.database import get_db
from app.services.job_service import (
    get_jobs, get_job_by_id, search_jobs, filter_jobs, save_jobs_and_get_records
)
from app.schemas.job_schema import (
    PaginatedJobsResponse, JobResponse,
    ScrapeRequest, ScrapeMetadataRequest,
    ScrapeTaskResponse, ScrapeStatusResponse,
)
from app.scheduler.celery_tasks import scrape_and_save_jobs
from app.scheduler.celery_worker import celery_app
from app.database.models.scrape_log import ScrapeLog
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)

def verify_api_key(
    api_key_header: Optional[str] = Security(API_KEY_HEADER),
    api_key_query: Optional[str] = Security(API_KEY_QUERY),
):
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: API_KEY environment variable is not set."
        )
    if api_key_header == expected_key or api_key_query == expected_key:
        return expected_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized: Invalid or missing API Key"
    )

# Redis client — reads the scrape batches stored by the Celery task
_redis = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True
)


# ── Shared CSV/Excel export helpers ─────────────────────────────────────────

EXPORT_FIELDS = [
    "remote_id", "title", "company_name", "company_country",
    "category", "salary", "job_link", "application_url",
    "key_preferences", "published_at",
]

# Human-readable column headers shown in the downloaded file
EXPORT_HEADERS = [
    "Job ID", "Job Title", "Company", "Country",
    "Category", "Salary", "Job Link", "Apply Link",
    "Required Skills", "Posted Date",
]


def _clean_value(field: str, value) -> str:
    """Post-process a raw field value into a clean, readable string."""
    import json as _json
    if value is None:
        return ""
    if field == "key_preferences":
        # Convert JSON array '["Python", "AWS"]' → 'Python, AWS'
        try:
            parsed = _json.loads(str(value))
            if isinstance(parsed, list):
                return ", ".join(str(s).strip() for s in parsed if s)
        except Exception:
            pass
        return str(value)
    if field == "published_at":
        # '2026-06-28 06:29:35.776000+00:00' → '2026-06-28'
        return str(value)[:10] if value else ""
    return str(value)


def _jobs_to_csv_bytes(jobs: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_HEADERS)  # human-readable headers
    for job in jobs:
        writer.writerow([_clean_value(f, job.get(f, "")) for f in EXPORT_FIELDS])
    return buf.getvalue().encode("utf-8")


def _jobs_to_excel_bytes(jobs: list[dict]) -> bytes:
    """Real XLSX export using openpyxl — clean headers, readable skills, formatted dates."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jobs"

    # Header row with bold dark styling
    header_fill = PatternFill(start_color="1e1b4b", end_color="1e1b4b", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx, header in enumerate(EXPORT_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Data rows — clean values
    for row_idx, job in enumerate(jobs, start=2):
        for col_idx, field in enumerate(EXPORT_FIELDS, start=1):
            ws.cell(row=row_idx, column=col_idx, value=_clean_value(field, job.get(field, "")))

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ─── GET /api/v1/jobs/ ─────────────────────────────────────────────────────────

@router.get("/", response_model=PaginatedJobsResponse)
@limiter.limit(LIMIT_READ)
def list_jobs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="published_at", enum=["published_at", "scraped_at", "title", "company_name"]),
    sort_order: str = Query(default="desc", enum=["asc", "desc"]),
    db: Session = Depends(get_db),
):
    return get_jobs(db, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order)


# ─── GET /api/v1/jobs/search ───────────────────────────────────────────────────

@router.get("/search", response_model=PaginatedJobsResponse)
@limiter.limit(LIMIT_SEARCH)
def search(
    request: Request,
    keyword: Optional[str] = Query(default=None, description="Search in title, description, company"),
    country: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="published_at", enum=["published_at", "scraped_at", "title", "company_name"]),
    sort_order: str = Query(default="desc", enum=["asc", "desc"]),
    db: Session = Depends(get_db),
):
    if not any([keyword, country, category]):
        raise HTTPException(status_code=400, detail="Provide at least one: keyword, country, or category")
    return search_jobs(db, keyword=keyword, country=country, category=category,
                       page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order)


# ─── GET /api/v1/jobs/filter ───────────────────────────────────────────────────

@router.get("/filter", response_model=PaginatedJobsResponse)
@limiter.limit(LIMIT_SEARCH)
def filter_job_list(
    request: Request,
    country: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="published_at", enum=["published_at", "scraped_at", "title", "company_name"]),
    sort_order: str = Query(default="desc", enum=["asc", "desc"]),
    db: Session = Depends(get_db),
):
    if not any([country, category, company]):
        raise HTTPException(status_code=400, detail="Provide at least one: country, category, or company")
    return filter_jobs(db, country=country, category=category, company=company,
                       page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order)


# ─── POST /api/v1/jobs/scrape  (NON-BLOCKING — dispatches to Celery) ───────────
#
#  Previously this endpoint called run_scraper() directly, which would block the
#  HTTP worker for the full duration of the scrape (minutes). Now it fires a
#  Celery task and immediately returns a task_id so the caller can poll.

@router.post("/scrape", response_model=ScrapeTaskResponse, status_code=202)
@limiter.limit(LIMIT_SCRAPE)
def trigger_scrape(
    request: Request,
    payload: ScrapeRequest,
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Dispatch a scrape job to the Celery worker and return immediately with
    a task_id.  Use GET /api/v1/jobs/scrape/status/{task_id} to track progress.
    """
    # Build Remote.io API filter dict from request payload
    filters: dict = {}
    if payload.location:
        filters["location"] = payload.location
    if payload.category:
        filters["category"] = payload.category
    if payload.skill:
        filters["skill"] = payload.skill
    if payload.location_type:
        filters["locationType"] = payload.location_type
    if payload.salary:
        filters["salary"] = payload.salary

    max_jobs = payload.limit if (payload.limit is not None and payload.limit > 0) else None

    # Persist a scrape log row immediately so the dashboard can show "running"
    log = ScrapeLog(
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db.add(log)
    db.commit()

    # Dispatch — .delay() sends the task to Redis; worker picks it up asynchronously
    task = scrape_and_save_jobs.delay(
        filters=filters if filters else None,
        max_jobs=max_jobs,
        scrape_log_id=log.id,
        proxy_url=payload.proxy_url,
    )

    return ScrapeTaskResponse(
        task_id=task.id,
        status="pending",
        message=f"Scrape task queued. Poll /api/v1/jobs/scrape/status/{task.id} for progress.",
    )


# ─── GET /api/v1/jobs/scrape/status/{task_id}  (Polling endpoint) ─────────────

@router.get("/scrape/status/{task_id}", response_model=ScrapeStatusResponse)
@limiter.limit(LIMIT_READ)
def get_scrape_status(request: Request, task_id: str):
    """
    Check the status of a previously dispatched scrape task.

    Celery task states:
      - PENDING  → task is queued / not yet picked up by a worker
      - STARTED  → worker has picked it up and is running
      - SUCCESS  → completed successfully; result contains the summary
      - FAILURE  → task raised an unhandled exception
      - RETRY    → worker is retrying after a transient error
      - REVOKED  → task was manually cancelled
    """
    result: AsyncResult = celery_app.AsyncResult(task_id)

    state = result.state  # Celery's internal state string

    # Map Celery states → our API vocabulary
    status_map = {
        "PENDING": "pending",
        "STARTED": "running",
        "RETRY":   "running",
        "SUCCESS": "success",
        "FAILURE": "failed",
        "REVOKED": "revoked",
    }
    api_status = status_map.get(state, state.lower())

    response_data: dict = {
        "task_id": task_id,
        "status": api_status,
        "result": None,
        "error": None,
    }

    if state == "SUCCESS":
        response_data["result"] = result.result  # dict returned by the task

    elif state == "FAILURE":
        # result.result is the exception object; stringify it for the response
        response_data["error"] = str(result.result)

    return ScrapeStatusResponse(**response_data)


# ─── GET /api/v1/jobs/scrape/export/all/{task_id}  (Download ALL from Remote.io)
@router.get("/scrape/export/all/{task_id}")
@limiter.limit(LIMIT_EXPORT)
def export_all_scraped(
    request: Request,
    task_id: str,
    fmt: str = Query(default="csv", enum=["csv", "excel"]),
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Download ALL jobs that were fetched from Remote.io in this scrape run.
    Reads from the temporary Redis batch stored by the Celery task (expires after 2h).
    """
    raw = _redis.get(f"scrape:all:{task_id}")
    if not raw:
        raise HTTPException(
            status_code=404,
            detail="Scrape batch not found. It may have expired (2h TTL) or the task_id is wrong."
        )
    all_ids: list[str] = json.loads(raw)
    if not all_ids:
        jobs = []
    else:
        from app.database.models.job import Job
        db_jobs = db.query(Job).filter(Job.remote_id.in_(all_ids)).all()
        jobs = [
            {
                "remote_id": j.remote_id, "title": j.title,
                "company_name": j.company_name, "company_country": j.company_country,
                "category": j.category, "salary": j.salary,
                "job_link": j.job_link, "application_url": j.application_url,
                "key_preferences": j.key_preferences,
                "published_at": str(j.published_at) if j.published_at else "",
            }
            for j in db_jobs
        ]

    date_str = datetime.now().strftime("%Y-%m-%d")
    if fmt == "excel":
        content = _jobs_to_excel_bytes(jobs)
        filename = f"all_scraped_jobs_{date_str}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = _jobs_to_csv_bytes(jobs)
        filename = f"all_scraped_jobs_{date_str}.csv"
        media_type = "text/csv"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── GET /api/v1/jobs/scrape/export/new/{task_id}  (Download only NEW jobs)
@router.get("/scrape/export/new/{task_id}")
@limiter.limit(LIMIT_EXPORT)
def export_new_scraped(
    request: Request,
    task_id: str,
    fmt: str = Query(default="csv", enum=["csv", "excel"]),
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Download ONLY the jobs that were brand-new (inserted for the first time)
    in this scrape run.
    """
    raw_ids = _redis.get(f"scrape:new:{task_id}")
    if not raw_ids:
        raise HTTPException(
            status_code=404,
            detail="New-jobs list not found. It may have expired (2h TTL) or the task_id is wrong."
        )
    new_ids: list[str] = json.loads(raw_ids)
    if not new_ids:
        jobs_data = []
    else:
        from app.database.models.job import Job
        db_jobs = db.query(Job).filter(Job.remote_id.in_(new_ids)).all()
        jobs_data = [
            {
                "remote_id": j.remote_id, "title": j.title,
                "company_name": j.company_name, "company_country": j.company_country,
                "category": j.category, "salary": j.salary,
                "job_link": j.job_link, "application_url": j.application_url,
                "key_preferences": j.key_preferences,
                "published_at": str(j.published_at) if j.published_at else "",
            }
            for j in db_jobs
        ]

    date_str = datetime.now().strftime("%Y-%m-%d")
    if fmt == "excel":
        content = _jobs_to_excel_bytes(jobs_data)
        filename = f"new_jobs_{date_str}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = _jobs_to_csv_bytes(jobs_data)
        filename = f"new_jobs_{date_str}.csv"
        media_type = "text/csv"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── POST /api/v1/jobs/scrape/metadata ───────────────────────────────────────

@router.post("/scrape/metadata")
def get_scrape_metadata(
    payload: ScrapeMetadataRequest,
    api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Fetch the first page of Remote.io API to get pagination metadata
    (total pages, total jobs) based on the requested filters.
    """
    filters: dict = {}
    if payload.location:
        filters["location"] = payload.location
    if payload.category:
        filters["category"] = payload.category
    if payload.skill:
        filters["skill"] = payload.skill
    if payload.location_type:
        filters["locationType"] = payload.location_type
    if payload.salary:
        filters["salary"] = payload.salary

    try:
        from app.scraper.remoteio_client import fetch_page
        data = fetch_page(1, filters)
        pagination = data.get("pagination", {})
        return {
            "total_pages": int(pagination.get("totalPages", 0)),
            "total_jobs": int(pagination.get("total", 0)),
            "jobs_per_page": 30,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {str(e)}")


# ─── GET /api/v1/jobs/{job_id} ─────────────────────────────────────────────────
# NOTE: This must be declared LAST so it doesn't swallow the /scrape/* routes.

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with id {job_id} not found")
    return job