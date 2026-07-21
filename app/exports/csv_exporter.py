import csv
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database.models.job import Job
from app.utils.constants import CSV_EXPORT_PATH
from app.utils.logger import logger
import json

EXPORT_DIR = os.path.dirname(CSV_EXPORT_PATH)
CHUNK_SIZE = 500  # process 500 jobs at a time, not all at once


def export_jobs_to_csv(db: Session, timestamped: bool = False) -> str:
    """
    Export all active jobs to CSV.
    - timestamped=False → overwrites exports/jobs_export.csv (default, for Celery)
    - timestamped=True  → creates exports/jobs_export_20260625_1045.csv (for manual runs)
    """
    try:
        os.makedirs(EXPORT_DIR, exist_ok=True)

        if timestamped:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            filename = f"jobs_export_{ts}.csv"
        else:
            filename = "jobs_export.csv"

        export_path = os.path.join(EXPORT_DIR, filename)

        fieldnames = [
            "id", "remote_id", "title", "company_name", "company_country",
            "category", "job_link", "application_url", "salary",
            "key_preferences", "published_at", "scraped_at",
        ]

        total = 0
        with open(export_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            # Chunked query — never loads all jobs into memory
            offset = 0
            while True:
                chunk = (
                    db.query(Job)
                    .filter(Job.is_active == True)
                    .order_by(Job.id)
                    .offset(offset)
                    .limit(CHUNK_SIZE)
                    .all()
                )
                if not chunk:
                    break

                for j in chunk:
                    writer.writerow({
                        "id": j.id,
                        "remote_id": j.remote_id,
                        "title": j.title,
                        "company_name": j.company_name,
                        "company_country": j.company_country,
                        "category": j.category,
                        "job_link": j.job_link,
                        "application_url": j.application_url,
                        "salary": j.salary,
                        "key_preferences": _parse_prefs(j.key_preferences),
                        "published_at": str(j.published_at) if j.published_at else "",
                        "scraped_at": str(j.scraped_at) if j.scraped_at else "",
                    })

                total += len(chunk)
                offset += CHUNK_SIZE

        logger.info(f"CSV exported: {total} jobs → {export_path}")
        return export_path

    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        return ""


def _parse_prefs(raw) -> str:
    """Convert key_preferences JSON string to comma-separated for CSV readability."""
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return ", ".join(parsed)
    except Exception:
        pass
    return str(raw)