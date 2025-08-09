"""
Artifact retention and cleanup system for ProofKit.

This module provides automated cleanup of old evidence bundles and artifacts
to prevent unlimited storage growth. Includes background task scheduling
and safe file system operations.

Example usage:
    >>> from core.cleanup import cleanup_old_artifacts, schedule_cleanup
    >>> # Manual cleanup
    >>> cleanup_old_artifacts(retention_days=30)
    >>> # Schedule background cleanup
    >>> schedule_cleanup(retention_days=30, interval_hours=24)
"""

import os
import time
import threading
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

from core.logging import get_logger

# Module logger
logger = get_logger(__name__)

# Global background task control
_cleanup_task: Optional[threading.Thread] = None
_cleanup_stop_event = threading.Event()


def get_retention_days() -> int:
    """
    Get artifact retention period from environment variable.
    
    Returns:
        Number of days to retain artifacts (default: 30)
        
    Example:
        >>> # With RETENTION_DAYS=7 in environment
        >>> days = get_retention_days()
        >>> assert days == 7
    """
    try:
        return int(os.environ.get("RETENTION_DAYS", "30"))
    except ValueError:
        logger.warning("Invalid RETENTION_DAYS value, using default 30")
        return 30


def is_path_safe(path: Path, base_dir: Path) -> bool:
    """
    Verify path is within base directory to prevent path traversal.
    
    Args:
        path: Path to check
        base_dir: Base directory that should contain the path
        
    Returns:
        True if path is safe, False otherwise
        
    Example:
        >>> base = Path("/app/storage")
        >>> safe_path = Path("/app/storage/artifacts/bundle.zip")
        >>> unsafe_path = Path("/etc/passwd") 
        >>> assert is_path_safe(safe_path, base) == True
        >>> assert is_path_safe(unsafe_path, base) == False
    """
    try:
        # Resolve both paths to handle symlinks and relative components
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        
        # Check if resolved path starts with base directory
        return str(resolved_path).startswith(str(resolved_base))
    except (OSError, ValueError):
        # Path resolution failed - not safe
        return False


def calculate_directory_size(directory: Path) -> int:
    """
    Calculate total size of directory and all subdirectories.
    
    Args:
        directory: Directory path to measure
        
    Returns:
        Total size in bytes
        
    Example:
        >>> storage_dir = Path("/app/storage")
        >>> size_bytes = calculate_directory_size(storage_dir)
        >>> size_mb = size_bytes / (1024 * 1024)
    """
    total_size = 0
    
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                try:
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                except (OSError, PermissionError) as e:
                    logger.warning(f"Cannot access file {file_path}: {e}")
                    continue
    except (OSError, PermissionError) as e:
        logger.error(f"Cannot access directory {directory}: {e}")
    
    return total_size


def find_expired_artifacts(
    storage_dir: Path,
    retention_days: int,
    now_provider: Optional[Callable[[], datetime]] = None
) -> List[Tuple[Path, datetime]]:
    """
    Find artifacts older than retention period.
    
    Args:
        storage_dir: Base storage directory to scan
        retention_days: Number of days to retain artifacts
        now_provider: Optional function that returns current datetime (for testing)
        
    Returns:
        List of (path, creation_time) tuples for expired artifacts
        
    Example:
        >>> storage = Path("/app/storage")
        >>> expired = find_expired_artifacts(storage, retention_days=30)
        >>> for path, created in expired:
        ...     print(f"Expired: {path} (created: {created})")
    """
    expired_artifacts: List[Tuple[Path, datetime]] = []
    # Use provided now_provider or default to datetime.now
    current_time = now_provider() if now_provider else datetime.now(timezone.utc)
    cutoff_time = current_time - timedelta(days=retention_days)
    
    # Special retention for LIVE-QA jobs (7 days minimum)
    live_qa_cutoff = current_time - timedelta(days=7)
    
    if not storage_dir.exists():
        logger.info(f"Storage directory does not exist: {storage_dir}")
        return expired_artifacts
    
    try:
        # Walk through storage directory structure
        for item in storage_dir.iterdir():
            if not item.is_dir():
                continue
                
            # Check hash directories (2-char hex)
            if len(item.name) == 2 and all(c in '0123456789abcdef' for c in item.name.lower()):
                for job_dir in item.iterdir():
                    if not job_dir.is_dir():
                        continue
                    
                    # Verify path safety
                    if not is_path_safe(job_dir, storage_dir):
                        logger.warning(f"Unsafe path detected, skipping: {job_dir}")
                        continue
                    
                    try:
                        # Check for LIVE-QA tag in metadata
                        metadata_path = job_dir / "metadata.json"
                        is_live_qa = False
                        if metadata_path.exists():
                            try:
                                import json
                                with open(metadata_path) as f:
                                    metadata = json.load(f)
                                    job_tag = metadata.get("job_tag", "")
                                    if job_tag == "LIVE-QA":
                                        is_live_qa = True
                            except Exception:
                                pass
                        
                        # Get directory creation time
                        stat_info = job_dir.stat()
                        created_time = datetime.fromtimestamp(stat_info.st_ctime, tz=timezone.utc)
                        
                        # Apply appropriate retention policy
                        if is_live_qa:
                            # LIVE-QA jobs get minimum 7 days retention
                            if created_time < live_qa_cutoff:
                                logger.info(f"LIVE-QA job expired: {job_dir}")
                                expired_artifacts.append((job_dir, created_time))
                        else:
                            # Regular jobs use standard retention
                            if created_time < cutoff_time:
                                expired_artifacts.append((job_dir, created_time))
                    
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Cannot access job directory {job_dir}: {e}")
                        continue
    
    except (OSError, PermissionError) as e:
        logger.error(f"Cannot scan storage directory {storage_dir}: {e}")
    
    return expired_artifacts


