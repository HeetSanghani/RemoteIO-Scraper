from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional, List
from app.database.models import Job
from app.schemas.job_schema import JobResponse, PaginatedJobsResponse
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ─── Save Jobs (fixed dedup — set-based, not full load) ───────────────────────

def save_jobs(db: Session, jobs: list) -> tuple[int, set]:
    """
    Insert only new jobs (dedup by remote_id).
    Returns (count_inserted, set_of_new_remote_ids).
    """
    if not jobs:
        return 0, set()

    # Load only remote_ids — O(1) lookup, memory safe at 100k+
    existing_ids = set(
        row[0] for row in db.query(Job.remote_id).all()
    )

    new_jobs = []
    new_remote_ids = set()
    for job in jobs:
        rid = job.get("remote_id")
        if rid in existing_ids:
            continue
        new_remote_ids.add(rid)
        new_jobs.append(Job(
            remote_id=rid,
            title=job.get("title"),
            company_name=job.get("company_name"),
            company_country=job.get("company_country"),
            category=job.get("category"),
            job_link=job.get("job_link"),
            application_url=job.get("application_url"),
            description=job.get("description"),
            salary=job.get("salary"),
            key_preferences=job.get("key_preferences"),
            published_at=job.get("published_at"),
            is_active=True,
        ))

    if new_jobs:
        db.bulk_save_objects(new_jobs)
        db.commit()
        logger.info(f"Inserted {len(new_jobs)} new jobs")

    return len(new_jobs), new_remote_ids


# ─── Sync Jobs (deactivate ghost jobs not seen in latest scrape) ──────────────

def sync_jobs(db: Session, scraped_remote_ids: List[str]) -> int:
    """
    After a full scrape, mark any job in the DB as is_active=False if its
    remote_id was NOT returned by the most recent scrape.
    Returns the count of jobs deactivated.
    """
    if not scraped_remote_ids:
        # Safety guard: never deactivate everything if the scrape returned nothing
        logger.warning("sync_jobs called with an empty ID list — skipping deactivation.")
        return 0

    result = (
        db.query(Job)
        .filter(
            Job.is_active == True,
            Job.remote_id.notin_(scraped_remote_ids),
        )
        .update(
            {"is_active": False, "updated_at": datetime.now(timezone.utc)},
            synchronize_session="fetch",
        )
    )
    db.commit()
    logger.info(f"sync_jobs: deactivated {result} ghost jobs not present in latest scrape.")
    return result


def save_jobs_and_get_records(db: Session, jobs: list) -> tuple[int, list]:
    if not jobs:
        return 0, []

    existing_ids = set(
        row[0] for row in db.query(Job.remote_id).all()
    )

    new_jobs = []
    for job in jobs:
        if job.get("remote_id") in existing_ids:
            continue
        new_jobs.append(Job(
            remote_id=job.get("remote_id"),
            title=job.get("title"),
            company_name=job.get("company_name"),
            company_country=job.get("company_country"),
            category=job.get("category"),
            job_link=job.get("job_link"),
            application_url=job.get("application_url"),
            description=job.get("description"),
            salary=job.get("salary"),
            key_preferences=job.get("key_preferences"),
            published_at=job.get("published_at"),
            is_active=True,
        ))

    if new_jobs:
        db.bulk_save_objects(new_jobs)
        db.commit()
        logger.info(f"Inserted {len(new_jobs)} new jobs")

    scraped_remote_ids = [j.get("remote_id") for j in jobs if j.get("remote_id")]
    db_jobs = []
    if scraped_remote_ids:
        db_jobs = db.query(Job).filter(Job.remote_id.in_(scraped_remote_ids)).all()
    
    return len(new_jobs), db_jobs


# ─── Get Jobs (paginated + sorted) ────────────────────────────────────────────

SORT_FIELDS = {
    "published_at": Job.published_at,
    "scraped_at": Job.scraped_at,
    "title": Job.title,
    "company_name": Job.company_name,
}

def get_jobs(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "published_at",
    sort_order: str = "desc",
) -> PaginatedJobsResponse:

    query = db.query(Job).filter(Job.is_active == True)

    # Sorting
    sort_col = SORT_FIELDS.get(sort_by, Job.published_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    jobs = query.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        jobs=[JobResponse.from_orm_with_prefs(j) for j in jobs],
    )


# ─── Search Jobs ───────────────────────────────────────────────────────────────

def search_jobs(
    db: Session,
    keyword: Optional[str] = None,
    country: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "published_at",
    sort_order: str = "desc",
) -> PaginatedJobsResponse:

    query = db.query(Job).filter(Job.is_active == True)

    if keyword:
        query = query.filter(
            or_(
                Job.title.ilike(f"%{keyword}%"),
                Job.description.ilike(f"%{keyword}%"),
                Job.company_name.ilike(f"%{keyword}%"),
            )
        )
    if country:
        query = query.filter(Job.company_country.ilike(f"%{country}%"))
    if category:
        query = query.filter(Job.category.ilike(f"%{category}%"))

    sort_col = SORT_FIELDS.get(sort_by, Job.published_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    jobs = query.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        jobs=[JobResponse.from_orm_with_prefs(j) for j in jobs],
    )


# ─── Filter Jobs ───────────────────────────────────────────────────────────────

def filter_jobs(
    db: Session,
    country: Optional[str] = None,
    category: Optional[str] = None,
    company: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "published_at",
    sort_order: str = "desc",
) -> PaginatedJobsResponse:

    query = db.query(Job).filter(Job.is_active == True)

    if country:
        query = query.filter(Job.company_country.ilike(f"%{country}%"))
    if category:
        query = query.filter(Job.category.ilike(f"%{category}%"))
    if company:
        query = query.filter(Job.company_name.ilike(f"%{company}%"))

    sort_col = SORT_FIELDS.get(sort_by, Job.published_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    jobs = query.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        jobs=[JobResponse.from_orm_with_prefs(j) for j in jobs],
    )


# ─── Get single job by ID ──────────────────────────────────────────────────────

def get_job_by_id(db: Session, job_id: int) -> Optional[JobResponse]:
    job = db.query(Job).filter(Job.id == job_id, Job.is_active == True).first()
    if not job:
        return None
    return JobResponse.from_orm_with_prefs(job)