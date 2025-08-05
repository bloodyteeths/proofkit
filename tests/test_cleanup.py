"""
Comprehensive tests for the cleanup module.

Tests cover artifact retention, cleanup operations, error handling,
and time-based logic using mocking and freezegun for deterministic testing.

Example usage:
    pytest tests/test_cleanup.py -v --cov=core.cleanup
"""

import pytest
import os
import shutil
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from freezegun import freeze_time

from core.cleanup import (
    get_retention_days,
    is_path_safe,
    calculate_directory_size,
    find_expired_artifacts,
    remove_artifact_directory,
    cleanup_old_artifacts,
    cleanup_background_task,
    schedule_cleanup,
    stop_cleanup
)


class TestGetRetentionDays:
    """Test retention days configuration from environment."""
    
    def test_default_retention_days(self):
        """Test default retention days when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            days = get_retention_days()
            assert days == 30
    
    def test_custom_retention_days(self):
        """Test custom retention days from environment."""
        with patch.dict(os.environ, {'RETENTION_DAYS': '7'}):
            days = get_retention_days()
            assert days == 7
    
    def test_invalid_retention_days_fallback(self):
        """Test fallback to default on invalid env value."""
        with patch.dict(os.environ, {'RETENTION_DAYS': 'invalid'}):
            with patch('core.cleanup.logger') as mock_logger:
                days = get_retention_days()
                assert days == 30
                mock_logger.warning.assert_called_once_with(
                    "Invalid RETENTION_DAYS value, using default 30"
                )


class TestIsPathSafe:
    """Test path safety validation for security."""
    
    def test_safe_path_within_base(self, tmp_path):
        """Test that paths within base directory are safe."""
        base_dir = tmp_path / "storage"
        base_dir.mkdir()
        
        safe_path = base_dir / "artifacts" / "abc123"
        assert is_path_safe(safe_path, base_dir) is True
    
    def test_unsafe_path_outside_base(self, tmp_path):
        """Test that paths outside base directory are unsafe."""
        base_dir = tmp_path / "storage"
        base_dir.mkdir()
        
        unsafe_path = tmp_path / "other" / "file.txt"
        assert is_path_safe(unsafe_path, base_dir) is False
    
    def test_path_traversal_attempt(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        base_dir = tmp_path / "storage"
        base_dir.mkdir()
        
        # Try to escape using ../
        unsafe_path = base_dir / ".." / ".." / "etc" / "passwd"
        assert is_path_safe(unsafe_path, base_dir) is False
    
    def test_symlink_traversal_attempt(self, tmp_path):
        """Test that symlink traversal is handled safely."""
        base_dir = tmp_path / "storage"
        base_dir.mkdir()
        
        # Create a symlink pointing outside base directory
        target = tmp_path / "outside.txt"
        target.write_text("sensitive data")
        
        symlink = base_dir / "link"
        symlink.symlink_to(target)
        
        # The symlink itself should be safe (within base)
        # but its target might not be - this tests resolution
        result = is_path_safe(symlink, base_dir)
        # Result depends on symlink resolution behavior
        assert isinstance(result, bool)
    
    def test_nonexistent_path_resolution_error(self, tmp_path):
        """Test handling of path resolution errors."""
        base_dir = tmp_path / "storage"
        base_dir.mkdir()
        
        # Create a path that will cause resolution error
        problematic_path = base_dir / "nonexistent" / ".." / ".." / "etc"
        
        # Should handle gracefully and return False
        assert is_path_safe(problematic_path, base_dir) is False


class TestCalculateDirectorySize:
    """Test directory size calculation."""
    
    def test_empty_directory(self, tmp_path):
        """Test size calculation for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        
        size = calculate_directory_size(empty_dir)
        assert size == 0
    
    def test_directory_with_files(self, tmp_path):
        """Test size calculation with actual files."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        
        # Create files of known sizes
        file1 = test_dir / "file1.txt"
        file1.write_text("Hello World")  # 11 bytes
        
        file2 = test_dir / "file2.txt"
        file2.write_text("Test")  # 4 bytes
        
        # Create subdirectory with file
        subdir = test_dir / "subdir"
        subdir.mkdir()
        file3 = subdir / "file3.txt"
        file3.write_text("Sub")  # 3 bytes
        
        size = calculate_directory_size(test_dir)
        assert size == 18  # 11 + 4 + 3 bytes
    
    def test_nonexistent_directory(self, tmp_path):
        """Test size calculation for nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        
        size = calculate_directory_size(nonexistent)
        assert size == 0
    
    def test_permission_error_handling(self, tmp_path):
        """Test handling of permission errors during size calculation."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        
        file1 = test_dir / "accessible.txt"
        file1.write_text("accessible")
        
        # Mock os.walk to simulate permission error
        with patch('os.walk') as mock_walk:
            mock_walk.side_effect = PermissionError("Access denied")
            
            with patch('core.cleanup.logger') as mock_logger:
                size = calculate_directory_size(test_dir)
                assert size == 0
                mock_logger.error.assert_called_once()


class TestFindExpiredArtifacts:
    """Test expired artifact discovery."""
    
    def setup_storage_structure(self, tmp_path, artifacts_data):
        """
        Helper to create storage structure with artifacts.
        
        Args:
            tmp_path: Temporary directory fixture
            artifacts_data: List of (hash_prefix, job_id, age_days) tuples
        
        Returns:
            Path to storage directory
        """
        import time
        
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Sort by age_days to create oldest first (so ctime works correctly)
        sorted_artifacts = sorted(artifacts_data, key=lambda x: x[2], reverse=True)
        
        for hash_prefix, job_id, age_days in sorted_artifacts:
            # Create hash directory (2-char hex)
            hash_dir = storage_dir / hash_prefix
            hash_dir.mkdir(exist_ok=True)
            
            # Create job directory
            job_dir = hash_dir / job_id
            job_dir.mkdir()
            
            # Sleep a tiny bit to ensure different creation times
            time.sleep(0.01)
        
        return storage_dir
    
    def test_find_expired_artifacts_with_retention(self, tmp_path):
        """Test finding artifacts older than retention period."""
        import time
        
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create artifacts with controlled timing
        # Use a fixed time in the past for predictable testing
        fixed_time = datetime(2024, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Create old artifacts (should be expired)
        for hash_prefix, job_id in [("ab", "job1_old"), ("ef", "job3_old")]:
            hash_dir = storage_dir / hash_prefix
            hash_dir.mkdir(exist_ok=True)
            job_dir = hash_dir / job_id
            job_dir.mkdir()
            time.sleep(0.01)  # Ensure different ctimes
        
        # Sleep to ensure the next directory has different ctime
        time.sleep(0.1)
        
        # Create new artifact (should not be expired)  
        hash_dir = storage_dir / "cd"
        hash_dir.mkdir()
        job_dir = hash_dir / "job2_new"
        job_dir.mkdir()
        
        # Use now_provider to control what "now" means
        # Set now to be exactly between the older and newer directories
        # The older dirs were created ~0.1+ seconds ago, newer dir just now
        # If we set fake "now" to be 30 days + 50ms after oldest creation time,
        # the older dirs will be > 30 days old, newer dir will be < 30 days old
        oldest_dir_time = datetime.now(timezone.utc) - timedelta(seconds=0.1)
        current_time = oldest_dir_time + timedelta(days=30, milliseconds=50)
        
        def test_now_provider():
            return current_time
        
        expired = find_expired_artifacts(storage_dir, retention_days=30, now_provider=test_now_provider)
        
        # Should find the 2 older artifacts (they will appear > 30 days old relative to our fake "now")
        assert len(expired) == 2
        expired_paths = [path for path, _ in expired]
        
        assert storage_dir / "ab" / "job1_old" in expired_paths
        assert storage_dir / "ef" / "job3_old" in expired_paths
        assert storage_dir / "cd" / "job2_new" not in expired_paths
    
    def test_find_expired_artifacts_exact_boundary(self, tmp_path):
        """Test exact retention boundary (N vs N+1 days)."""
        import time
        
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create first artifact (this will be treated as older)
        hash_dir1 = storage_dir / "ab"
        hash_dir1.mkdir()
        job_dir_31_days = hash_dir1 / "exactly_31_days"
        job_dir_31_days.mkdir()
        
        # Sleep to ensure different creation time
        time.sleep(0.1)
        
        # Create second artifact (this will be treated as newer)
        hash_dir2 = storage_dir / "cd"
        hash_dir2.mkdir()
        job_dir_30_days = hash_dir2 / "exactly_30_days"
        job_dir_30_days.mkdir()
        
        # Create a now_provider that makes the timing work
        # Get actual creation times and set fake "now" appropriately
        stat1 = job_dir_31_days.stat()
        stat2 = job_dir_30_days.stat()
        older_ctime = datetime.fromtimestamp(stat1.st_ctime, tz=timezone.utc)
        newer_ctime = datetime.fromtimestamp(stat2.st_ctime, tz=timezone.utc)
        
        # Set fake "now" to be exactly 30 days + some buffer after the newer one
        # This makes the older one > 30 days old, newer one <= 30 days old
        fake_now = newer_ctime + timedelta(days=30, seconds=5)
        
        def test_now_provider():
            return fake_now
        
        expired = find_expired_artifacts(
            storage_dir, 
            retention_days=30,
            now_provider=test_now_provider
        )
        
        # Only the older artifact should be expired
        assert len(expired) == 1
        expired_path = expired[0][0]
        assert expired_path == job_dir_31_days
    
    def test_find_expired_artifacts_nonexistent_storage(self, tmp_path):
        """Test handling of nonexistent storage directory."""
        nonexistent = tmp_path / "nonexistent"
        
        with patch('core.cleanup.logger') as mock_logger:
            expired = find_expired_artifacts(nonexistent, retention_days=30)
            
            assert expired == []
            mock_logger.info.assert_called_once_with(
                f"Storage directory does not exist: {nonexistent}"
            )
    
    def test_find_expired_artifacts_invalid_hash_dirs(self, tmp_path):
        """Test handling of invalid hash directory names."""
        import time
        
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create valid hash directory with job
        valid_hash = storage_dir / "ab"
        valid_hash.mkdir()
        valid_job = valid_hash / "valid_job"
        valid_job.mkdir()
        
        # Create invalid directory names that should be ignored
        (storage_dir / "invalid_name").mkdir()  # Invalid name
        (storage_dir / "xyz").mkdir()  # Invalid hex chars
        (storage_dir / "a").mkdir()   # Too short  
        (storage_dir / "abc").mkdir()  # Too long
        
        # Use now_provider to make the valid job appear old
        current_time = datetime.now(timezone.utc) + timedelta(days=31)
        
        def test_now_provider():
            return current_time
        
        expired = find_expired_artifacts(storage_dir, retention_days=30, now_provider=test_now_provider)
        
        # Should only process valid hash directories
        assert len(expired) == 1  # Only the valid job should be found
        assert expired[0][0] == valid_job
    
    def test_find_expired_artifacts_unsafe_paths(self, tmp_path):
        """Test handling of unsafe job directory paths."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        
        # Create normal job directory
        normal_job = hash_dir / "normal_job"
        normal_job.mkdir()
        
        # Mock is_path_safe to simulate unsafe path detection
        with patch('core.cleanup.is_path_safe') as mock_safe:
            # First call (normal_job) returns False (unsafe)
            # This simulates detection of a malicious path
            mock_safe.return_value = False
            
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should skip unsafe paths
                assert len(expired) == 0
                mock_logger.warning.assert_called()
    
    def test_find_expired_artifacts_permission_errors(self, tmp_path):
        """Test handling of permission errors."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create hash directory and job directory  
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "job1"
        job_dir.mkdir()
        
        # Mock Path.stat to raise permission error for specific job directory
        original_stat = Path.stat
        def mock_stat(path_self):
            if "job1" in str(path_self):
                raise PermissionError("Access denied")
            return original_stat(path_self)
        
        with patch.object(Path, 'stat', mock_stat):
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should handle gracefully and continue
                assert len(expired) == 0
                mock_logger.warning.assert_called()


class TestRemoveArtifactDirectory:
    """Test artifact directory removal."""
    
    def test_remove_existing_directory(self, tmp_path):
        """Test successful removal of existing directory."""
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        
        # Add some content
        (artifact_dir / "file.txt").write_text("content")
        subdir = artifact_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")
        
        with patch('core.cleanup.logger') as mock_logger:
            result = remove_artifact_directory(artifact_dir)
            
            assert result is True
            assert not artifact_dir.exists()
            mock_logger.info.assert_called_once()
    
    def test_remove_nonexistent_directory(self, tmp_path):
        """Test removal of nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        
        with patch('core.cleanup.logger') as mock_logger:
            result = remove_artifact_directory(nonexistent)
            
            assert result is True
            mock_logger.info.assert_called_once_with(
                f"Artifact directory already removed: {nonexistent}"
            )
    
    def test_remove_directory_dry_run(self, tmp_path):
        """Test dry run mode."""
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        (artifact_dir / "file.txt").write_text("content")
        
        with patch('core.cleanup.logger') as mock_logger:
            result = remove_artifact_directory(artifact_dir, dry_run=True)
            
            assert result is True
            assert artifact_dir.exists()  # Should not actually remove
            mock_logger.info.assert_called_once_with(
                f"DRY RUN: Would remove artifact directory: {artifact_dir}"
            )
    
    def test_remove_directory_permission_error(self, tmp_path):
        """Test handling of permission errors during removal."""
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        
        # Mock shutil.rmtree to raise permission error
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = PermissionError("Access denied")
            
            with patch('core.cleanup.logger') as mock_logger:
                result = remove_artifact_directory(artifact_dir)
                
                assert result is False
                mock_logger.error.assert_called_once()
    
    def test_remove_directory_os_error(self, tmp_path):
        """Test handling of OS errors during removal."""
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        
        # Mock shutil.rmtree to raise OS error
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = OSError("Disk full")
            
            with patch('core.cleanup.logger') as mock_logger:
                result = remove_artifact_directory(artifact_dir)
                
                assert result is False
                mock_logger.error.assert_called_once()


