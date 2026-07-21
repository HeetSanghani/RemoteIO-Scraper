from sqlalchemy.orm import Session
from app.database.models.job import Job
from app.utils.logger import logger


def get_existing_remote_ids(db: Session) -> set:
    """Fetch all existing remote_ids from DB as a set for fast lookup."""
    ids = db.query(Job.remote_id).all()
    return {row[0] for row in ids}


def filter_new_jobs(db: Session, parsed_jobs: list[dict]) -> list[dict]:
    """Return only jobs that don't already exist in DB."""
    existing_ids = get_existing_remote_ids(db)
    new_jobs = [j for j in parsed_jobs if j["remote_id"] not in existing_ids]
    logger.info(f"Dedup: {len(parsed_jobs)} total → {len(new_jobs)} new → {len(parsed_jobs) - len(new_jobs)} skipped")
    return new_jobs