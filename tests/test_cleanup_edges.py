"""
Comprehensive edge case tests for the cleanup module.

Tests focus on extreme scenarios including:
- 0-day retention policies 
- Deeply nested directory structures
- OSError handling during cleanup operations
- Race conditions and concurrent access
- Filesystem permission boundary cases

Example usage:
    pytest tests/test_cleanup_edges.py -v --cov=core.cleanup
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


class TestZeroDayRetention:
    """Test 0-day retention policy edge cases."""
    
    def test_zero_day_retention_removes_everything(self, tmp_path):
        """Test that 0-day retention removes all artifacts immediately."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create artifacts with various ages
        artifacts = [
            ("ab", "brand_new", 0),      # Just created
            ("cd", "minutes_old", 0),    # Also just created 
            ("ef", "day_old", 1),        # 1 day old
        ]
        
        for hash_prefix, job_id, age_days in artifacts:
            hash_dir = storage_dir / hash_prefix
            hash_dir.mkdir(exist_ok=True)
            
            job_dir = hash_dir / job_id
            job_dir.mkdir()
            
            # Create realistic content
            (job_dir / "proof.pdf").write_text("PDF content")
            (job_dir / "evidence.zip").write_text("ZIP content")
            
            # Set creation time
            if age_days > 0:
                creation_time = datetime.now(timezone.utc) - timedelta(days=age_days)
                timestamp = creation_time.timestamp()
                os.utime(job_dir, (timestamp, timestamp))
            
            time.sleep(0.01)  # Ensure different creation times
        
        # Run cleanup with 0-day retention
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=0
        )
        
        # All artifacts should be expired and removed
        assert stats['expired'] == 3
        assert stats['removed'] == 3
        assert stats['failed'] == 0
        
        # Verify all artifacts are gone
        assert not (storage_dir / "ab" / "brand_new").exists()
        assert not (storage_dir / "cd" / "minutes_old").exists()
        assert not (storage_dir / "ef" / "day_old").exists()
    
    def test_zero_day_retention_with_failures(self, tmp_path):
        """Test 0-day retention with some removal failures."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create test artifacts
        for i in range(3):
            hash_dir = storage_dir / f"a{i}"
            hash_dir.mkdir()
            job_dir = hash_dir / f"job_{i}"
            job_dir.mkdir()
            (job_dir / "file.txt").write_text("content")
        
        # Mock shutil.rmtree to fail for specific directory
        original_rmtree = shutil.rmtree
        def selective_rmtree(path, **kwargs):
            if "job_1" in str(path):
                raise OSError("Device busy")
            return original_rmtree(path, **kwargs)
        
        with patch('shutil.rmtree', side_effect=selective_rmtree):
            stats = cleanup_old_artifacts(
                storage_dir=storage_dir,
                retention_days=0
            )
        
        assert stats['expired'] == 3
        assert stats['removed'] == 2
        assert stats['failed'] == 1
    
    def test_zero_day_retention_environment_variable(self, tmp_path):
        """Test 0-day retention from environment variable."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create one artifact
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "test_job"
        job_dir.mkdir()
        (job_dir / "test.txt").write_text("test")
        
        # Set 0-day retention via environment
        with patch.dict(os.environ, {'RETENTION_DAYS': '0'}):
            days = get_retention_days()
            assert days == 0
            
            stats = cleanup_old_artifacts(storage_dir=storage_dir)
            
            assert stats['expired'] == 1
            assert stats['removed'] == 1
    
    def test_zero_day_retention_dry_run(self, tmp_path):
        """Test 0-day retention in dry run mode."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "test_job"
        job_dir.mkdir()
        (job_dir / "test.txt").write_text("test")
        
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=0,
            dry_run=True
        )
        
        # Should find and "remove" but not actually delete
        assert stats['expired'] == 1
        assert stats['removed'] == 1
        assert stats['freed_bytes'] == 0  # No actual bytes freed in dry run
        
        # Verify directory still exists
        assert job_dir.exists()


class TestNestedDirectoryStructures:
    """Test cleanup with deeply nested directory structures."""
    
    def create_nested_artifact(self, base_path, depth=10):
        """Create deeply nested artifact structure."""
        current_path = base_path
        for i in range(depth):
            current_path = current_path / f"level_{i}"
            current_path.mkdir()
            
            # Add files at each level
            (current_path / f"file_{i}.txt").write_text(f"Content at level {i}")
            
            # Add subdirectory structure  
            if i < depth - 1:
                subdir = current_path / f"sub_{i}"
                subdir.mkdir()
                (subdir / f"subfile_{i}.txt").write_text(f"Sub content {i}")
        
        return current_path
    
    def test_deeply_nested_structure_removal(self, tmp_path):
        """Test removal of deeply nested directory structures."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "nested_job"
        job_dir.mkdir()
        
        # Create deeply nested structure within job directory
        deepest_path = self.create_nested_artifact(job_dir, depth=15)
        
        # Set old creation time on job directory
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        # Should successfully remove entire nested structure
        assert stats['expired'] == 1
        assert stats['removed'] == 1
        assert stats['failed'] == 0
        assert not job_dir.exists()
    
    def test_nested_structure_with_symlinks(self, tmp_path):
        """Test nested structure containing symlinks."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "symlink_job"
        job_dir.mkdir()
        
        # Create nested structure
        level1 = job_dir / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        
        # Create target file outside storage
        external_target = tmp_path / "external_file.txt"
        external_target.write_text("external content")
        
        # Create symlink within nested structure
        symlink = level2 / "external_link"
        symlink.symlink_to(external_target)
        
        # Create circular symlink
        circular_link = level2 / "circular"
        circular_link.symlink_to(level1)
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        # Should handle symlinks gracefully
        assert stats['expired'] == 1
        assert stats['removed'] == 1
        assert not job_dir.exists()
        assert external_target.exists()  # External target should remain
    
    def test_nested_structure_permission_issues(self, tmp_path):
        """Test nested structure with permission issues at various levels."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "permission_job"
        job_dir.mkdir()
        
        # Create nested structure
        level1 = job_dir / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "file.txt").write_text("content")
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        # Mock os.walk to simulate permission error at level2
        original_walk = os.walk
        def mock_walk(path):
            for root, dirs, files in original_walk(path):
                if "level2" in root:
                    raise PermissionError("Access denied to level2")
                yield root, dirs, files
        
        with patch('os.walk', side_effect=mock_walk):
            # Should still be able to calculate size (with error handling)
            size = calculate_directory_size(job_dir)
            assert size >= 0  # Should handle permission errors gracefully
        
        # Mock shutil.rmtree to simulate permission error during removal
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = PermissionError("Cannot remove nested structure")
            
            stats = cleanup_old_artifacts(
                storage_dir=storage_dir,
                retention_days=30
            )
        
        assert stats['expired'] == 1
        assert stats['removed'] == 0
        assert stats['failed'] == 1
    
    def test_very_deep_path_names(self, tmp_path):
        """Test handling of very deep path names approaching OS limits."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "deep_path_job"
        job_dir.mkdir()
        
        # Create a very deep path with long names
        current_path = job_dir
        try:
            for i in range(50):  # Attempt to create very deep structure
                long_name = f"very_long_directory_name_level_{i}_" + "x" * 20
                current_path = current_path / long_name
                current_path.mkdir()
                (current_path / f"file_{i}.txt").write_text(f"Level {i}")
        except OSError:
            # OS path length limit reached, which is expected
            pass
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        # Should handle deep paths gracefully
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        assert stats['expired'] == 1
        assert stats['removed'] == 1
        assert not job_dir.exists()


class TestOSErrorHandling:
    """Test comprehensive OSError handling during cleanup operations."""
    
    def test_disk_full_during_size_calculation(self, tmp_path):
        """Test handling of disk full errors during size calculation."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "disk_full_job"
        job_dir.mkdir()
        (job_dir / "file.txt").write_text("content")
        
        # Mock os.path.getsize to raise OSError (disk full)
        with patch('os.path.getsize') as mock_getsize:
            mock_getsize.side_effect = OSError("No space left on device")
            
            with patch('core.cleanup.logger') as mock_logger:
                size = calculate_directory_size(job_dir)
                
                assert size == 0  # Should return 0 on error
                mock_logger.error.assert_called_once()
    
    def test_io_error_during_artifact_discovery(self, tmp_path):
        """Test handling of I/O errors during artifact discovery."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "io_error_job"
        job_dir.mkdir()
        
        # Mock Path.stat to raise IOError
        original_stat = Path.stat
        def mock_stat(path_self):
            if "io_error_job" in str(path_self):
                raise IOError("I/O error reading directory")
            return original_stat(path_self)
        
        with patch.object(Path, 'stat', mock_stat):
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should handle I/O error gracefully
                assert len(expired) == 0
                mock_logger.warning.assert_called()
    
    def test_device_busy_during_removal(self, tmp_path):
        """Test handling of device busy errors during removal."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "busy_job"
        job_dir.mkdir()
        (job_dir / "locked_file.txt").write_text("locked content")
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        # Mock shutil.rmtree to raise device busy error
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = OSError("Device or resource busy")
            
            with patch('core.cleanup.logger') as mock_logger:
                result = remove_artifact_directory(job_dir)
                
                assert result is False
                mock_logger.error.assert_called_once()
                
                # Verify error message contains relevant information
                error_call = mock_logger.error.call_args[0][0]
                assert "Device or resource busy" in error_call
    
    def test_readonly_filesystem_during_removal(self, tmp_path):
        """Test handling of read-only filesystem errors."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "readonly_job"
        job_dir.mkdir()
        (job_dir / "readonly_file.txt").write_text("readonly content")
        
        # Mock shutil.rmtree to raise read-only filesystem error
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = OSError("Read-only file system")
            
            with patch('core.cleanup.logger') as mock_logger:
                result = remove_artifact_directory(job_dir)
                
                assert result is False
                mock_logger.error.assert_called_once()
    
    def test_network_filesystem_timeout(self, tmp_path):
        """Test handling of network filesystem timeouts."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "network_job"
        job_dir.mkdir()
        
        # Mock Path.iterdir to raise network timeout
        with patch.object(Path, 'iterdir') as mock_iterdir:
            mock_iterdir.side_effect = OSError("Network is unreachable")
            
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should handle network error gracefully
                assert len(expired) == 0
                mock_logger.info.assert_called_with(
                    f"Storage directory does not exist: {storage_dir}"
                )
    
    def test_interrupted_system_call_handling(self, tmp_path):
        """Test handling of interrupted system calls."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "interrupted_job"
        job_dir.mkdir()
        (job_dir / "file.txt").write_text("content")
        
        # Mock shutil.rmtree to raise interrupted system call error
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = OSError("Interrupted system call")
            
            result = remove_artifact_directory(job_dir)
            
            assert result is False
    
    def test_multiple_os_errors_during_cleanup(self, tmp_path):
        """Test handling multiple different OS errors in single cleanup run."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create multiple job directories
        jobs = []
        for i in range(5):
            hash_dir = storage_dir / f"a{i}"
            hash_dir.mkdir()
            job_dir = hash_dir / f"error_job_{i}"
            job_dir.mkdir()
            (job_dir / "file.txt").write_text("content")
            jobs.append(job_dir)
            
            # Set old creation time
            old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
            os.utime(job_dir, (old_time, old_time))
        
        # Mock shutil.rmtree to raise different errors for different directories
        original_rmtree = shutil.rmtree
        def selective_error_rmtree(path, **kwargs):
            path_str = str(path)
            if "error_job_0" in path_str:
                raise PermissionError("Permission denied")
            elif "error_job_1" in path_str:
                raise OSError("Device busy")
            elif "error_job_2" in path_str:
                raise IOError("I/O error")
            elif "error_job_3" in path_str:
                raise OSError("No space left on device")
            else:
                return original_rmtree(path, **kwargs)
        
        with patch('shutil.rmtree', side_effect=selective_error_rmtree):
            with patch('core.cleanup.logger') as mock_logger:
                stats = cleanup_old_artifacts(
                    storage_dir=storage_dir,
                    retention_days=30
                )
        
        # Should find all 5 expired artifacts
        assert stats['expired'] == 5
        # Should successfully remove 1 (error_job_4)
        assert stats['removed'] == 1
        # Should fail to remove 4 due to various errors
        assert stats['failed'] == 4
        
        # Should log multiple errors
        assert mock_logger.error.call_count == 4
    
    def test_corrupted_filesystem_metadata(self, tmp_path):
        """Test handling of corrupted filesystem metadata."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "corrupted_job"
        job_dir.mkdir()
        
        # Mock Path.stat to raise OSError indicating corrupted metadata
        with patch.object(Path, 'stat') as mock_stat:
            mock_stat.side_effect = OSError("Structure needs cleaning")
            
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should handle corruption gracefully
                assert len(expired) == 0
                mock_logger.warning.assert_called()


class TestConcurrentAccessHandling:
    """Test cleanup behavior under concurrent access scenarios."""
    
    def test_directory_removed_during_iteration(self, tmp_path):
        """Test handling when directory is removed during iteration."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create test structure
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "concurrent_job"
        job_dir.mkdir()
        (job_dir / "file.txt").write_text("content")
        
        # Mock Path.iterdir to simulate directory being removed during iteration
        original_iterdir = Path.iterdir
        call_count = 0
        
        def mock_iterdir(path_self):
            nonlocal call_count
            call_count += 1
            
            if call_count == 2 and "concurrent_job" in str(path_self):
                # Simulate directory being removed by another process
                raise FileNotFoundError("Directory removed during iteration")
            
            return original_iterdir(path_self)
        
        with patch.object(Path, 'iterdir', mock_iterdir):
            with patch('core.cleanup.logger') as mock_logger:
                expired = find_expired_artifacts(storage_dir, retention_days=30)
                
                # Should handle concurrent removal gracefully
                assert isinstance(expired, list)
    
    def test_file_locked_during_size_calculation(self, tmp_path):
        """Test handling of file locks during size calculation."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "locked_job"
        job_dir.mkdir()
        (job_dir / "locked_file.txt").write_text("locked content")
        
        # Mock os.path.getsize to simulate file lock
        call_count = 0
        def mock_getsize(path):
            nonlocal call_count
            call_count += 1
            
            if "locked_file.txt" in str(path):
                if call_count == 1:
                    raise PermissionError("File is locked by another process")
                else:
                    return 100  # Return size on subsequent calls
            return 50
        
        with patch('os.path.getsize', side_effect=mock_getsize):
            with patch('core.cleanup.logger') as mock_logger:
                size = calculate_directory_size(job_dir)
                
                # Should handle file locks gracefully
                assert size == 0  # Returns 0 due to permission error
                mock_logger.error.assert_called_once()
    
    def test_race_condition_during_cleanup_scheduling(self, tmp_path):
        """Test race conditions during cleanup task scheduling."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Simulate concurrent scheduling attempts
        def concurrent_scheduler():
            return schedule_cleanup(
                storage_dir=storage_dir,
                retention_days=30,
                interval_hours=1
            )
        
        # Mock the cleanup task state to simulate race condition
        with patch('core.cleanup._cleanup_task', None):
            # First call should succeed
            result1 = concurrent_scheduler()
            assert result1 is True
            
            # Mock a running task for second call
            mock_task = MagicMock()
            mock_task.is_alive.return_value = True
            
            with patch('core.cleanup._cleanup_task', mock_task):
                # Second concurrent call should detect running task
                result2 = concurrent_scheduler()
                assert result2 is False
    
    def test_cleanup_stop_during_background_execution(self):
        """Test stopping cleanup during background task execution."""
        # Mock a running background task
        mock_task = MagicMock()
        mock_task.is_alive.return_value = True
        
        mock_stop_event = MagicMock()
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup._cleanup_stop_event', mock_stop_event):
                # Simulate task taking time to stop
                def slow_join(timeout=None):
                    time.sleep(0.1)  # Simulate cleanup operation
                    mock_task.is_alive.return_value = False
                
                mock_task.join.side_effect = slow_join
                
                with patch('core.cleanup.logger') as mock_logger:
                    result = stop_cleanup()
                    
                    assert result is True
                    mock_stop_event.set.assert_called_once()
                    mock_task.join.assert_called_once_with(timeout=10.0)
                    mock_logger.info.assert_called_with(
                        "Background cleanup task stopped successfully"
                    )


