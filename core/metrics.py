"""
ProofKit Application Metrics Collection

This module provides metrics collection for the three critical monitoring metrics:
1. P95 compile time > 5s for 10m
2. 5xx error rate > 1% for 5m
3. Bundle verify error rate > 0.5% for 10m

Example usage:
    >>> from core.metrics import MetricsCollector
    >>> collector = MetricsCollector()
    >>> compile_times = collector.get_compile_times(start_time)
"""

import os
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, NamedTuple
from dataclasses import dataclass
import glob
import re

from core.logging import get_logger

logger = get_logger(__name__)

# Base directory for metrics collection
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
STORAGE_DIR = BASE_DIR / "storage"


@dataclass
class CompileMetric:
    """Compilation time metrics for P95 monitoring."""
    p95_seconds: float
    avg_seconds: float
    count: int
    breached_threshold: bool
    window_minutes: int


@dataclass
class ErrorMetric:
    """5xx error rate metrics."""
    error_rate_percent: float
    error_count: int
    total_requests: int
    breached_threshold: bool
    window_minutes: int


@dataclass
class BundleVerifyMetric:
    """Bundle verification error metrics."""
    error_rate_percent: float
    error_count: int
    total_verifications: int
    breached_threshold: bool
    window_minutes: int


class MetricsCollector:
    """
    Collects operational metrics from ProofKit application logs and storage.
    
    Focuses on the three critical metrics that matter for production monitoring:
    - Compilation performance (P95 times)
    - Error rates (5xx responses)
    - Bundle verification reliability
    """
    
    def __init__(self, log_dir: Path = LOG_DIR, storage_dir: Path = STORAGE_DIR):
        """
        Initialize metrics collector.
        
        Args:
            log_dir: Directory containing application logs
            storage_dir: Directory containing processed files
        """
        self.log_dir = log_dir
        self.storage_dir = storage_dir
        
    def get_compile_times(self, start_time: datetime) -> List[float]:
        """
        Extract compilation times from application logs.
        
        Parses logs to find compilation duration entries and extracts timing data
        for P95 calculation and threshold monitoring.
        
        Args:
            start_time: Start of time window to analyze
            
        Returns:
            List of compilation times in seconds
        """
        compile_times = []
        
        try:
            # Look for log files
            log_files = []
            if self.log_dir.exists():
                log_files.extend(self.log_dir.glob("*.log"))
                log_files.extend(self.log_dir.glob("app*.log"))
            
            # Also check for stdout logs from container
            log_files.extend(Path("/").glob("var/log/app*.log"))
            
            for log_file in log_files:
                if not log_file.exists():
                    continue
                    
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            # Parse JSON log entries
                            if self._is_after_time(line, start_time):
                                duration = self._extract_compile_time(line)
                                if duration is not None:
                                    compile_times.append(duration)
                                    
                except Exception as e:
                    logger.debug(f"Error reading log file {log_file}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error collecting compile times: {e}")
        
        logger.debug(f"Collected {len(compile_times)} compile times since {start_time}")
        return compile_times
    
    def get_request_counts(self, start_time: datetime) -> Tuple[int, int]:
        """
        Get total request count and 5xx error count from logs.
        
        Args:
            start_time: Start of time window to analyze
            
        Returns:
            Tuple of (total_requests, error_5xx_count)
        """
        total_requests = 0
        error_5xx_count = 0
        
        try:
            # Look for log files
            log_files = []
            if self.log_dir.exists():
                log_files.extend(self.log_dir.glob("*.log"))
                log_files.extend(self.log_dir.glob("app*.log"))
            
            for log_file in log_files:
                if not log_file.exists():
                    continue
                    
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if self._is_after_time(line, start_time):
                                request_info = self._extract_request_info(line)
                                if request_info:
                                    total_requests += 1
                                    status_code = request_info.get('status', 0)
                                    if 500 <= status_code <= 599:
                                        error_5xx_count += 1
                                        
                except Exception as e:
                    logger.debug(f"Error reading log file {log_file}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error collecting request counts: {e}")
        
        logger.debug(f"Collected {total_requests} requests, {error_5xx_count} 5xx errors since {start_time}")
        return total_requests, error_5xx_count
    
    def get_bundle_verify_stats(self, start_time: datetime) -> Tuple[int, int]:
        """
        Get bundle verification statistics from logs and storage.
        
        Args:
            start_time: Start of time window to analyze
            
        Returns:
            Tuple of (total_verifications, verification_errors)
        """
        total_verifications = 0
        verification_errors = 0
        
        try:
            # Check application logs for verification events
            log_files = []
            if self.log_dir.exists():
                log_files.extend(self.log_dir.glob("*.log"))
                log_files.extend(self.log_dir.glob("app*.log"))
            
            for log_file in log_files:
                if not log_file.exists():
                    continue
                    
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if self._is_after_time(line, start_time):
                                verify_info = self._extract_verify_info(line)
                                if verify_info:
                                    total_verifications += 1
                                    if verify_info.get('error', False):
                                        verification_errors += 1
                                        
                except Exception as e:
                    logger.debug(f"Error reading log file {log_file}: {e}")
                    continue
            
            # Also check storage directory for verification attempts
            if self.storage_dir.exists():
                cutoff_timestamp = start_time.timestamp()
                
                for item in self.storage_dir.rglob("*.zip"):
                    try:
                        # Check modification time
                        if item.stat().st_mtime < cutoff_timestamp:
                            continue
                        
                        # This represents a bundle creation, which implies verification
                        total_verifications += 1
                        
                        # Check for verification errors in associated logs or metadata
                        # For now, assume successful if bundle exists
                        
                    except Exception as e:
                        logger.debug(f"Error analyzing bundle {item}: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Error collecting bundle verify stats: {e}")
        
        logger.debug(f"Collected {total_verifications} verifications, {verification_errors} errors since {start_time}")
        return total_verifications, verification_errors
    
    def _is_after_time(self, log_line: str, start_time: datetime) -> bool:
        """
        Check if log line timestamp is after given start time.
        
        Args:
            log_line: Log line to check
            start_time: Minimum timestamp
            
        Returns:
            True if log line is after start_time
        """
        try:
            # Try to parse JSON log entry
            if log_line.strip().startswith('{'):
                log_entry = json.loads(log_line.strip())
                if 'time' in log_entry:
                    log_time = datetime.fromisoformat(log_entry['time'].replace('Z', '+00:00'))
                    return log_time >= start_time
            
            # Try to parse standard log format timestamps
            # 2025-08-09T12:34:56.789Z
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)', log_line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str[:-1] + '+00:00'
                log_time = datetime.fromisoformat(timestamp_str)
                return log_time >= start_time
                
        except Exception as e:
            logger.debug(f"Error parsing timestamp from log line: {e}")
            
        return False
    
    def _extract_compile_time(self, log_line: str) -> Optional[float]:
        """
        Extract compilation time from log line.
        
        Args:
            log_line: Log line to analyze
            
        Returns:
            Compilation time in seconds, or None if not found
        """
        try:
            # Look for JSON log entries with duration information
            if log_line.strip().startswith('{'):
                log_entry = json.loads(log_line.strip())
                
                # Check for compilation completion messages
                msg = log_entry.get('msg', '').lower()
                if any(keyword in msg for keyword in ['compilation', 'compile', 'processing completed']):
                    # Look for duration in milliseconds
                    if 'duration_ms' in log_entry:
                        return float(log_entry['duration_ms']) / 1000.0
                    
                    # Look for duration in seconds
                    if 'duration' in log_entry:
                        return float(log_entry['duration'])
            
            # Look for text log entries with timing information
            # "Processing completed in 2.34s"
            time_match = re.search(r'(?:completed|took|finished).*?(\d+\.?\d*)\s*(?:s|sec|seconds)', log_line, re.IGNORECASE)
            if time_match:
                return float(time_match.group(1))
            
            # "duration: 1234ms"
            ms_match = re.search(r'(?:duration|took).*?(\d+)\s*(?:ms|milliseconds)', log_line, re.IGNORECASE)
            if ms_match:
                return float(ms_match.group(1)) / 1000.0
                
        except Exception as e:
            logger.debug(f"Error extracting compile time: {e}")
            
        return None
    
    def _extract_request_info(self, log_line: str) -> Optional[Dict[str, Any]]:
        """
        Extract request information from log line.
        
        Args:
            log_line: Log line to analyze
            
        Returns:
            Dictionary with request info, or None if not found
        """
        try:
            # Look for JSON log entries with request information
            if log_line.strip().startswith('{'):
                log_entry = json.loads(log_line.strip())
                
                # Check for request completion messages
                if 'status' in log_entry and 'method' in log_entry:
                    return {
                        'status': int(log_entry['status']),
                        'method': log_entry['method'],
                        'path': log_entry.get('path', ''),
                        'duration_ms': log_entry.get('duration_ms', 0)
                    }
            
            # Look for standard HTTP access log format
            # "GET /api/compile HTTP/1.1" 200 1234
            access_match = re.search(r'"([A-Z]+)\s+([^"]+)"\s+(\d+)\s+(\d+)', log_line)
            if access_match:
                return {
                    'method': access_match.group(1),
                    'path': access_match.group(2),
                    'status': int(access_match.group(3)),
                    'size': int(access_match.group(4))
                }
                
        except Exception as e:
            logger.debug(f"Error extracting request info: {e}")
            
        return None
    
    def _extract_verify_info(self, log_line: str) -> Optional[Dict[str, Any]]:
        """
        Extract bundle verification information from log line.
        
        Args:
            log_line: Log line to analyze
            
        Returns:
            Dictionary with verification info, or None if not found
        """
        try:
            # Look for JSON log entries with verification information
            if log_line.strip().startswith('{'):
                log_entry = json.loads(log_line.strip())
                
                msg = log_entry.get('msg', '').lower()
                if any(keyword in msg for keyword in ['verify', 'verification', 'bundle check']):
                    return {
                        'error': 'error' in msg or 'fail' in msg,
                        'path': log_entry.get('path', ''),
                        'duration_ms': log_entry.get('duration_ms', 0)
                    }
            
            # Look for verification messages in text logs
            if any(keyword in log_line.lower() for keyword in ['verify', 'verification', 'bundle']):
                error_indicators = ['error', 'fail', 'invalid', 'corrupt']
                has_error = any(indicator in log_line.lower() for indicator in error_indicators)
                
                return {
                    'error': has_error,
                    'path': '',
                    'duration_ms': 0
                }
                
        except Exception as e:
            logger.debug(f"Error extracting verify info: {e}")
            
        return None
    
    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get current health summary of all critical metrics.
        
        Returns:
            Dictionary with health status and metric values
        """
        now = datetime.now(timezone.utc)
        
        # Get metrics for standard windows
        compile_times = self.get_compile_times(now - timedelta(minutes=10))
        total_requests, error_5xx = self.get_request_counts(now - timedelta(minutes=5))
        total_verify, verify_errors = self.get_bundle_verify_stats(now - timedelta(minutes=10))
        
        # Calculate current values
        p95_time = 0.0
        if compile_times:
            sorted_times = sorted(compile_times)
            p95_index = int(0.95 * len(sorted_times))
            p95_time = sorted_times[p95_index] if sorted_times else 0.0
        
        error_rate = (error_5xx / total_requests * 100) if total_requests > 0 else 0.0
        verify_error_rate = (verify_errors / total_verify * 100) if total_verify > 0 else 0.0
        
        # Check thresholds
        compile_healthy = p95_time <= 5.0
        error_healthy = error_rate <= 1.0
        verify_healthy = verify_error_rate <= 0.5
        
        overall_healthy = compile_healthy and error_healthy and verify_healthy
        
        return {
            "timestamp": now.isoformat(),
            "healthy": overall_healthy,
            "metrics": {
                "compile_p95": {
                    "value_seconds": round(p95_time, 2),
                    "threshold_seconds": 5.0,
                    "healthy": compile_healthy,
                    "sample_count": len(compile_times)
                },
                "error_5xx_rate": {
                    "value_percent": round(error_rate, 2),
                    "threshold_percent": 1.0,
                    "healthy": error_healthy,
                    "total_requests": total_requests,
                    "error_count": error_5xx
                },
                "bundle_verify_error_rate": {
                    "value_percent": round(verify_error_rate, 2),
                    "threshold_percent": 0.5,
                    "healthy": verify_healthy,
                    "total_verifications": total_verify,
                    "error_count": verify_errors
                }
            }
        }