#!/bin/sh
# Start the Celery worker and beat scheduler in the background.
# Optimized for Upstash Free Tier by disabling gossip/mingle to save API limits.
celery -A app.scheduler.celery_worker.celery_app worker -B --loglevel=info --concurrency=1 --without-gossip --without-mingle --without-heartbeat &

# Start the FastAPI web server in the foreground
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
