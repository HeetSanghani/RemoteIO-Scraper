#!/bin/sh
# Start the Celery worker in the background with limited concurrency to save memory on free tier
celery -A app.scheduler.celery_worker.celery_app worker --loglevel=info --concurrency=1 &

# Start the FastAPI web server in the foreground
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
