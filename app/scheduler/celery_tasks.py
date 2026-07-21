from app.scheduler.celery_worker import celery_app
from app.scraper.scraper_service import run_scraper
from app.services.job_service import save_jobs, sync_jobs
from app.exports.csv_exporter import export_jobs_to_csv
from app.database.database import SessionLocal
from app.database.models.scrape_log import ScrapeLog
from app.utils.logger import logger
from datetime import datetime, timezone
import time
import json
import redis
import os

# Redis client for temporary scrape batch storage
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_kwargs = {"decode_responses": True}
if _redis_url.startswith("rediss://"):
    _redis_kwargs["ssl_cert_reqs"] = "none"

_redis = redis.Redis.from_url(_redis_url, **_redis_kwargs)
SCRAPE_BATCH_TTL = 60 * 60 * 2  # 2 hours — enough time to download after a scrape


@celery_app.task(
    name="scrape_and_save_jobs",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # retry after 60 seconds
)
def scrape_and_save_jobs(self, filters: dict = None, max_jobs: int = None, scrape_log_id: int = None, proxy_url: str = None):
    """
    Main scrape task.
    - filters: dict of Remote.io API filter params (location, category, skill, etc.)
    - max_jobs: hard cap on jobs to return (None = all pages)
    - scrape_log_id: ID of the pre-created ScrapeLog entry (if triggered via API)
    - proxy_url: Optional custom proxy URL to override default settings
    Can be triggered manually via API or by Celery Beat on a schedule.
    """
    # Apply scheduler jitter for background scheduled runs (when scrape_log_id is None)
    if not scrape_log_id:
        import random
        jitter_delay = random.uniform(5.0, 120.0)
        logger.info(f"Scheduled Celery task triggered. Applying scheduler jitter: sleeping for {jitter_delay:.2f}s before scraping...")
        time.sleep(jitter_delay)

    db = SessionLocal()
    if scrape_log_id:
        log = db.query(ScrapeLog).filter(ScrapeLog.id == scrape_log_id).first()
        if not log:
            log = ScrapeLog(started_at=datetime.now(timezone.utc), status="running")
            db.add(log)
            db.commit()
    else:
        log = ScrapeLog(started_at=datetime.now(timezone.utc), status="running")
        db.add(log)
        db.commit()

    start_time = time.time()

    try:
        logger.info(f"=== Celery task: starting scrape | filters={filters} max_jobs={max_jobs} proxy_url={proxy_url} ===")

        # ── Step 1: Scrape ────────────────────────────────────────────────────
        try:
            parsed_jobs = run_scraper(filters=filters, max_jobs=max_jobs, proxy_url=proxy_url)
            log.jobs_found = len(parsed_jobs)
            db.commit()
            logger.info(f"Scraper returned {len(parsed_jobs)} jobs")
        except Exception as scrape_err:
            logger.error(f"Scraper failed: {scrape_err}")
            raise self.retry(exc=scrape_err)  # retries up to max_retries

        # ── Step 2: Save new jobs ─────────────────────────────────────────────
        inserted, new_remote_ids = save_jobs(db, parsed_jobs)
        log.jobs_inserted = inserted
        db.commit()
        logger.info(f"{inserted} new jobs inserted")

        # ── Step 3: Store full batch + new IDs in Redis (for export downloads) ─
        # Key: scrape:all:{task_id}  → full list of all scraped jobs (from Remote.io)
        # Key: scrape:new:{task_id}  → only the remote_ids that were inserted this run
        # Both expire after 2 hours
        task_id = self.request.id
        try:
            _redis.setex(
                f"scrape:all:{task_id}",
                SCRAPE_BATCH_TTL,
                json.dumps(parsed_jobs, default=str),
            )
            _redis.setex(
                f"scrape:new:{task_id}",
                SCRAPE_BATCH_TTL,
                json.dumps(list(new_remote_ids)),
            )
            logger.info(f"Stored scrape batch in Redis under task_id={task_id}")
        except Exception as redis_err:
            logger.warning(f"Redis batch store failed (non-critical): {redis_err}")

        # ── Step 4: Sync / deactivate ghost jobs ─────────────────────────────
        # Only run full sync when no filters are applied (i.e. this was a
        # full-catalogue scrape). Partial scrapes must NOT deactivate unrelated jobs.
        deactivated = 0
        if not filters:
            scraped_remote_ids = [j["remote_id"] for j in parsed_jobs if j.get("remote_id")]
            deactivated = sync_jobs(db, scraped_remote_ids)
            logger.info(f"{deactivated} ghost jobs deactivated / removed from active list")

        # ── Step 5: Export CSV (non-critical) ────────────────────────────────
        try:
            export_jobs_to_csv(db)
            logger.info("CSV export complete")
        except Exception as csv_err:
            logger.warning(f"CSV export failed (non-critical): {csv_err}")

        # ── Step 6: Mark success ─────────────────────────────────────────────
        duration = round(time.time() - start_time, 2)
        log.status = "success"
        log.completed_at = datetime.now(timezone.utc)
        if hasattr(log, "duration_seconds"):
            log.duration_seconds = duration
        db.commit()

        # Invalidate analytics cache
        try:
            _redis.delete("cache:analytics")
            logger.info("Cleared analytics cache from Redis on successful scrape.")
        except Exception as cache_err:
            logger.warning(f"Failed to clear analytics cache: {cache_err}")

        logger.info(f"=== Celery task done in {duration}s: {inserted} new, {deactivated} deactivated ===")
        return {
            "status": "success",
            "task_id": task_id,
            "jobs_found": log.jobs_found,
            "jobs_inserted": inserted,
            "jobs_deactivated": deactivated,
            "duration_seconds": duration,
        }

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        log.status = "failed"
        log.error_message = str(e)
        log.completed_at = datetime.now(timezone.utc)
        if hasattr(log, "duration_seconds"):
            log.duration_seconds = duration
        db.commit()

        # Invalidate analytics cache on failure as well (to show updated scrape history status)
        try:
            _redis.delete("cache:analytics")
            logger.info("Cleared analytics cache from Redis on failed scrape.")
        except Exception as cache_err:
            logger.warning(f"Failed to clear analytics cache: {cache_err}")

        logger.error(f"Celery task failed after {duration}s: {e}")
        return {"status": "failed", "error": str(e)}

    finally:
        db.close()