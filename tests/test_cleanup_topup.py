"""
Top-up tests for cleanup module to achieve ≥90% coverage.

These tests target specific missing lines and edge cases to increase coverage
beyond the existing test_cleanup.py baseline.

Example usage:
    pytest tests/test_cleanup_topup.py -v --cov=core.cleanup
"""

import pytest
import os
import shutil
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.cleanup import (
    is_path_safe,
    calculate_directory_size,
    find_expired_artifacts,
    cleanup_background_task,
    schedule_cleanup,
    stop_cleanup
)


class TestMissingCoverageLines:
    """Test specific lines that are missing coverage to reach ≥90%."""
    
    def test_is_path_safe_resolution_error_handling(self, tmp_path):
        """Test is_path_safe when path resolution raises OSError/ValueError - lines 78-80."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        
        # Mock Path.resolve to raise ValueError on test_path
        original_resolve = Path.resolve
        def mock_resolve(path_self):
            if "test_bad_path" in str(path_self):
                raise ValueError("Invalid path resolution")
            return original_resolve(path_self)
        
        with patch.object(Path, 'resolve', mock_resolve):
            bad_path = base_dir / "test_bad_path"
            result = is_path_safe(bad_path, base_dir)
            
            # Should return False when resolution fails
            assert result is False
        
        # Test with OSError as well
        def mock_resolve_os_error(path_self):
            if "test_os_error_path" in str(path_self):
                raise OSError("OS level error")
            return original_resolve(path_self)
        
        with patch.object(Path, 'resolve', mock_resolve_os_error):
            bad_path = base_dir / "test_os_error_path"
            result = is_path_safe(bad_path, base_dir)
            
            # Should return False when resolution fails
            assert result is False
    
    def test_calculate_directory_size_file_access_error(self, tmp_path):
        """Test calculate_directory_size when individual file access fails - lines 107-109.""" 
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        
        # Create a regular file
        regular_file = test_dir / "regular.txt"
        regular_file.write_text("content")
        
        # Mock Path.stat to raise PermissionError for specific file
        original_stat = Path.stat
        def mock_stat(path_self):
            if "regular.txt" in str(path_self):
                raise PermissionError("Access denied to file")
            return original_stat(path_self)
        
        with patch.object(Path, 'stat', mock_stat):
            with patch('core.cleanup.logger') as mock_logger:
                size = calculate_directory_size(test_dir)
                
                # Should continue processing and log warning
                assert size == 0  # File couldn't be measured
                mock_logger.warning.assert_called_once()
                warning_call = mock_logger.warning.call_args_list[0]
                assert "Cannot access file" in str(warning_call)
    
    def test_find_expired_artifacts_job_directory_not_directory(self, tmp_path):
        """Test find_expired_artifacts when job item is not a directory - line 157."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create valid hash directory
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        
        # Create a file instead of job directory (should be skipped)
        not_a_dir = hash_dir / "not_a_directory.txt"
        not_a_dir.write_text("this is a file, not a directory")
        
        # Create a valid job directory as well
        valid_job = hash_dir / "valid_job"
        valid_job.mkdir()
        
        # Set old creation time for valid job
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(valid_job, (old_time, old_time))
        
        expired = find_expired_artifacts(storage_dir, retention_days=30)
        
        # Should only find the valid job directory, skip the file
        assert len(expired) == 1
        assert expired[0][0] == valid_job
    
    def test_find_expired_artifacts_stat_permission_error(self, tmp_path):
        """Test find_expired_artifacts when job directory stat fails - lines 172-174."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "problem_job"
        job_dir.mkdir()
        
        # Mock Path.stat to raise PermissionError
        original_stat = Path.stat
        def mock_stat(path_self):
            if "problem_job" in str(path_self):
                raise PermissionError("Cannot stat job directory")
            return original_stat(path_self)
        
        with patch.object(Path, 'stat', mock_stat):
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should handle gracefully and continue processing
                assert expired == []
                mock_logger.warning.assert_called_once()
                warning_call = mock_logger.warning.call_args_list[0]
                assert "Cannot access job directory" in str(warning_call)
    
    def test_cleanup_background_task_exception_handling(self, tmp_path):
        """Test cleanup_background_task exception handling - lines 376-377."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        stop_event = threading.Event()
        stop_event.set()  # Stop immediately after first iteration
        
        # Mock cleanup_old_artifacts to raise exception
        def mock_cleanup(*args, **kwargs):
            raise RuntimeError("Simulated cleanup failure")
        
        with patch('core.cleanup.cleanup_old_artifacts', side_effect=mock_cleanup):
            with patch('core.cleanup.logger') as mock_logger:
                cleanup_background_task(
                    storage_dir=storage_dir,
                    retention_days=30,
                    interval_hours=1,
                    stop_event=stop_event
                )
        
        # Should log the error
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args_list[0]
        assert "Background cleanup failed" in str(error_call)
    
    def test_cleanup_background_task_timeout_and_break(self, tmp_path):
        """Test cleanup_background_task wait timeout and break logic - line 385."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        stop_event = threading.Event()
        
        # Mock cleanup to succeed  
        def mock_cleanup(*args, **kwargs):
            return {'removed': 0, 'failed': 0}
        
        # Control the wait behavior
        wait_call_count = 0
        original_wait = threading.Event.wait
        def mock_wait(self, timeout=None):
            nonlocal wait_call_count
            wait_call_count += 1
            if wait_call_count == 1:
                # First wait returns False (timeout, continue loop)
                return False
            else:
                # Second wait returns True (stop event set, break loop)
                return True
        
        with patch('core.cleanup.cleanup_old_artifacts', side_effect=mock_cleanup):
            with patch.object(threading.Event, 'wait', mock_wait):
                with patch('core.cleanup.logger') as mock_logger:
                    cleanup_background_task(
                        storage_dir=storage_dir,
                        retention_days=30,
                        interval_hours=1,
                        stop_event=stop_event
                    )
        
        # Should execute cleanup at least once and then break on stop event
        assert wait_call_count >= 2
        
        # Should log start and stop
        start_calls = [call for call in mock_logger.info.call_args_list 
                      if "Background cleanup task started" in str(call)]
        stop_calls = [call for call in mock_logger.info.call_args_list 
                     if "Background cleanup task stopped" in str(call)]
        
        assert len(start_calls) == 1
        assert len(stop_calls) == 1
    
    def test_schedule_cleanup_already_running_warning(self, tmp_path):
        """Test schedule_cleanup when task is already running - lines 416-417."""
        # Mock a running task
        mock_task = MagicMock()
        mock_task.is_alive.return_value = True
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup.logger') as mock_logger:
                result = schedule_cleanup()
                
                assert result is False
                mock_logger.warning.assert_called_once_with(
                    "Background cleanup task already running"
                )
    
    def test_schedule_cleanup_get_retention_days_default(self, tmp_path):
        """Test schedule_cleanup using get_retention_days() for default - line 424."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        with patch('core.cleanup._cleanup_task', None):
            with patch.dict(os.environ, {'RETENTION_DAYS': '15'}):
                with patch('core.cleanup.logger') as mock_logger:
                    # Don't specify retention_days, should use get_retention_days()
                    result = schedule_cleanup(storage_dir=storage_dir)
        
        assert result is True
        
        # Should log with the value from environment
        log_calls = [call for call in mock_logger.info.call_args_list 
                    if "Background cleanup task scheduled" in str(call)]
        
        assert len(log_calls) == 1
        # Check that retention_days=15 is in the logged extra data
        call_extra = log_calls[0][1].get('extra', {})
        assert call_extra.get('retention_days') == 15
    
    def test_stop_cleanup_task_not_alive(self):
        """Test stop_cleanup when task exists but is not alive - line 421."""
        # Mock a dead task
        mock_task = MagicMock()
        mock_task.is_alive.return_value = False
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup.logger') as mock_logger:
                result = stop_cleanup()
                
                assert result is False
                mock_logger.info.assert_called_once_with(
                    "Background cleanup task not running"
                )
    
    def test_stop_cleanup_task_timeout_warning(self):
        """Test stop_cleanup when task doesn't stop within timeout - lines 480-481."""
        # Mock a task that doesn't stop within timeout
        mock_task = MagicMock()
        mock_task.is_alive.side_effect = [True, True]  # Alive before and after join
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup._cleanup_stop_event') as mock_event:
                with patch('core.cleanup.logger') as mock_logger:
                    result = stop_cleanup()
                    
                    assert result is False
                    mock_event.set.assert_called_once()
                    mock_task.join.assert_called_once_with(timeout=10.0)
                    mock_logger.warning.assert_called_once_with(
                        "Background cleanup task did not stop within timeout"
                    )


