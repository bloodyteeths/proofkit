"""
TSA (Time Stamp Authority) resilient implementation for ProofKit.

Provides non-blocking timestamp generation with retry queuing for RFC 3161 TSA services.
When TSA is unreachable, certificates are marked "Timestamp pending" and retry jobs are queued.

Example usage:
    from core.timestamp import get_timestamp_with_retry, process_retry_queue
    
    # Get timestamp with resilient fallback
    timestamp_info = get_timestamp_with_retry(pdf_content, job_id="batch_001")
    
    # Process retry queue (called by scheduler)
    process_retry_queue()
"""

import hashlib
import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, asdict
from threading import Lock

# TSA compliance imports
try:
    from cryptography.hazmat.primitives import hashes
    import rfc3161ng
    TSA_AVAILABLE = True
except ImportError:
    TSA_AVAILABLE = False

logger = logging.getLogger(__name__)

# RFC 3161 TSA URLs (using public TSAs)
RFC3161_TSA_URLS = [
    'http://timestamp.apple.com/ts01',
    'http://time.certum.pl',
    'http://timestamp.digicert.com'
]

# Retry queue configuration
RETRY_QUEUE_DIR = Path("/tmp/tsa_retry_queue")
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 300  # 5 minutes
RETRY_MAX_AGE_HOURS = 24

# Thread-safe lock for queue operations
_queue_lock = Lock()


@dataclass
class TimestampRetryJob:
    """Represents a pending TSA timestamp retry job."""
    job_id: str
    pdf_path: str
    pdf_hash: str
    created_at: datetime
    attempts: int = 0
    last_attempt_at: Optional[datetime] = None
    tsa_errors: List[str] = None
    
    def __post_init__(self):
        if self.tsa_errors is None:
            self.tsa_errors = []


@dataclass  
class TimestampResult:
    """Result of timestamp generation attempt."""
    success: bool
    timestamp: Optional[bytes] = None
    timestamp_info: Optional[Dict[str, Any]] = None
    pending: bool = False
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _ensure_retry_queue_dir():
    """Ensure retry queue directory exists."""
    RETRY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def _generate_rfc3161_timestamp(pdf_content: bytes) -> Optional[bytes]:
    """
    Generate RFC 3161 timestamp for PDF content.
    
    Args:
        pdf_content: PDF content as bytes
        
    Returns:
        RFC 3161 timestamp token or None if failed
    """
    if not TSA_AVAILABLE:
        return None
    
    try:
        # Calculate hash of PDF content
        digest = hashes.Hash(hashes.SHA256())
        digest.update(pdf_content)
        data_hash = digest.finalize()
        
        # Try each TSA URL with timeout
        for tsa_url in RFC3161_TSA_URLS:
            try:
                logger.debug(f"Attempting TSA request to {tsa_url}")
                rt = rfc3161ng.RemoteTimestamper(tsa_url, hashname='sha256', timeout=10)
                
                timestamp = rt.timestamp(data=data_hash)
                if timestamp:
                    logger.info(f"Successfully obtained timestamp from {tsa_url}")
                    return timestamp
                    
            except Exception as e:
                logger.warning(f"TSA {tsa_url} failed: {e}")
                continue
        
        logger.warning("All TSA URLs failed")
        return None
        
    except Exception as e:
        logger.error(f"RFC 3161 timestamp generation failed: {e}")
        return None


