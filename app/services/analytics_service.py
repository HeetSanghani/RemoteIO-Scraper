from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.database.models.job import Job
from app.database.models.scrape_log import ScrapeLog
from app.utils.logger import logger
from datetime import datetime, timezone, timedelta
import json


def get_filter_options(db: Session) -> dict:
    """Return ALL distinct categories, countries and companies that have active jobs."""
    try:
        categories = db.query(
            Job.category, func.count(Job.id).label("count")
        ).filter(
            Job.is_active == True,
            Job.category != None,
            Job.category != "",
        ).group_by(Job.category).order_by(Job.category.asc()).all()

        countries = db.query(
            Job.company_country, func.count(Job.id).label("count")
        ).filter(
            Job.is_active == True,
            Job.company_country != None,
            Job.company_country != "",
        ).group_by(Job.company_country).order_by(Job.company_country.asc()).all()

        companies = db.query(
            Job.company_name, func.count(Job.id).label("count")
        ).filter(
            Job.is_active == True,
            Job.company_name != None,
            Job.company_name != "",
        ).group_by(Job.company_name).order_by(Job.company_name.asc()).all()

        return {
            "categories": [{"category": r[0], "count": r[1]} for r in categories],
            "countries":  [{"country":  r[0], "count": r[1]} for r in countries],
            "companies":  [{"company":  r[0], "count": r[1]} for r in companies],
        }
    except Exception as e:
        logger.error(f"Filter options error: {e}")
        return {"categories": [], "countries": [], "companies": []}


def get_analytics(db: Session) -> dict:
    import redis
    import os

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    r_client = None
    try:
        r_client = redis.Redis.from_url(redis_url, decode_responses=True)
        cached = r_client.get("cache:analytics")
        if cached:
            logger.info("Serving analytics from Redis cache")
            return json.loads(cached)
    except Exception as cache_err:
        logger.warning(f"Redis cache read failed: {cache_err}")

    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)

        # ── Basic counts ──────────────────────────────────────────────────────
        total_jobs = db.query(func.count(Job.id)).filter(
            Job.is_active == True
        ).scalar()

        jobs_today = db.query(func.count(Job.id)).filter(
            Job.is_active == True,
            Job.scraped_at >= today_start,
        ).scalar()

        jobs_this_week = db.query(func.count(Job.id)).filter(
            Job.is_active == True,
            Job.scraped_at >= week_start,
        ).scalar()

        jobs_with_salary = db.query(func.count(Job.id)).filter(
            Job.is_active == True,
            Job.salary != None,
            Job.salary != "",
        ).scalar()

        # ── Duplicate count ───────────────────────────────────────────────────
        # Jobs sharing the same title + company_name = likely duplicates
        duplicate_count = _get_duplicate_count(db)

        # ── Top categories ────────────────────────────────────────────────────
        top_categories = db.query(
            Job.category, func.count(Job.id).label("count")
        ).filter(
            Job.is_active == True,
            Job.category != None,
            Job.category != "",
        ).group_by(Job.category).order_by(func.count(Job.id).desc()).limit(10).all()

        # ── Top countries ─────────────────────────────────────────────────────
        top_countries = db.query(
            Job.company_country, func.count(Job.id).label("count")
        ).filter(
            Job.is_active == True,
            Job.company_country != None,
            Job.company_country != "",
        ).group_by(Job.company_country).order_by(func.count(Job.id).desc()).limit(10).all()

        # ── Top companies ─────────────────────────────────────────────────────
        top_companies = db.query(
            Job.company_name, func.count(Job.id).label("count")
        ).filter(
            Job.is_active == True,
        ).group_by(Job.company_name).order_by(func.count(Job.id).desc()).limit(10).all()

        # ── Top skills ────────────────────────────────────────────────────────
        top_skills = _get_top_skills(db, limit=10)

        # ── Daily growth (last 14 days) ───────────────────────────────────────
        daily_growth = _get_daily_growth(db, days=14)

        # ── Scrape history (last 10 runs) ─────────────────────────────────────
        recent_scrapes = db.query(ScrapeLog).order_by(
            ScrapeLog.started_at.desc()
        ).limit(10).all()

        scrape_history = [
            {
                "started_at": str(s.started_at),
                "completed_at": str(s.completed_at) if s.completed_at else None,
                "status": s.status,
                "jobs_found": s.jobs_found,
                "jobs_inserted": s.jobs_inserted,
                "error_message": s.error_message,
            }
            for s in recent_scrapes
        ]

        result_data = {
            "total_jobs": total_jobs,
            "jobs_today": jobs_today,
            "jobs_this_week": jobs_this_week,
            "jobs_with_salary": jobs_with_salary,
            "salary_coverage_pct": round((jobs_with_salary / total_jobs) * 100, 1) if total_jobs else 0,
            "duplicate_count": duplicate_count,
            "top_categories": [{"category": r[0], "count": r[1]} for r in top_categories],
            "top_countries": [{"country": r[0], "count": r[1]} for r in top_countries],
            "top_companies": [{"company": r[0], "count": r[1]} for r in top_companies],
            "top_skills": top_skills,
            "daily_growth": daily_growth,
            "scrape_history": scrape_history,
        }

        if r_client:
            try:
                r_client.setex("cache:analytics", 3600, json.dumps(result_data))  # 1h TTL
                logger.info("Cached analytics in Redis (TTL=1h)")
            except Exception as cache_write_err:
                logger.warning(f"Redis cache write failed: {cache_write_err}")

        return result_data

    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return {"error": str(e)}