def remove_artifact_directory(artifact_path: Path, dry_run: bool = False) -> bool:
    """
    Safely remove an artifact directory and all contents.
    
    Args:
        artifact_path: Path to artifact directory to remove
        dry_run: If True, only log what would be removed
        
    Returns:
        True if successful, False otherwise
        
    Example:
        >>> artifact = Path("/app/storage/ab/abc123")
        >>> # Test what would be removed
        >>> remove_artifact_directory(artifact, dry_run=True)
        >>> # Actually remove
        >>> success = remove_artifact_directory(artifact, dry_run=False)
    """
    if not artifact_path.exists():
        logger.info(f"Artifact directory already removed: {artifact_path}")
        return True
    
    if dry_run:
        logger.info(f"DRY RUN: Would remove artifact directory: {artifact_path}")
        return True
    
    try:
        # Calculate size before removal for logging
        size_bytes = calculate_directory_size(artifact_path)
        
        # Remove directory and all contents
        import shutil
        shutil.rmtree(artifact_path)
        
        logger.info(
            f"Removed artifact directory: {artifact_path}",
            extra={
                "artifact_path": str(artifact_path),
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2)
            }
        )
        
        return True
    
    except (OSError, PermissionError) as e:
        logger.error(
            f"Failed to remove artifact directory: {artifact_path}",
            extra={
                "artifact_path": str(artifact_path),
                "error": str(e)
            }
        )
        return False


def cleanup_old_artifacts(
    storage_dir: Optional[Path] = None,
    retention_days: Optional[int] = None,
    dry_run: bool = False,
    now_provider: Optional[Callable[[], datetime]] = None
) -> Dict[str, int]:
    """
    Clean up artifacts older than retention period.
    
    Args:
        storage_dir: Storage directory to clean (default: ./storage)
        retention_days: Days to retain artifacts (default: from env)
        dry_run: If True, only log what would be cleaned
        now_provider: Optional function that returns current datetime (for testing)
        
    Returns:
        Dictionary with cleanup statistics
        
    Example:
        >>> # Clean artifacts older than 30 days
        >>> stats = cleanup_old_artifacts(retention_days=30)
        >>> print(f"Removed {stats['removed']} artifacts, freed {stats['freed_mb']} MB")
    """
    # Set defaults
    if storage_dir is None:
        storage_dir = Path("./storage")
    
    if retention_days is None:
        retention_days = get_retention_days()
    
    logger.info(
        f"Starting artifact cleanup",
        extra={
            "storage_dir": str(storage_dir),
            "retention_days": retention_days,
            "dry_run": dry_run
        }
    )
    
    # Find expired artifacts
    expired_artifacts = find_expired_artifacts(storage_dir, retention_days, now_provider)
    
    # Initialize statistics
    stats = {
        "scanned": 0,
        "expired": len(expired_artifacts),
        "removed": 0,
        "failed": 0,
        "freed_bytes": 0,
        "freed_mb": 0
    }
    
    # Process expired artifacts
    for artifact_path, created_time in expired_artifacts:
        stats["scanned"] += 1
        
        logger.info(
            f"Processing expired artifact",
            extra={
                "artifact_path": str(artifact_path),
                "created_time": created_time.isoformat(),
                "age_days": ((now_provider() if now_provider else datetime.now(timezone.utc)) - created_time).days
            }
        )
        
        # Calculate size before removal
        if not dry_run:
            size_bytes = calculate_directory_size(artifact_path)
            stats["freed_bytes"] += size_bytes
        
        # Remove artifact
        if remove_artifact_directory(artifact_path, dry_run=dry_run):
            stats["removed"] += 1
        else:
            stats["failed"] += 1
    
    # Convert bytes to MB
    stats["freed_mb"] = round(stats["freed_bytes"] / (1024 * 1024), 2)
    
    # Log statsd format metrics
    logger.info(f"cleanup_removed:{stats['removed']}|c")
    if not dry_run and stats['freed_mb'] > 0:
        logger.info(f"cleanup_freed_mb:{stats['freed_mb']}|g")
    
    logger.info(
        f"Artifact cleanup completed",
        extra={
            "statistics": stats,
            "dry_run": dry_run
        }
    )
    
    return stats