def get_timestamp_with_retry(pdf_content: bytes, 
                           job_id: str,
                           pdf_path: Optional[str] = None,
                           now_provider: Optional[Callable[[], datetime]] = None) -> TimestampResult:
    """
    Get RFC 3161 timestamp with resilient retry fallback.
    
    Args:
        pdf_content: PDF content to timestamp
        job_id: Job identifier for retry tracking
        pdf_path: Optional path to PDF file (for retry jobs)
        now_provider: Optional function to provide current datetime (for testing)
        
    Returns:
        TimestampResult with success status and optional timestamp
    """
    timestamp_now = now_provider() if now_provider else datetime.now(timezone.utc)
    
    # First attempt to get timestamp
    timestamp_token = _generate_rfc3161_timestamp(pdf_content)
    
    if timestamp_token:
        # Success case - return timestamp info
        timestamp_info = {
            'timestamp': timestamp_now.isoformat(),
            'token': timestamp_token.hex(),
            'token_length': len(timestamp_token),
            'tsa_status': 'success'
        }
        return TimestampResult(
            success=True,
            timestamp=timestamp_token,
            timestamp_info=timestamp_info
        )
    
    # TSA failed - queue for retry if PDF path provided
    if pdf_path:
        try:
            pdf_hash = hashlib.sha256(pdf_content).hexdigest()
            retry_job = TimestampRetryJob(
                job_id=job_id,
                pdf_path=pdf_path,
                pdf_hash=pdf_hash,
                created_at=timestamp_now
            )
            _queue_retry_job(retry_job)
            logger.info(f"TSA failed, queued retry job for {job_id}")
        except Exception as e:
            logger.error(f"Failed to queue retry job for {job_id}: {e}")
    
    # Return pending result
    timestamp_info = {
        'timestamp': timestamp_now.isoformat(),
        'token': None,
        'token_length': 0,
        'tsa_status': 'pending',
        'retry_queued': pdf_path is not None
    }
    
    return TimestampResult(
        success=False,
        pending=True,
        timestamp_info=timestamp_info,
        errors=['TSA unavailable - timestamp pending']
    )


def _queue_retry_job(retry_job: TimestampRetryJob):
    """
    Add retry job to queue.
    
    Args:
        retry_job: Job to queue for retry
    """
    with _queue_lock:
        _ensure_retry_queue_dir()
        
        job_file = RETRY_QUEUE_DIR / f"{retry_job.job_id}.json"
        
        # Convert datetime objects to ISO strings for JSON serialization
        job_data = asdict(retry_job)
        job_data['created_at'] = retry_job.created_at.isoformat()
        if retry_job.last_attempt_at:
            job_data['last_attempt_at'] = retry_job.last_attempt_at.isoformat()
        
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=2)
        
        logger.debug(f"Queued retry job: {job_file}")


def _load_retry_job(job_file: Path) -> Optional[TimestampRetryJob]:
    """
    Load retry job from file.
    
    Args:
        job_file: Path to job file
        
    Returns:
        TimestampRetryJob or None if failed to load
    """
    try:
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Convert ISO strings back to datetime objects
        job_data['created_at'] = datetime.fromisoformat(job_data['created_at'])
        if job_data.get('last_attempt_at'):
            job_data['last_attempt_at'] = datetime.fromisoformat(job_data['last_attempt_at'])
        
        return TimestampRetryJob(**job_data)
        
    except Exception as e:
        logger.error(f"Failed to load retry job {job_file}: {e}")
        return None


def _remove_retry_job(job_file: Path):
    """Remove retry job file."""
    try:
        job_file.unlink()
        logger.debug(f"Removed retry job: {job_file}")
    except Exception as e:
        logger.warning(f"Failed to remove retry job {job_file}: {e}")


def process_retry_queue(now_provider: Optional[Callable[[], datetime]] = None) -> Dict[str, int]:
    """
    Process TSA retry queue - called by scheduler.
    
    Args:
        now_provider: Optional function to provide current datetime (for testing)
        
    Returns:
        Dictionary with processing statistics
    """
    current_time = now_provider() if now_provider else datetime.now(timezone.utc)
    
    stats = {
        'jobs_processed': 0,
        'jobs_succeeded': 0,
        'jobs_failed': 0,
        'jobs_expired': 0,
        'jobs_deferred': 0
    }
    
    if not RETRY_QUEUE_DIR.exists():
        return stats
    
    with _queue_lock:
        # Process all job files
        for job_file in RETRY_QUEUE_DIR.glob("*.json"):
            retry_job = _load_retry_job(job_file)
            if not retry_job:
                _remove_retry_job(job_file)
                continue
            
            stats['jobs_processed'] += 1
            
            # Check if job has expired
            age = current_time - retry_job.created_at
            if age > timedelta(hours=RETRY_MAX_AGE_HOURS):
                logger.warning(f"Retry job {retry_job.job_id} expired after {age}")
                _remove_retry_job(job_file)
                stats['jobs_expired'] += 1
                continue
            
            # Check if we should retry (wait between attempts)
            if retry_job.last_attempt_at:
                time_since_last = current_time - retry_job.last_attempt_at
                if time_since_last < timedelta(seconds=RETRY_DELAY_SECONDS):
                    stats['jobs_deferred'] += 1
                    continue
            
            # Check max attempts
            if retry_job.attempts >= MAX_RETRY_ATTEMPTS:
                logger.warning(f"Retry job {retry_job.job_id} max attempts reached")
                _remove_retry_job(job_file)
                stats['jobs_failed'] += 1
                continue
            
            # Attempt to process the job
            success = _process_retry_job(retry_job, current_time)
            
            if success:
                logger.info(f"Retry job {retry_job.job_id} succeeded")
                _remove_retry_job(job_file)
                stats['jobs_succeeded'] += 1
            else:
                # Update job with failed attempt and save back
                retry_job.attempts += 1
                retry_job.last_attempt_at = current_time
                _queue_retry_job(retry_job)
                stats['jobs_deferred'] += 1
    
    if stats['jobs_processed'] > 0:
        logger.info(f"TSA retry queue processed: {stats}")
    
    return stats


