"""
Background task scheduler for ProofKit production operations.

Handles automated cleanup and backup tasks without requiring cron.
"""

import os
import time
import logging
import threading
import subprocess
from datetime import datetime, timezone
from typing import Optional

from core.cleanup import cleanup_old_artifacts

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackgroundScheduler:
    """Simple background task scheduler for production operations."""
    
    def __init__(self):
        self.running = False
        self.cleanup_thread: Optional[threading.Thread] = None
        self.backup_thread: Optional[threading.Thread] = None
        
    def start(self):
        """Start background scheduler threads."""
        if self.running:
            logger.warning("Scheduler already running")
            return
            
        self.running = True
        logger.info("Starting background scheduler")
        
        # Start cleanup scheduler thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_scheduler, daemon=True)
        self.cleanup_thread.start()
        
        # Start backup scheduler thread  
        self.backup_thread = threading.Thread(target=self._backup_scheduler, daemon=True)
        self.backup_thread.start()
        
        logger.info("Background scheduler started successfully")
    
    def stop(self):
        """Stop background scheduler."""
        self.running = False
        logger.info("Background scheduler stopped")
    
    def _cleanup_scheduler(self):
        """Run cleanup task daily at 2:00 AM UTC."""
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Check if it's 2:00 AM UTC (allow 1-minute window)
                if current_time.hour == 2 and current_time.minute == 0:
                    logger.info("Starting scheduled cleanup task")
                    
                    try:
                        # Run cleanup
                        removed_count = cleanup_old_artifacts()
                        logger.info(f"Cleanup completed: {removed_count} artifacts removed")
                        
                        # Log metrics in statsd format
                        print(f"cleanup_removed:{removed_count}|c")
                        
                        # Sleep for 70 seconds to avoid running multiple times in the same minute
                        time.sleep(70)
                        
                    except Exception as e:
                        logger.error(f"Cleanup task failed: {e}")
                        
                else:
                    # Sleep for 30 seconds and check again
                    time.sleep(30)
                    
            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {e}")
                time.sleep(60)  # Wait a minute before retrying
    
    def _backup_scheduler(self):
        """Run backup task daily at 2:00 AM UTC."""
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Check if it's 2:00 AM UTC and we have AWS credentials
                if (current_time.hour == 2 and current_time.minute == 0 and 
                    self._has_backup_credentials()):
                    
                    logger.info("Starting scheduled backup task")
                    
                    try:
                        # Run backup script
                        backup_script = "/app/scripts/backup_to_s3.sh"
                        if os.path.exists(backup_script):
                            result = subprocess.run(
                                [backup_script], 
                                capture_output=True, 
                                text=True,
                                timeout=300  # 5 minute timeout
                            )
                            
                            if result.returncode == 0:
                                logger.info("Backup completed successfully")
                                print("backup_success:1|c")
                            else:
                                logger.error(f"Backup failed: {result.stderr}")
                                print("backup_failed:1|c")
                        else:
                            logger.warning("Backup script not found, skipping backup")
                        
                        # Sleep for 70 seconds to avoid running multiple times
                        time.sleep(70)
                        
                    except Exception as e:
                        logger.error(f"Backup task failed: {e}")
                        print("backup_failed:1|c")
                        
                else:
                    # Sleep for 30 seconds and check again
                    time.sleep(30)
                    
            except Exception as e:
                logger.error(f"Error in backup scheduler: {e}")
                time.sleep(60)  # Wait a minute before retrying
    
    def _has_backup_credentials(self) -> bool:
        """Check if AWS backup credentials are available."""
        return all([
            os.environ.get("S3_BUCKET"),
            os.environ.get("AWS_ACCESS_KEY_ID"), 
            os.environ.get("AWS_SECRET_ACCESS_KEY")
        ])


# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None

def start_background_tasks():
    """Start background task scheduler."""
    global _scheduler
    
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    else:
        logger.warning("Background tasks already started")

def stop_background_tasks():
    """Stop background task scheduler."""
    global _scheduler
    
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


if __name__ == "__main__":
    # For testing
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    try:
        # Keep running
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()
        print("Scheduler stopped")