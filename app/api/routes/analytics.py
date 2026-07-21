from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.services.analytics_service import get_analytics, get_filter_options
from app.schemas.analytics_schema import AnalyticsResponse
from app.middleware.rate_limiter import limiter, LIMIT_READ

router = APIRouter(prefix="/api/v1", tags=["Analytics"])


@router.get("/analytics", response_model=AnalyticsResponse)
@limiter.limit(LIMIT_READ)
def analytics(request: Request, db: Session = Depends(get_db)):
    return get_analytics(db)


@router.get("/filters")
@limiter.limit(LIMIT_READ)
def filters(request: Request, db: Session = Depends(get_db)):
    """Return all distinct categories, countries, and companies available in the DB for filter dropdowns."""
    return get_filter_options(db)