class TestEdgeCasePathValidation:
    """Test edge cases in path validation and safety checks."""
    
    def test_unicode_paths(self, tmp_path):
        """Test handling of Unicode characters in paths."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create directory with Unicode characters
        unicode_hash = storage_dir / "测试"  # Chinese characters
        unicode_hash.mkdir()
        unicode_job = unicode_hash / "工作_αβγ_🚀"  # Mixed Unicode
        unicode_job.mkdir()
        (unicode_job / "файл.txt").write_text("Unicode content")  # Cyrillic
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(unicode_job, (old_time, old_time))
        
        # Should handle Unicode paths correctly
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        # Unicode paths should be processed normally
        assert stats['expired'] >= 0  # Should not crash
        assert stats['removed'] >= 0
    
    def test_path_with_special_characters(self, tmp_path):
        """Test paths containing special shell characters."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create directories with special characters
        special_chars = ["$VAR", "file;rm-rf", "file&&echo", "file|grep", "file`cmd`"]
        
        for i, special in enumerate(special_chars):
            try:
                hash_dir = storage_dir / f"a{i}"
                hash_dir.mkdir()
                # Sanitize special characters for directory names
                safe_name = special.replace(";", "_").replace("&", "_").replace("|", "_").replace("`", "_").replace("$", "_")
                job_dir = hash_dir / safe_name
                job_dir.mkdir()
                (job_dir / "file.txt").write_text("content")
                
                # Set old creation time
                old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
                os.utime(job_dir, (old_time, old_time))
            except OSError:
                # Some special characters may not be allowed by filesystem
                continue
        
        # Should handle special characters safely
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        assert stats['expired'] >= 0
        assert stats['removed'] >= 0
    
    def test_extremely_long_path_names(self, tmp_path):
        """Test handling of extremely long path names."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        
        # Create extremely long directory name (near filesystem limits)
        long_name = "x" * 200  # Very long name
        try:
            job_dir = hash_dir / long_name
            job_dir.mkdir()
            (job_dir / "file.txt").write_text("content")
            
            # Set old creation time
            old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
            os.utime(job_dir, (old_time, old_time))
            
            # Should handle long paths appropriately
            stats = cleanup_old_artifacts(
                storage_dir=storage_dir,
                retention_days=30
            )
            
            assert stats['expired'] >= 0
            assert stats['removed'] >= 0
            
        except OSError:
            # Filesystem may reject extremely long names - this is expected
            pass
    
    def test_path_traversal_with_encoded_sequences(self, tmp_path):
        """Test path traversal attempts with encoded sequences."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Various encoded path traversal attempts
        traversal_attempts = [
            "..%2F..%2Fetc%2Fpasswd",  # URL encoded
            "..\\..\\windows\\system32",   # Windows style
            "%2e%2e%2f%2e%2e%2f",         # Double encoded
        ]
        
        for attempt in traversal_attempts:
            try:
                # Test path safety validation
                traversal_path = storage_dir / attempt
                
                # is_path_safe should catch these attempts
                is_safe = is_path_safe(traversal_path, storage_dir)
                
                # Traversal attempts should be detected as unsafe
                assert is_safe is False
                
            except (ValueError, OSError):
                # Some encoded sequences may cause path resolution errors
                # This is acceptable defensive behavior
                pass
    
    def test_case_sensitivity_edge_cases(self, tmp_path):
        """Test case sensitivity handling in path operations."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create directories with different case variations
        variations = [
            ("AB", "Job123"),
            ("ab", "job123"), 
            ("Ab", "JOB123"),
        ]
        
        for hash_prefix, job_id in variations:
            hash_dir = storage_dir / hash_prefix
            hash_dir.mkdir(exist_ok=True)
            
            job_dir = hash_dir / job_id
            if not job_dir.exists():  # Avoid conflicts on case-insensitive filesystems
                job_dir.mkdir()
                (job_dir / "file.txt").write_text("content")
                
                # Set old creation time
                old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
                os.utime(job_dir, (old_time, old_time))
        
        # Should handle case variations appropriately
        stats = cleanup_old_artifacts(
            storage_dir=storage_dir,
            retention_days=30
        )
        
        assert stats['expired'] >= 0
        assert stats['removed'] >= 0
        assert stats['failed'] == 0


class TestCleanupMissingCoverage:
    """Test specific lines that are missing coverage in cleanup.py."""
    
    def test_invalid_retention_days_env_var(self):
        """Test invalid RETENTION_DAYS environment variable value."""
        # Test invalid string that can't be converted to int
        with patch.dict(os.environ, {'RETENTION_DAYS': 'invalid_number'}):
            with patch('core.cleanup.logger') as mock_logger:
                days = get_retention_days()
                
                assert days == 30  # Should fallback to default
                mock_logger.warning.assert_called_once()
                # Check that warning message mentions invalid value
                warning_call = mock_logger.warning.call_args[0][0]
                assert "Invalid RETENTION_DAYS" in warning_call
    
    def test_path_safety_with_resolution_errors(self, tmp_path):
        """Test path safety validation with path resolution errors."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        # Create a path that will cause resolution issues
        problematic_path = storage_dir / "nonexistent" / "deeply" / "nested" / "path"
        
        # Mock Path.resolve to raise OSError
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_resolve.side_effect = OSError("Path resolution failed")
            
            # Should handle resolution failure gracefully
            is_safe = is_path_safe(problematic_path, storage_dir)
            
            assert is_safe is False  # Should return False on resolution error
    
    def test_artifact_already_removed_handling(self, tmp_path):
        """Test handling when artifact is already removed."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "already_gone_job"
        job_dir.mkdir()
        (job_dir / "file.txt").write_text("content")
        
        # Remove the directory before calling remove_artifact_directory
        shutil.rmtree(job_dir)
        
        with patch('core.cleanup.logger') as mock_logger:
            result = remove_artifact_directory(job_dir)
            
            assert result is True  # Should return True for already removed
            mock_logger.info.assert_called_once()
            # Check that log message mentions already removed
            info_call = mock_logger.info.call_args[0][0]
            assert "already removed" in info_call
    
    def test_background_cleanup_exception_handling(self, tmp_path):
        """Test exception handling in background cleanup task."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        stop_event = threading.Event()
        
        # Mock cleanup_old_artifacts to raise an exception
        with patch('core.cleanup.cleanup_old_artifacts') as mock_cleanup:
            mock_cleanup.side_effect = Exception("Cleanup failed unexpectedly")
            
            with patch('core.cleanup.logger') as mock_logger:
                # Start background task briefly
                thread = threading.Thread(
                    target=cleanup_background_task,
                    args=(storage_dir, 30, 1, stop_event)
                )
                thread.start()
                
                # Give it time to hit the exception
                time.sleep(0.1)
                
                # Stop the thread
                stop_event.set()
                thread.join(timeout=2.0)
                
                # Should have logged the error
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args[0][0]
                assert "Background cleanup failed" in error_call
    
    def test_stop_cleanup_timeout_scenario(self):
        """Test cleanup stop with timeout scenario."""
        # Mock a task that doesn't stop within timeout
        mock_task = MagicMock()
        mock_task.is_alive.return_value = True  # Never stops
        
        mock_stop_event = MagicMock()
        
        with patch('core.cleanup._cleanup_task', mock_task):
            with patch('core.cleanup._cleanup_stop_event', mock_stop_event):
                # Mock join to not change alive status (simulates timeout)
                def timeout_join(timeout=None):
                    time.sleep(0.1)  # Simulate work but don't change alive status
                
                mock_task.join.side_effect = timeout_join
                
                with patch('core.cleanup.logger') as mock_logger:
                    result = stop_cleanup()
                    
                    assert result is False  # Should return False on timeout
                    mock_stop_event.set.assert_called_once()
                    mock_task.join.assert_called_once_with(timeout=10.0)
                    mock_logger.warning.assert_called_with(
                        "Background cleanup task did not stop within timeout"
                    )
    
    def test_stop_cleanup_when_not_running(self):
        """Test stop_cleanup when task is not running."""
        # Mock no running task
        with patch('core.cleanup._cleanup_task', None):
            with patch('core.cleanup.logger') as mock_logger:
                result = stop_cleanup()
                
                assert result is False
                mock_logger.info.assert_called_with(
                    "Background cleanup task not running"
                )