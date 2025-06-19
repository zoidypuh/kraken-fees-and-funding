"""
Celery configuration for Kraken Dashboard
"""
from celery import Celery
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Determine broker URL - use Redis if available, otherwise use in-memory for development
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
USE_REDIS = os.environ.get('USE_REDIS_BROKER', 'true').lower() == 'true'

# Test Redis connection
broker_url = REDIS_URL
backend_url = REDIS_URL

if USE_REDIS:
    try:
        import redis
        r = redis.from_url(REDIS_URL)
        r.ping()
        print(f"✓ Connected to Redis at {REDIS_URL}")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        print("  Falling back to in-memory broker (development only)")
        broker_url = 'memory://'
        backend_url = 'cache+memory://'
else:
    print("Using in-memory broker (development only)")
    broker_url = 'memory://'
    backend_url = 'cache+memory://'

# Initialize Celery
celery_app = Celery(
    'kraken_dashboard',
    broker=broker_url,
    backend=backend_url,
    include=['tasks']  # Include the tasks module
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    result_expires=3600,  # Results expire after 1 hour
)

# Configure task routes (optional)
celery_app.conf.task_routes = {
    'tasks.calculate_position_data_async': {'queue': 'positions'},
    'tasks.batch_calculate_positions': {'queue': 'positions'},
    'tasks.update_chart_data_async': {'queue': 'charts'},
} 