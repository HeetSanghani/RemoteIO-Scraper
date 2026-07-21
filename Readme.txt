# Terminal 1 — FastAPI
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Celery Worker (optional)
celery -A app.scheduler.celery_worker.celery_app worker --loglevel=info

# Terminal 3 — Celery Beat (optional)
celery -A app.scheduler.scheduler.celery_app beat --loglevel=info

# Manual scrape anytime
python -c "
from app.scraper.scraper_service import run_scraper
from app.services.job_service import save_jobs
from app.exports.csv_exporter import export_jobs_to_csv
from app.database.database import SessionLocal
jobs = run_scraper()
db = SessionLocal()
save_jobs(db, jobs)
export_jobs_to_csv(db)
db.close()
print('Done!')
"



# Docker

docker compose exec api python -c "
from app.scraper.scraper_service import run_scraper
from app.services.job_service import save_jobs
from app.exports.csv_exporter import export_jobs_to_csv
from app.database.database import SessionLocal
jobs = run_scraper()
db = SessionLocal()
save_jobs(db, jobs)
export_jobs_to_csv(db)
db.close()
print('Done!')
"


# fuser -k 8000/tcp

