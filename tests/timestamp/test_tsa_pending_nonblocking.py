#!/usr/bin/env python3
"""Test TSA resilience and non-blocking behavior."""

import json
import os
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.timestamp import (
    get_timestamp_with_retry, 
    process_retry_queue,
    get_retry_queue_status,
    clear_retry_queue,
    TimestampRetryJob,
    TimestampResult,
    RETRY_QUEUE_DIR
)


@pytest.fixture
def temp_queue_dir():
    """Create temporary queue directory for testing."""
    original_dir = RETRY_QUEUE_DIR
    test_dir = Path(tempfile.mkdtemp()) / "tsa_retry_test"
    
    # Monkey patch the queue directory
    import core.timestamp
    core.timestamp.RETRY_QUEUE_DIR = test_dir
    
    yield test_dir
    
    # Cleanup and restore
    if test_dir.exists():
        shutil.rmtree(test_dir)
    core.timestamp.RETRY_QUEUE_DIR = original_dir


@pytest.fixture
def mock_pdf_content():
    """Mock PDF content for testing."""
    return b"mock PDF content for testing"


@pytest.fixture
def fixed_time():
    """Fixed timestamp for deterministic testing."""
    return datetime(2025, 8, 9, 12, 0, 0, tzinfo=timezone.utc)


def test_tsa_success_case(mock_pdf_content, fixed_time):
    """Test successful TSA timestamp generation."""
    with patch('core.timestamp._generate_rfc3161_timestamp') as mock_tsa:
        # Mock successful timestamp
        mock_token = b'mock_timestamp_token_12345'
        mock_tsa.return_value = mock_token
        
        result = get_timestamp_with_retry(
            pdf_content=mock_pdf_content,
            job_id="test_success",
            pdf_path="/tmp/test.pdf",
            now_provider=lambda: fixed_time
        )
        
        assert result.success is True
        assert result.pending is False
        assert result.timestamp == mock_token
        assert result.timestamp_info['tsa_status'] == 'success'
        assert result.timestamp_info['timestamp'] == fixed_time.isoformat()
        assert 'token' in result.timestamp_info
        assert result.errors == []


def test_tsa_failure_with_retry_queue(temp_queue_dir, mock_pdf_content, fixed_time):
    """Test TSA failure triggers retry queue."""
    with patch('core.timestamp._generate_rfc3161_timestamp') as mock_tsa:
        # Mock TSA failure
        mock_tsa.return_value = None
        
        result = get_timestamp_with_retry(
            pdf_content=mock_pdf_content,
            job_id="test_retry",
            pdf_path="/tmp/test.pdf",
            now_provider=lambda: fixed_time
        )
        
        assert result.success is False
        assert result.pending is True
        assert result.timestamp is None
        assert result.timestamp_info['tsa_status'] == 'pending'
        assert result.timestamp_info['retry_queued'] is True
        assert 'TSA unavailable' in result.errors[0]
        
        # Check retry job was queued
        job_files = list(temp_queue_dir.glob("*.json"))
        assert len(job_files) == 1
        
        # Verify job content
        with open(job_files[0], 'r') as f:
            job_data = json.load(f)
        
        assert job_data['job_id'] == "test_retry"
        assert job_data['pdf_path'] == "/tmp/test.pdf"
        assert job_data['attempts'] == 0
        assert job_data['created_at'] == fixed_time.isoformat()


def test_tsa_failure_without_pdf_path(mock_pdf_content, fixed_time):
    """Test TSA failure without PDF path doesn't queue retry."""
    with patch('core.timestamp._generate_rfc3161_timestamp') as mock_tsa:
        # Mock TSA failure
        mock_tsa.return_value = None
        
        result = get_timestamp_with_retry(
            pdf_content=mock_pdf_content,
            job_id="test_no_queue",
            pdf_path=None,  # No PDF path provided
            now_provider=lambda: fixed_time
        )
        
        assert result.success is False
        assert result.pending is True
        assert result.timestamp_info['retry_queued'] is False


def test_retry_queue_processing_success(temp_queue_dir, fixed_time):
    """Test successful retry queue processing."""
    # Create a test PDF file
    pdf_path = temp_queue_dir / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_content = b"test PDF content"
    pdf_path.write_bytes(pdf_content)
    
    # Create retry job
    retry_job = TimestampRetryJob(
        job_id="retry_success",
        pdf_path=str(pdf_path),
        pdf_hash="abc123",  # Will be recalculated
        created_at=fixed_time,
        attempts=0
    )
    
    job_file = temp_queue_dir / "retry_success.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    
    job_data = {
        'job_id': retry_job.job_id,
        'pdf_path': retry_job.pdf_path,
        'pdf_hash': retry_job.pdf_hash,
        'created_at': retry_job.created_at.isoformat(),
        'attempts': retry_job.attempts,
        'last_attempt_at': None,
        'tsa_errors': []
    }
    
    with open(job_file, 'w') as f:
        json.dump(job_data, f)
    
    # Mock successful TSA on retry
    with patch('core.timestamp._generate_rfc3161_timestamp') as mock_tsa:
        mock_tsa.return_value = b'retry_success_token'
        
        stats = process_retry_queue(now_provider=lambda: fixed_time)
        
        assert stats['jobs_processed'] == 1
        assert stats['jobs_succeeded'] == 1
        assert stats['jobs_failed'] == 0
        assert stats['jobs_expired'] == 0
        
        # Job should be removed from queue
        assert not job_file.exists()