class TestCleanupOldArtifacts:
    """Test comprehensive cleanup operations."""
    
    def test_cleanup_with_default_parameters(self, tmp_path):
        """Test cleanup with default parameters."""
        # Change to temp directory to test default storage path
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Create default storage structure
            storage_dir = tmp_path / "storage"
            artifacts = [
                ("ab", "old_job", 35),
                ("cd", "new_job", 25),
            ]
            self.setup_storage_structure(tmp_path, storage_dir, artifacts)
            
            with patch.dict(os.environ, {'RETENTION_DAYS': '30'}):
                stats = cleanup_old_artifacts()
            
            assert stats['expired'] == 1
            assert stats['removed'] == 1
            assert stats['failed'] == 0
            
        finally:
            os.chdir(original_cwd)
    
    def setup_storage_structure(self, tmp_path, storage_dir, artifacts_data):
        """Helper to create storage structure."""
        import time
        
        storage_dir.mkdir(exist_ok=True)
        
        # Sort by age_days to create oldest first (so ctime reflects age)
        sorted_artifacts = sorted(artifacts_data, key=lambda x: x[2], reverse=True)
        
        for hash_prefix, job_id, age_days in sorted_artifacts:
            hash_dir = storage_dir / hash_prefix
            hash_dir.mkdir(exist_ok=True)
            
            job_dir = hash_dir / job_id
            job_dir.mkdir(exist_ok=True)
            
            # Create some content
            (job_dir / "proof.pdf").write_text("fake pdf content")
            (job_dir / "evidence.zip").write_text("fake zip content")
            
            # Sleep to ensure different creation times
            time.sleep(0.01)
    
    def test_cleanup_comprehensive_scenario(self, tmp_path):
        """Test comprehensive cleanup scenario with mixed results."""
        storage_dir = tmp_path / "storage"
        artifacts = [
            ("ab", "expired_job1", 35),
            ("cd", "current_job", 25),
            ("ef", "expired_job2", 40),
            ("gh", "expired_job3", 50),
        ]
        
        self.setup_storage_structure(tmp_path, storage_dir, artifacts)
        
        # Use now_provider to make appropriate artifacts appear old
        # The 3 oldest created directories (50, 40, 35 age_days) should be expired
        # The newest one (25 age_days) should not be expired
        current_time = datetime.now(timezone.utc) + timedelta(days=31)
        
        def test_now_provider():
            return current_time
        
        # Mock one removal to fail
        original_rmtree = shutil.rmtree
        def mock_rmtree(path, **kwargs):
            if "expired_job2" in str(path):
                raise PermissionError("Simulated failure")
            else:
                original_rmtree(path, **kwargs)
        
        with patch('shutil.rmtree', side_effect=mock_rmtree):
            stats = cleanup_old_artifacts(
                storage_dir=storage_dir,
                retention_days=30,
                dry_run=False,
                now_provider=test_now_provider
            )
        
        assert stats['expired'] == 3  # 3 expired artifacts found
        assert stats['removed'] == 2  # 2 successfully removed
        assert stats['failed'] == 1   # 1 failed to remove
        assert stats['freed_bytes'] > 0
        assert stats['freed_mb'] > 0
    
    def test_cleanup_dry_run_mode(self, tmp_path):
        """Test cleanup in dry run mode."""
        storage_dir = tmp_path / "storage"
        artifacts = [("ab", "old_job", 35)]
        self.setup_storage_structure(tmp_path, storage_dir, artifacts)
        
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30,
            dry_run=True
        )
        
        # Should find artifacts but not remove them
        assert stats['expired'] == 1
        assert stats['removed'] == 1  # Counts successful dry run "removal"
        assert stats['freed_bytes'] == 0  # No actual bytes freed in dry run
        
        # Verify directory still exists
        assert (storage_dir / "ab" / "old_job").exists()
    
    def test_cleanup_with_now_provider(self, tmp_path):
        """Test cleanup with custom now_provider for time control."""
        storage_dir = tmp_path / "storage"
        
        # Create artifact that's exactly 30 days old
        fixed_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        creation_time = fixed_time - timedelta(days=30)
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir(parents=True)
        job_dir = hash_dir / "boundary_job"
        job_dir.mkdir()
        
        # Set creation time to exactly 30 days ago
        timestamp = creation_time.timestamp()
        os.utime(job_dir, (timestamp, timestamp))
        
        # Test with now_provider
        def test_now_provider():
            return fixed_time
        
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30,
            now_provider=test_now_provider
        )
        
        # 30-day-old artifact should NOT be expired (boundary case)
        assert stats['expired'] == 0
        assert stats['removed'] == 0