class TestZeroDayRetentionEdgeCase:
    """Test 0-day retention which should delete everything older than today."""
    
    def test_zero_day_retention_deletes_old_files(self, tmp_path):
        """Test that 0-day retention deletes files older than current day."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create hash directory
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        
        # Create an old job directory
        old_job = hash_dir / "old_job"
        old_job.mkdir()
        (old_job / "file.txt").write_text("content")
        
        # Set creation time to yesterday
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        timestamp = yesterday.timestamp()
        os.utime(old_job, (timestamp, timestamp))
        
        # Use now_provider for consistent testing
        def now_provider():
            return datetime.now(timezone.utc)
        
        # Run cleanup with 0-day retention
        from core.cleanup import cleanup_old_artifacts
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=0,
            now_provider=now_provider
        )
        
        # Should find and remove the old job
        assert stats['expired'] == 1
        assert stats['removed'] == 1
        assert not old_job.exists()


class TestHiddenFilesHandling:
    """Test that hidden files and nested directories are handled correctly."""
    
    def test_hidden_files_removed_with_directory(self, tmp_path):
        """Test that hidden files are removed along with their parent directory."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "job_with_hidden"
        job_dir.mkdir()
        
        # Create regular and hidden files
        (job_dir / "regular.txt").write_text("regular")
        (job_dir / ".hidden_file").write_text("hidden")
        
        # Create hidden subdirectory
        hidden_dir = job_dir / ".hidden_dir"  
        hidden_dir.mkdir()
        (hidden_dir / "nested.txt").write_text("nested in hidden")
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        # Run cleanup
        from core.cleanup import cleanup_old_artifacts
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        # Should successfully remove entire structure including hidden files
        assert stats['removed'] == 1
        assert not job_dir.exists()
        assert not hidden_dir.exists()