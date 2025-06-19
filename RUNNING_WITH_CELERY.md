# Running Kraken Dashboard with Celery

This guide explains how to run the Kraken Dashboard with Celery for improved performance and background task processing.

## Quick Start (Development)

### Without Redis (In-Memory Broker)

1. **Terminal 1 - Start Celery Worker:**
   ```bash
   ./start_celery.sh
   ```

2. **Terminal 2 - Start Flower (Optional, for monitoring):**
   ```bash
   ./start_flower.sh
   ```
   Then visit http://localhost:5555 to see the Celery monitoring dashboard.

3. **Terminal 3 - Start Flask App:**
   ```bash
   python app.py
   ```

### With Redis

1. **Install and Start Redis:**
   ```bash
   # Install Redis (Ubuntu/WSL)
   sudo apt update
   sudo apt install redis-server
   
   # Start Redis
   redis-server
   ```

2. **Set Environment Variables:**
   ```bash
   export USE_REDIS_BROKER=true
   export USE_REDIS_CACHE=true
   export REDIS_URL=redis://localhost:6379/0
   ```

3. **Start Services:**
   Follow the same steps as above (Celery, Flower, Flask)

## Features with Celery

When Celery is running, the dashboard automatically:

1. **Async Position Calculations**: Long-running position calculations are processed in the background
2. **Non-blocking UI**: The interface remains responsive while calculations run
3. **Automatic Fallback**: If Celery is not available, the app falls back to synchronous processing
4. **Progress Indicators**: Shows "processing in background..." while tasks run

## Environment Variables

- `USE_REDIS_BROKER`: Set to `true` to use Redis, `false` for in-memory (default: `false`)
- `REDIS_URL`: Redis connection URL (default: `redis://localhost:6379/0`)
- `USE_REDIS_CACHE`: Set to `true` to use Redis for caching (default: `false`)
- `USE_ASYNC_API`: Set to `true` to use async API client (default: `true`)

## Production Setup

For production, use a process manager like Supervisor or systemd:

### Supervisor Configuration

Create `/etc/supervisor/conf.d/kraken-celery.conf`:

```ini
[program:kraken-celery]
command=/path/to/venv/bin/celery -A celery_app worker --loglevel=info
directory=/path/to/kraken-dashboard
user=www-data
numprocs=1
stdout_logfile=/var/log/kraken/celery.log
stderr_logfile=/var/log/kraken/celery.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600

[program:kraken-flower]
command=/path/to/venv/bin/celery -A celery_app flower --port=5555 --basic_auth=admin:secretpassword
directory=/path/to/kraken-dashboard
user=www-data
stdout_logfile=/var/log/kraken/flower.log
stderr_logfile=/var/log/kraken/flower.log
autostart=true
autorestart=true
```

### Systemd Service

Create `/etc/systemd/system/kraken-celery.service`:

```ini
[Unit]
Description=Kraken Dashboard Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/path/to/kraken-dashboard
Environment="PATH=/path/to/venv/bin"
Environment="USE_REDIS_BROKER=true"
Environment="REDIS_URL=redis://localhost:6379/0"
ExecStart=/path/to/venv/bin/celery -A celery_app worker --detach --loglevel=info

[Install]
WantedBy=multi-user.target
```

## Monitoring

### Flower Dashboard

Flower provides a web interface for monitoring Celery:
- View active tasks
- Monitor worker status
- See task history
- Inspect task details

Access at: http://localhost:5555

### Command Line

Check Celery status:
```bash
celery -A celery_app status
celery -A celery_app inspect active
celery -A celery_app inspect stats
```

## Troubleshooting

### Celery Worker Not Starting

1. Check if Redis is running (if using Redis):
   ```bash
   redis-cli ping
   ```

2. Check Celery logs:
   ```bash
   celery -A celery_app worker --loglevel=debug
   ```

### Tasks Not Processing

1. Verify workers are running:
   ```bash
   celery -A celery_app inspect active_queues
   ```

2. Check for errors in task execution:
   ```bash
   celery -A celery_app events
   ```

### Memory Issues

If using in-memory broker and experiencing memory issues:
1. Switch to Redis
2. Reduce worker concurrency
3. Set task result expiration:
   ```python
   celery_app.conf.result_expires = 3600  # 1 hour
   ```

## Performance Tips

1. **Use Redis**: Much more efficient than in-memory broker
2. **Adjust Concurrency**: Set based on CPU cores and task types
3. **Monitor Memory**: Use Flower to track memory usage
4. **Task Timeouts**: Set appropriate timeouts to prevent hanging tasks
5. **Result Backend**: Use Redis for result backend in production 