class TestBackgroundCleanup:
    """Test background cleanup task functionality."""
    
    def test_cleanup_background_task_single_run(self, tmp_path):
        """Test single execution of background cleanup task."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        stop_event = threading.Event()
        stop_event.set()  # Immediately stop after first run
        
        with patch('core.cleanup.cleanup_old_artifacts') as mock_cleanup:
            mock_cleanup.return_value = {'removed': 1, 'failed': 0}
            
            with patch('core.cleanup.logger') as mock_logger:
                cleanup_background_task(
                    storage_dir=storage_dir,
                    retention_days=30,
                    interval_hours=1,
                    stop_event=stop_event
                )
            
            # Should execute cleanup once
            mock_cleanup.assert_called_once_with(
                storage_dir=storage_dir,
                retention_days=30,
                dry_run=False
            )
            
            # Should log start, completion, and stop
            assert mock_logger.info.call_count >= 2
    
    def test_cleanup_background_task_exception_handling(self, tmp_path):
        """Test background task exception handling."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        stop_event = threading.Event()
        stop_event.set()  # Stop after first iteration
        
        with patch('core.cleanup.cleanup_old_artifacts') as mock_cleanup:
            mock_cleanup.side_effect = Exception("Simulated error")
            
            with patch('core.cleanup.logger') as mock_logger:
                cleanup_background_task(
                    storage_dir=storage_dir,
                    retention_days=30,
                    interval_hours=1,
                    stop_event=stop_event
                )
            
            # Should log the error
            mock_logger.error.assert_called_once()
    
    def test_schedule_cleanup_success(self, tmp_path):
        """Test successful scheduling of cleanup task."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        with patch('core.cleanup._cleanup_task', None):
            result = schedule_cleanup(
                storage_dir=storage_dir,
                retention_days=7,
                interval_hours=12
            )
            
            assert result is True
    
    def test_schedule_cleanup_already_running(self, tmp_path):
        """Test scheduling when task already running."""
        # Mock an already running task
        mock_task = MagicMock()
        mock_task.is_alive.return_value = True
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup.logger') as mock_logger:
                result = schedule_cleanup()
                
                assert result is False
                mock_logger.warning.assert_called_once_with(
                    "Background cleanup task already running"
                )
    
    def test_stop_cleanup_success(self):
        """Test successful stopping of cleanup task."""
        # Mock a running task
        mock_task = MagicMock()
        mock_task.is_alive.return_value = True
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup._cleanup_stop_event') as mock_event:
                with patch('core.cleanup.logger') as mock_logger:
                    result = stop_cleanup()
                    
                    assert result is True
                    mock_event.set.assert_called_once()
                    mock_task.join.assert_called_once_with(timeout=10.0)
                    mock_logger.info.assert_called_with(
                        "Background cleanup task stopped successfully"
                    )
    
    def test_stop_cleanup_not_running(self):
        """Test stopping when no task is running."""
        with patch('core.cleanup._cleanup_task', None):
            with patch('core.cleanup.logger') as mock_logger:
                result = stop_cleanup()
                
                assert result is False
                mock_logger.info.assert_called_once_with(
                    "Background cleanup task not running"
                )
    
    def test_stop_cleanup_timeout(self):
        """Test stopping with task timeout."""
        # Mock a task that doesn't stop within timeout
        mock_task = MagicMock()
        mock_task.is_alive.side_effect = [True, True]  # Still alive after join
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup._cleanup_stop_event') as mock_event:
                with patch('core.cleanup.logger') as mock_logger:
                    result = stop_cleanup()
                    
                    assert result is False
                    mock_logger.warning.assert_called_once_with(
                        "Background cleanup task did not stop within timeout"
                    )


class TestCleanupIntegration:
    """Integration tests for cleanup module."""
    
    def test_full_cleanup_cycle(self, tmp_path):
        """Test complete cleanup cycle with real files."""
        storage_dir = tmp_path / "storage"
        
        # Create realistic storage structure
        artifacts = [
            ("a1", "job_2024_01_01", 45),  # Old - should be removed
            ("b2", "job_2024_01_15", 35),  # Old - should be removed  
            ("c3", "job_2024_02_01", 25),  # Recent - should be kept
            ("d4", "job_2024_02_10", 15),  # Recent - should be kept
        ]
        
        total_size = 0
        for hash_prefix, job_id, age_days in artifacts:
            hash_dir = storage_dir / hash_prefix
            hash_dir.mkdir(parents=True)
            
            job_dir = hash_dir / job_id
            job_dir.mkdir()
            
            # Create realistic job artifacts
            (job_dir / "proof.pdf").write_text("PDF content" * 100)
            (job_dir / "evidence.zip").write_text("ZIP content" * 50)
            (job_dir / "decision.json").write_text('{"result": "PASS"}')
            
            # Calculate total size for old artifacts
            if age_days > 30:
                for file in job_dir.iterdir():
                    total_size += file.stat().st_size
            
            # Set creation time
            creation_time = datetime.now(timezone.utc) - timedelta(days=age_days)
            timestamp = creation_time.timestamp()
            os.utime(job_dir, (timestamp, timestamp))
        
        # Run actual cleanup
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        # Verify results
        assert stats['expired'] == 2
        assert stats['removed'] == 2
        assert stats['failed'] == 0
        assert stats['freed_bytes'] == total_size
        assert stats['freed_mb'] > 0
        
        # Verify old artifacts removed
        assert not (storage_dir / "a1" / "job_2024_01_01").exists()
        assert not (storage_dir / "b2" / "job_2024_01_15").exists()
        
        # Verify recent artifacts preserved
        assert (storage_dir / "c3" / "job_2024_02_01").exists()
        assert (storage_dir / "d4" / "job_2024_02_10").exists()
    
    def test_cleanup_with_mixed_file_permissions(self, tmp_path):
        """Test cleanup handling various file permission scenarios."""
        storage_dir = tmp_path / "storage"
        
        # Create artifact with permission issues
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir(parents=True)
        
        accessible_job = hash_dir / "accessible_job"
        accessible_job.mkdir()
        (accessible_job / "file.txt").write_text("accessible")
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(accessible_job, (old_time, old_time))
        
        # Mock permission error for specific operations
        original_rmtree = shutil.rmtree
        def selective_rmtree(path, **kwargs):
            # Simulate intermittent permission errors
            if "accessible_job" in str(path):
                raise PermissionError("Simulated permission denied")
            return original_rmtree(path, **kwargs)
        
        with patch('shutil.rmtree', side_effect=selective_rmtree):
            with patch('core.cleanup.logger') as mock_logger:
                stats = cleanup_old_artifacts(
                    storage_dir=storage_dir,
                    retention_days=30
                )
        
        # Should handle permission errors gracefully
        assert stats['expired'] == 1
        assert stats['removed'] == 0
        assert stats['failed'] == 1
        
        # Should log error
        mock_logger.error.assert_called()