def test_retry_queue_processing_max_attempts(temp_queue_dir, fixed_time):
    """Test retry job reaches max attempts."""
    # Create retry job with max attempts
    job_file = temp_queue_dir / "max_attempts.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    
    job_data = {
        'job_id': "max_attempts",
        'pdf_path': "/tmp/nonexistent.pdf",
        'pdf_hash': "abc123",
        'created_at': fixed_time.isoformat(),
        'attempts': 3,  # At max attempts
        'last_attempt_at': None,
        'tsa_errors': []
    }
    
    with open(job_file, 'w') as f:
        json.dump(job_data, f)
    
    stats = process_retry_queue(now_provider=lambda: fixed_time)
    
    assert stats['jobs_processed'] == 1
    assert stats['jobs_failed'] == 1
    assert stats['jobs_succeeded'] == 0
    
    # Job should be removed from queue
    assert not job_file.exists()


def test_retry_queue_processing_expired_jobs(temp_queue_dir, fixed_time):
    """Test expired retry jobs are removed."""
    # Create expired retry job (25 hours old)
    expired_time = fixed_time - timedelta(hours=25)
    job_file = temp_queue_dir / "expired.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    
    job_data = {
        'job_id': "expired",
        'pdf_path': "/tmp/expired.pdf",
        'pdf_hash': "abc123",
        'created_at': expired_time.isoformat(),
        'attempts': 1,
        'last_attempt_at': None,
        'tsa_errors': []
    }
    
    with open(job_file, 'w') as f:
        json.dump(job_data, f)
    
    stats = process_retry_queue(now_provider=lambda: fixed_time)
    
    assert stats['jobs_processed'] == 1
    assert stats['jobs_expired'] == 1
    assert stats['jobs_succeeded'] == 0
    
    # Job should be removed from queue
    assert not job_file.exists()


def test_retry_queue_processing_deferred_jobs(temp_queue_dir, fixed_time):
    """Test jobs are deferred when retry delay hasn't passed."""
    # Create job with recent attempt (2 minutes ago, delay is 5 minutes)
    recent_attempt = fixed_time - timedelta(minutes=2)
    job_file = temp_queue_dir / "deferred.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    
    job_data = {
        'job_id': "deferred",
        'pdf_path': "/tmp/deferred.pdf", 
        'pdf_hash': "abc123",
        'created_at': fixed_time.isoformat(),
        'attempts': 1,
        'last_attempt_at': recent_attempt.isoformat(),
        'tsa_errors': []
    }
    
    with open(job_file, 'w') as f:
        json.dump(job_data, f)
    
    stats = process_retry_queue(now_provider=lambda: fixed_time)
    
    assert stats['jobs_processed'] == 1
    assert stats['jobs_deferred'] == 1
    assert stats['jobs_succeeded'] == 0
    
    # Job should still exist
    assert job_file.exists()


def test_retry_queue_status(temp_queue_dir, fixed_time):
    """Test retry queue status reporting."""
    # Ensure queue directory exists
    temp_queue_dir.mkdir(parents=True, exist_ok=True)
    
    # Empty queue
    status = get_retry_queue_status()
    assert status['queue_size'] == 0
    assert status['queue_directory_exists'] is True
    
    # Add some jobs
    for i in range(3):
        job_file = temp_queue_dir / f"job_{i}.json"
        job_file.parent.mkdir(parents=True, exist_ok=True)
        
        job_data = {
            'job_id': f"job_{i}",
            'pdf_path': f"/tmp/job_{i}.pdf",
            'pdf_hash': "abc123",
            'created_at': (fixed_time - timedelta(minutes=i)).isoformat(),
            'attempts': 0,
            'last_attempt_at': None,
            'tsa_errors': []
        }
        
        with open(job_file, 'w') as f:
            json.dump(job_data, f)
    
    status = get_retry_queue_status()
    assert status['queue_size'] == 3
    assert status['oldest_job'] is not None
    assert status['newest_job'] is not None


def test_clear_retry_queue(temp_queue_dir):
    """Test clearing retry queue."""
    # Add some jobs
    for i in range(2):
        job_file = temp_queue_dir / f"clear_{i}.json"
        job_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(job_file, 'w') as f:
            json.dump({'job_id': f'clear_{i}'}, f)
    
    cleared_count = clear_retry_queue()
    assert cleared_count == 2
    
    # Queue should be empty
    status = get_retry_queue_status()
    assert status['queue_size'] == 0


def test_pdf_validation_non_blocking(mock_pdf_content, fixed_time):
    """Test that PDF generation doesn't block when TSA unavailable."""
    with patch('core.timestamp._generate_rfc3161_timestamp') as mock_tsa:
        # Mock TSA failure
        mock_tsa.return_value = None
        
        # This should not raise an exception or block
        result = get_timestamp_with_retry(
            pdf_content=mock_pdf_content,
            job_id="non_blocking_test",
            pdf_path="/tmp/non_blocking.pdf",
            now_provider=lambda: fixed_time
        )
        
        # Should get a pending result, not failure
        assert result.pending is True
        assert result.success is False
        assert 'pending' in result.timestamp_info['tsa_status']
        assert len(result.errors) == 1
        assert 'TSA unavailable' in result.errors[0]


def test_tsa_dependencies_unavailable(mock_pdf_content, fixed_time):
    """Test graceful handling when TSA dependencies unavailable."""
    with patch('core.timestamp.TSA_AVAILABLE', False):
        result = get_timestamp_with_retry(
            pdf_content=mock_pdf_content,
            job_id="no_deps",
            pdf_path="/tmp/no_deps.pdf",
            now_provider=lambda: fixed_time
        )
        
        assert result.success is False
        assert result.pending is True
        assert result.timestamp_info['tsa_status'] == 'pending'


if __name__ == "__main__":
    # Run basic tests
    pytest.main([__file__, "-v"])