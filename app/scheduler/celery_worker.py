from celery import Celery
import os
from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "remoteio_scraper",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.scheduler.celery_tasks"]
)

import ssl

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

if REDIS_URL.startswith("rediss://"):
    celery_app.conf.update(
        broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
        redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )

celery_app.conf.beat_schedule = {
    "scrape-every-hour": {
        "task": "scrape_and_save_jobs",
        "schedule": crontab(minute=0, hour="*"),  # top of every hour
    },
}