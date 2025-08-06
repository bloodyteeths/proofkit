# 🕒 ProofKit Background Task Scheduler

## Implementation Summary

ProofKit now uses a **Python-based background scheduler** instead of cron jobs, making it compatible with Docker containers without cron dependencies.

## How It Works

### 1. Background Scheduler (`core/scheduler.py`)
- **Pure Python**: No external dependencies on cron or system services
- **Thread-based**: Runs cleanup and backup tasks in separate daemon threads
- **Production-ready**: Comprehensive error handling and logging
- **Docker-compatible**: Works in any Python environment

### 2. Integration with FastAPI (`app.py`)
```python
@app.on_event("startup")
async def startup_event():
    """Start background scheduler on application startup."""
    start_background_tasks()

@app.on_event("shutdown") 
async def shutdown_event():
    """Stop background scheduler on application shutdown."""
    stop_background_tasks()
```

### 3. Automated Tasks

#### **Daily Cleanup (2:00 AM UTC)**
- Removes artifacts older than `RETENTION_DAYS` (default: 14 days)
- Logs metrics in statsd format: `cleanup_removed:N|c`
- Comprehensive error handling and retry logic

#### **Daily Backup (2:00 AM UTC)**  
- Runs `/app/scripts/backup_to_s3.sh` if AWS credentials available
- Logs success/failure metrics: `backup_success:1|c` or `backup_failed:1|c`
- 5-minute timeout protection
- Graceful handling when AWS credentials not configured

## Production Benefits

### ✅ **Container Compatibility**
- No cron dependencies required
- Works in Python slim Docker images
- Starts automatically with the application

### ✅ **Reliable Operation**
- Thread-safe implementation
- Automatic error recovery
- Comprehensive logging for debugging

### ✅ **Monitoring Integration**
- Statsd metrics for observability
- Structured logging for analysis
- Health status reporting

### ✅ **Configuration Flexibility**
- Environment variable driven
- Graceful handling of missing credentials
- Easy to test and debug

## Configuration

### Environment Variables
```bash
RETENTION_DAYS=14              # Cleanup retention period
S3_BUCKET=proofkit-backups     # S3 bucket for backups
AWS_ACCESS_KEY_ID=xxx          # AWS credentials
AWS_SECRET_ACCESS_KEY=xxx      # AWS credentials
```

### Fly.io Secrets
```bash
fly secrets set S3_BUCKET=proofkit-backups-prod
fly secrets set AWS_ACCESS_KEY_ID=AKIAI...
fly secrets set AWS_SECRET_ACCESS_KEY=xxx...
```

## Monitoring & Metrics

### Statsd Metrics Emitted
```
cleanup_removed:5|c           # Number of artifacts cleaned up
backup_success:1|c            # Backup completed successfully  
backup_failed:1|c             # Backup failed
```

### Log Messages
```
[INFO] Starting background scheduler
[INFO] Starting scheduled cleanup task
[INFO] Cleanup completed: 5 artifacts removed
[INFO] Starting scheduled backup task  
[INFO] Backup completed successfully
```

## Testing & Verification

### Local Testing
```bash
# Test the scheduler directly
python core/scheduler.py

# Check logs for task execution
tail -f logs/app.log | grep "cleanup\|backup"
```

### Production Verification
```bash
# Check Fly.io logs
fly logs --app proofkit-prod | grep "cleanup\|backup"

# Verify metrics are being emitted
fly logs --app proofkit-prod | grep "cleanup_removed\|backup_"
```

## Deployment Changes

### ✅ **Simplified fly.toml**
- No complex `release_command` required
- Clean deployment configuration
- Automatic task startup with application

### ✅ **Zero Manual Setup**
- Tasks start automatically on app startup
- No additional deployment steps needed
- Works immediately after `fly deploy`

## Migration Notes

**Previous Approach**: Cron-based release_command (incompatible with Docker)
```bash
# This didn't work in Python slim containers
release_command = "crontab -l | ..."
```

**New Approach**: Python background threads (Docker-compatible)
```python
# This works in any Python environment
start_background_tasks()
```

## Architecture Benefits

1. **Simplicity**: Single Python process handles all tasks
2. **Reliability**: Built-in error handling and retry logic
3. **Observability**: Structured logging and metrics
4. **Maintainability**: Pure Python, no external dependencies
5. **Testability**: Easy to unit test and debug

---

**Status**: ✅ **Production Ready**  
**Compatibility**: ✅ **Docker/Fly.io Compatible**  
**Monitoring**: ✅ **Integrated with Logging/Metrics**