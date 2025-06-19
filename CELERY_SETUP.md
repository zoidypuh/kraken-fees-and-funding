# Celery Task Queue Setup (Future Implementation)

This document outlines how to implement Celery for long-running operations in the Kraken Dashboard.

## When to Use Celery

Consider implementing Celery when:
- Position calculations take more than 30 seconds
- You need to process historical data in the background
- You want to schedule periodic data updates
- Multiple users are accessing the dashboard simultaneously

## Installation

```bash
pip install celery[redis]==5.3.4
pip install flower==2.0.1  # For monitoring
```

## Basic Setup

### 1. Create `celery_app.py`:

```python
from celery import Celery
import os

# Initialize Celery
celery_app = Celery(
    'kraken_dashboard',
    broker=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
)
```

### 2. Create `tasks.py`:

```python
from celery_app import celery_app
from kraken_client import get_position_accumulated_data
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def calculate_position_data_async(self, api_key, api_secret, position):
    """Calculate position data asynchronously."""
    try:
        return get_position_accumulated_data(api_key, api_secret, position)
    except Exception as exc:
        logger.error(f"Task failed: {exc}")
        raise self.retry(exc=exc, countdown=60)  # Retry after 1 minute

@celery_app.task
def batch_calculate_positions(api_key, api_secret, positions):
    """Calculate multiple positions in parallel."""
    from celery import group
    
    # Create a group of tasks
    job = group(
        calculate_position_data_async.s(api_key, api_secret, pos) 
        for pos in positions
    )
    
    # Execute and return results
    result = job.apply_async()
    return result.get(timeout=120)  # 2 minute timeout
```

### 3. Update app.py to use Celery:

```python
from tasks import calculate_position_data_async, batch_calculate_positions

# In your endpoint
@app.route('/api/positions-async')
@require_api_credentials
def get_positions_async(api_key, api_secret):
    """Get positions with async calculation."""
    positions = get_open_positions(api_key, api_secret)
    
    # Start async task
    task = batch_calculate_positions.delay(api_key, api_secret, positions)
    
    return jsonify({
        'task_id': task.id,
        'status': 'processing',
        'positions_count': len(positions)
    })

@app.route('/api/task-status/<task_id>')
def get_task_status(task_id):
    """Check task status."""
    from celery.result import AsyncResult
    
    task = AsyncResult(task_id)
    
    if task.state == 'PENDING':
        response = {'state': task.state, 'status': 'Task pending...'}
    elif task.state == 'SUCCESS':
        response = {'state': task.state, 'result': task.result}
    else:
        response = {'state': task.state, 'error': str(task.info)}
    
    return jsonify(response)
```

## Running Celery

### Development:
```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Celery worker
celery -A celery_app worker --loglevel=info

# Terminal 3: Start Flower (monitoring)
celery -A celery_app flower

# Terminal 4: Start Flask app
python app.py
```

### Production:
Use supervisor or systemd to manage Celery workers:

```ini
# /etc/supervisor/conf.d/celery.conf
[program:celery]
command=/path/to/venv/bin/celery -A celery_app worker --loglevel=info
directory=/path/to/kraken-dashboard
user=www-data
numprocs=1
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker.log
autostart=true
autorestart=true
startsecs=10
```

## Frontend Integration

Update the JavaScript to handle async tasks:

```javascript
function refreshPositionsAsync() {
    fetch('/api/positions-async')
        .then(response => response.json())
        .then(data => {
            if (data.task_id) {
                // Poll for results
                pollTaskStatus(data.task_id);
            }
        });
}

function pollTaskStatus(taskId) {
    const interval = setInterval(() => {
        fetch(`/api/task-status/${taskId}`)
            .then(response => response.json())
            .then(data => {
                if (data.state === 'SUCCESS') {
                    clearInterval(interval);
                    updatePositions(data.result);
                } else if (data.state === 'FAILURE') {
                    clearInterval(interval);
                    console.error('Task failed:', data.error);
                }
            });
    }, 1000);  // Poll every second
}
```

## Benefits

1. **Non-blocking**: Long calculations don't block the web server
2. **Scalable**: Can add more workers as needed
3. **Reliable**: Failed tasks can be retried automatically
4. **Monitorable**: Flower provides a web UI for monitoring tasks

## When to Implement

Consider implementing when:
- Users complain about timeouts
- You have > 10 concurrent users
- Position calculations take > 30 seconds
- You need scheduled tasks (daily reports, etc.) 