def _get_duplicate_count(db: Session) -> int:
    """Count jobs that share the same title + company_name (potential duplicates)."""
    try:
        subquery = (
            db.query(func.count(Job.id).label("cnt"))
            .filter(Job.is_active == True)
            .group_by(Job.title, Job.company_name)
            .having(func.count(Job.id) > 1)
            .subquery()
        )
        result = db.query(func.sum(subquery.c.cnt)).scalar()
        return int(result) if result else 0
    except Exception as e:
        logger.error(f"Duplicate count error: {e}")
        return 0


def _get_daily_growth(db: Session, days: int = 14) -> list:
    """Jobs scraped per day for the last N days."""
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            db.query(
                func.date(Job.scraped_at).label("date"),
                func.count(Job.id).label("jobs_scraped"),
            )
            .filter(Job.is_active == True, Job.scraped_at >= since)
            .group_by(func.date(Job.scraped_at))
            .order_by(func.date(Job.scraped_at).asc())
            .all()
        )
        return [{"date": str(r[0]), "jobs_scraped": r[1]} for r in rows]
    except Exception as e:
        logger.error(f"Daily growth error: {e}")
        return []


def _get_top_skills(db: Session, limit: int = 10) -> list:
    """Parse key_preferences JSON from all jobs and count skill frequency."""
    import redis
    import os

    try:
        # Try reading from Redis first
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis = redis.Redis.from_url(redis_url, decode_responses=True)
            cached = _redis.get("analytics:top_skills")
            if cached:
                skills_list = json.loads(cached)
                return skills_list[:limit]
        except Exception as redis_err:
            logger.warning(f"Redis read failed in _get_top_skills: {redis_err}")
            _redis = None

        # Compute skills
        if db.bind.dialect.name == "postgresql":
            try:
                sql = text("""
                    SELECT skill, COUNT(*) as count
                    FROM jobs, json_array_elements_text(key_preferences::json) AS skill
                    WHERE is_active = true
                      AND key_preferences IS NOT NULL
                      AND key_preferences LIKE '[%'
                    GROUP BY skill
                    ORDER BY count DESC
                    LIMIT 100
                """)
                rows = db.execute(sql).fetchall()
                skills_list = [{"skill": r[0], "count": r[1]} for r in rows]
            except Exception as sql_err:
                logger.error(f"Postgres native top skills failed, falling back: {sql_err}")
                skills_list = _get_top_skills_fallback(db)
        else:
            skills_list = _get_top_skills_fallback(db)

        # Cache top 100 in Redis for 15 minutes (900 seconds)
        if _redis:
            try:
                _redis.setex("analytics:top_skills", 900, json.dumps(skills_list))
            except Exception as redis_err:
                pass

        return skills_list[:limit]
    except Exception as e:
        logger.error(f"Top skills error: {e}")
        return []


def _get_top_skills_fallback(db: Session) -> list:
    skill_counts = {}
    chunk_size = 2000
    offset = 0
    while True:
        rows = db.query(Job.key_preferences).filter(
            Job.is_active == True,
            Job.key_preferences != None,
            Job.key_preferences != "",
            Job.key_preferences.like("[%")
        ).offset(offset).limit(chunk_size).all()
        
        if not rows:
            break
            
        for (raw,) in rows:
            try:
                skills = json.loads(raw)
                if isinstance(skills, list):
                    for skill in skills:
                        s = skill.strip()
                        if s:
                            skill_counts[s] = skill_counts.get(s, 0) + 1
            except Exception:
                continue
        offset += chunk_size
        
    sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
    return [{"skill": k, "count": v} for k, v in sorted_skills[:100]]