def cleanup_background_task(
    storage_dir: Path,
    retention_days: int,
    interval_hours: int,
    stop_event: threading.Event
) -> None:
    """
    Background task that runs periodic cleanup.
    
    Args:
        storage_dir: Storage directory to clean
        retention_days: Days to retain artifacts
        interval_hours: Hours between cleanup runs
        stop_event: Threading event to signal stop
        
    Example:
        >>> stop_event = threading.Event()
        >>> task = threading.Thread(
        ...     target=cleanup_background_task,
        ...     args=(Path("./storage"), 30, 24, stop_event)
        ... )
        >>> task.start()
    """
    logger.info(
        f"Background cleanup task started",
        extra={
            "storage_dir": str(storage_dir),
            "retention_days": retention_days,
            "interval_hours": interval_hours
        }
    )
    
    interval_seconds = interval_hours * 3600
    
    while not stop_event.is_set():
        try:
            # Run cleanup
            stats = cleanup_old_artifacts(
                storage_dir=storage_dir,
                retention_days=retention_days,
                dry_run=False
            )
            
            logger.info(
                f"Background cleanup completed",
                extra={"statistics": stats}
            )
        
        except Exception as e:
            logger.error(
                f"Background cleanup failed",
                extra={"error": str(e)},
                exc_info=True
            )
        
        # Wait for next cleanup or stop signal
        if stop_event.wait(timeout=interval_seconds):
            break  # Stop event was set
    
    logger.info("Background cleanup task stopped")


def schedule_cleanup(
    storage_dir: Optional[Path] = None,
    retention_days: Optional[int] = None,
    interval_hours: int = 24
) -> bool:
    """
    Schedule background cleanup task.
    
    Args:
        storage_dir: Storage directory to clean (default: ./storage)
        retention_days: Days to retain artifacts (default: from env)
        interval_hours: Hours between cleanup runs (default: 24)
        
    Returns:
        True if scheduled successfully, False if already running
        
    Example:
        >>> # Schedule daily cleanup of artifacts older than 30 days
        >>> success = schedule_cleanup(retention_days=30, interval_hours=24)
        >>> if success:
        ...     print("Cleanup scheduled successfully")
    """
    global _cleanup_task, _cleanup_stop_event
    
    # Check if already running
    if _cleanup_task and _cleanup_task.is_alive():
        logger.warning("Background cleanup task already running")
        return False
    
    # Set defaults
    if storage_dir is None:
        storage_dir = Path("./storage")
    
    if retention_days is None:
        retention_days = get_retention_days()
    
    # Reset stop event
    _cleanup_stop_event.clear()
    
    # Create and start background task
    _cleanup_task = threading.Thread(
        target=cleanup_background_task,
        args=(storage_dir, retention_days, interval_hours, _cleanup_stop_event),
        daemon=True,
        name="ProofKit-Cleanup"
    )
    
    _cleanup_task.start()
    
    logger.info(
        f"Background cleanup task scheduled",
        extra={
            "storage_dir": str(storage_dir),
            "retention_days": retention_days,
            "interval_hours": interval_hours
        }
    )
    
    return True


def stop_cleanup() -> bool:
    """
    Stop the background cleanup task.
    
    Returns:
        True if stopped successfully, False if not running
        
    Example:
        >>> # Stop background cleanup
        >>> success = stop_cleanup()
        >>> if success:
        ...     print("Cleanup task stopped")
    """
    global _cleanup_task, _cleanup_stop_event
    
    if not _cleanup_task or not _cleanup_task.is_alive():
        logger.info("Background cleanup task not running")
        return False
    
    # Signal stop
    _cleanup_stop_event.set()
    
    # Wait for task to complete (with timeout)
    _cleanup_task.join(timeout=10.0)
    
    if _cleanup_task.is_alive():
        logger.warning("Background cleanup task did not stop within timeout")
        return False
    
    logger.info("Background cleanup task stopped successfully")
    return True