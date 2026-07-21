from celery.schedules import crontab
from app.scheduler.celery_worker import celery_app

celery_app.conf.beat_schedule = {
    "scrape-every-hour": {
        "task": "scrape_and_save_jobs",
        "schedule": crontab(minute=0, hour="*"),  # Every hour
    },
}