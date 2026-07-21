#!/bin/sh
# Start the Celery worker in the background
celery -A app.scheduler.celery_worker.celery_app worker --loglevel=info &

# Start the FastAPI web server in the foreground
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
