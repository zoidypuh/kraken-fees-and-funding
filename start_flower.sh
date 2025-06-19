#!/bin/bash

# Start Flower monitoring for Celery

echo "Starting Flower monitoring..."
echo "================================"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set development environment
export USE_REDIS_BROKER=false  # Use in-memory broker for development

# Start Flower on port 5555
echo "Flower will be available at http://localhost:5555"
celery -A celery_app flower --port=5555

# For production with Redis:
# export USE_REDIS_BROKER=true
# export REDIS_URL=redis://localhost:6379/0
# celery -A celery_app flower --port=5555 --basic_auth=admin:password 