from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import json


class JobResponse(BaseModel):
    id: int
    remote_id: str
    title: str
    company_name: str
    company_country: Optional[str] = None
    category: Optional[str] = None
    job_link: Optional[str] = None
    application_url: Optional[str] = None
    salary: Optional[str] = None
    key_preferences: Optional[List[str]] = None
    published_at: Optional[datetime] = None
    scraped_at: datetime
    is_active: bool

    @classmethod
    def from_orm_with_prefs(cls, job):
        data = {
            "id": job.id,
            "remote_id": job.remote_id,
            "title": job.title,
            "company_name": job.company_name,
            "company_country": job.company_country,
            "category": job.category,
            "job_link": job.job_link,
            "application_url": job.application_url,
            "salary": job.salary,
            "published_at": job.published_at,
            "scraped_at": job.scraped_at,
            "is_active": job.is_active,
            "key_preferences": _parse_prefs(job.key_preferences),
        }
        return cls(**data)

    model_config = {"from_attributes": True}


class PaginatedJobsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    jobs: List[JobResponse]


class JobSearchParams(BaseModel):
    keyword: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    skill: Optional[str] = None
    salary_min: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ScrapeRequest(BaseModel):
    location: Optional[str] = None
    category: Optional[str] = None
    skill: Optional[str] = None
    location_type: Optional[str] = Field(default=None, description="remote or hybrid")
    salary: Optional[str] = None
    limit: Optional[int] = Field(default=30, ge=0, description="Max jobs to scrape. Set to 0 or null for all pages.")
    proxy_url: Optional[str] = Field(default=None, description="Optional custom proxy URL to override the server defaults.")


class ScrapeMetadataRequest(BaseModel):
    location: Optional[str] = None
    category: Optional[str] = None
    skill: Optional[str] = None
    location_type: Optional[str] = None
    salary: Optional[str] = None


def _parse_prefs(raw) -> Optional[List[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except Exception:
        return None


# ─── Async scrape task schemas ────────────────────────────────────────────────

class ScrapeTaskResponse(BaseModel):
    """Returned immediately when a scrape is dispatched to Celery."""
    task_id: str
    status: str = "pending"
    message: str = "Scrape task queued. Poll /api/v1/jobs/scrape/status/{task_id} for progress."


class ScrapeStatusResponse(BaseModel):
    """Returned when polling a scrape task's status."""
    task_id: str
    status: str                          # pending | running | success | failed | revoked
    result: Optional[dict] = None        # populated on success/failure
    error: Optional[str] = None