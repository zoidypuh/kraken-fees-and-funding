#!/bin/bash

# Start Celery worker for Kraken Dashboard

echo "Starting Celery worker..."
echo "================================"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set development environment
export FLASK_DEBUG=false
export USE_REDIS_BROKER=false  # Use in-memory broker for development

# Start Celery with info logging
celery -A celery_app worker --loglevel=info --concurrency=2 -n kraken_worker@%h

# For production with Redis:
# export USE_REDIS_BROKER=true
# export REDIS_URL=redis://localhost:6379/0
# celery -A celery_app worker --loglevel=info --concurrency=4 -n kraken_worker@%h 