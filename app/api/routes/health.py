from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.database.models.scrape_log import ScrapeLog
from app.middleware.rate_limiter import limiter, LIMIT_HEALTH, LIMIT_READ

router = APIRouter(tags=["Health"])


@router.get("/health")
@limiter.limit(LIMIT_HEALTH)
def health(request: Request):
    return {"status": "ok", "service": "RemoteIO Job Scraper"}


@router.get("/api/v1/scraper/status")
@limiter.limit(LIMIT_READ)
def scraper_status(request: Request, db: Session = Depends(get_db)):
    logs = db.query(ScrapeLog).order_by(ScrapeLog.id.desc()).limit(5).all()
    return {
        "recent_runs": [
            {
                "id": l.id,
                "started_at": l.started_at,
                "completed_at": l.completed_at,
                "jobs_found": l.jobs_found,
                "jobs_inserted": l.jobs_inserted,
                "status": l.status,
                "error": l.error_message,
            } for l in logs
        ]
    }