def _process_retry_job(retry_job: TimestampRetryJob, current_time: datetime) -> bool:
    """
    Process a single retry job.
    
    Args:
        retry_job: Job to process
        current_time: Current timestamp
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if PDF file still exists
        if not os.path.exists(retry_job.pdf_path):
            logger.warning(f"PDF file not found for retry job {retry_job.job_id}: {retry_job.pdf_path}")
            return True  # Consider it successful (nothing to do)
        
        # Read PDF content
        with open(retry_job.pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        # Verify PDF hasn't changed
        current_hash = hashlib.sha256(pdf_content).hexdigest()
        if current_hash != retry_job.pdf_hash:
            logger.warning(f"PDF content changed for retry job {retry_job.job_id}")
            return True  # Consider it successful (PDF changed, nothing to do)
        
        # Attempt to get timestamp
        timestamp_token = _generate_rfc3161_timestamp(pdf_content)
        
        if timestamp_token:
            # TODO: Update the PDF with the timestamp and re-save
            # This would require implementing PDF metadata updating
            logger.info(f"Successfully obtained timestamp for retry job {retry_job.job_id}")
            return True
        else:
            logger.debug(f"TSA still unavailable for retry job {retry_job.job_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing retry job {retry_job.job_id}: {e}")
        retry_job.tsa_errors.append(str(e))
        return False


def get_retry_queue_status() -> Dict[str, Any]:
    """
    Get current retry queue status.
    
    Returns:
        Dictionary with queue status information
    """
    if not RETRY_QUEUE_DIR.exists():
        return {
            'queue_size': 0,
            'oldest_job': None,
            'queue_directory_exists': False
        }
    
    job_files = list(RETRY_QUEUE_DIR.glob("*.json"))
    
    status = {
        'queue_size': len(job_files),
        'oldest_job': None,
        'newest_job': None,
        'queue_directory_exists': True
    }
    
    if job_files:
        # Find oldest and newest jobs
        oldest_mtime = float('inf')
        newest_mtime = 0
        
        for job_file in job_files:
            mtime = job_file.stat().st_mtime
            if mtime < oldest_mtime:
                oldest_mtime = mtime
                status['oldest_job'] = {
                    'file': job_file.name,
                    'created': datetime.fromtimestamp(mtime, timezone.utc).isoformat()
                }
            if mtime > newest_mtime:
                newest_mtime = mtime
                status['newest_job'] = {
                    'file': job_file.name,  
                    'created': datetime.fromtimestamp(mtime, timezone.utc).isoformat()
                }
    
    return status


def clear_retry_queue() -> int:
    """
    Clear all jobs from retry queue (for testing).
    
    Returns:
        Number of jobs cleared
    """
    if not RETRY_QUEUE_DIR.exists():
        return 0
    
    count = 0
    with _queue_lock:
        for job_file in RETRY_QUEUE_DIR.glob("*.json"):
            _remove_retry_job(job_file)
            count += 1
    
    return count


# Usage example in comments:
"""
Example usage for TSA resilient timestamping:

from core.timestamp import get_timestamp_with_retry, process_retry_queue

# Generate PDF with resilient TSA timestamping
pdf_bytes = generate_pdf(...)

# Try to get timestamp - will queue for retry if TSA unavailable
result = get_timestamp_with_retry(
    pdf_content=pdf_bytes,
    job_id="batch_001",
    pdf_path="/tmp/proof.pdf"
)

if result.success:
    print(f"Timestamp obtained: {result.timestamp_info['timestamp']}")
elif result.pending:
    print("Timestamp pending - retry job queued")

# In scheduler (called periodically)
stats = process_retry_queue()
print(f"Processed {stats['jobs_processed']} retry jobs")
"""