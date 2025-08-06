"""
Extra edge case tests for cleanup module.

Tests focus on:
- chmod 000 permission issues during cleanup
- Very deep nested directory structures
- Minimal mocks and fixtures for targeted testing

Example usage:
    pytest tests/test_cleanup_extra.py -v
"""

import pytest
import os
import stat
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.cleanup import (
    calculate_directory_size,
    remove_artifact_directory,
    cleanup_old_artifacts,
)


class TestPermissionEdgeCases:
    """Test cleanup behavior with permission issues."""
    
    def test_chmod_000_file_skipped_with_logging(self, tmp_path):
        """Test that chmod 000 file is skipped gracefully with logging."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "permission_job"
        job_dir.mkdir()
        
        # Create file and remove all permissions
        restricted_file = job_dir / "restricted.txt"
        restricted_file.write_text("restricted content")
        restricted_file.chmod(0o000)  # No permissions at all
        
        # Set old creation time on job directory
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        try:
            with patch('core.cleanup.logger') as mock_logger:
                # Size calculation should skip the restricted file
                size = calculate_directory_size(job_dir)
                assert size >= 0  # Should complete without crashing
                
                # Should log warning about inaccessible file
                mock_logger.warning.assert_called()
                warning_call = mock_logger.warning.call_args[0][0]
                assert "Cannot access file" in warning_call
                assert str(restricted_file) in warning_call
                
        finally:
            # Restore permissions for cleanup
            restricted_file.chmod(0o644)
    
    def test_chmod_000_directory_removal_fails_gracefully(self, tmp_path):
        """Test removal of directory with chmod 000 subdirectory."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "protected_job"
        job_dir.mkdir()
        
        # Create subdirectory with no permissions
        restricted_dir = job_dir / "restricted"
        restricted_dir.mkdir()
        (restricted_dir / "file.txt").write_text("content")
        restricted_dir.chmod(0o000)
        
        try:
            with patch('core.cleanup.logger') as mock_logger:
                # Attempt to remove should fail but be handled gracefully
                result = remove_artifact_directory(job_dir)
                
                # Should fail due to permission error
                assert result is False
                
                # Should log error about removal failure
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args[0][0]
                assert "Failed to remove artifact directory" in error_call
                
        finally:
            # Restore permissions for test cleanup
            restricted_dir.chmod(0o755)


class TestDeepNestedStructures:
    """Test cleanup with very deep directory structures."""
    
    def create_deep_structure(self, base_path, depth=50):
        """Create a very deep nested directory structure efficiently."""
        current_path = base_path
        
        for level in range(depth):
            current_path = current_path / f"lvl{level}"
            current_path.mkdir()
            
            # Add small file at each level
            (current_path / f"f{level}.txt").write_text(f"L{level}")
            
            if level > depth - 10:  # Only add complexity near the end
                (current_path / f"extra{level}.dat").write_text("data")
        
        return current_path
    
    def test_very_deep_nested_directory_removed_successfully(self, tmp_path):
        """Test successful removal of very deep nested directory."""
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "deep_job"
        job_dir.mkdir()
        
        # Create deep structure (50 levels)
        try:
            deepest_path = self.create_deep_structure(job_dir, depth=50)
            
            # Verify structure was created successfully
            assert deepest_path.exists()
            
            # Set old creation time on job directory
            old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
            os.utime(job_dir, (old_time, old_time))
            
            # Remove the entire structure
            result = remove_artifact_directory(job_dir)
            
            # Should successfully remove entire deep structure
            assert result is True
            assert not job_dir.exists()
            
        except OSError:
            # Some filesystems have path length limits
            pytest.skip("Filesystem path length limit reached")
    
    def test_deep_structure_size_calculation_with_mock(self, tmp_path):
        """Test size calculation on deep structure using mocks for efficiency."""
        job_dir = tmp_path / "mock_deep_job"
        job_dir.mkdir()
        
        # Mock os.walk to simulate deep structure without creating it
        mock_walk_data = []
        
        # Simulate 100-level deep structure
        for level in range(100):
            dir_path = str(job_dir / "/".join([f"level_{i}" for i in range(level + 1)]))
            files = [f"file_{level}.txt", f"data_{level}.bin"]
            mock_walk_data.append((dir_path, [], files))
        
        # Mock file sizes
        def mock_stat(path):
            stat_result = MagicMock()
            stat_result.st_size = 1024  # 1KB per file
            return stat_result
        
        with patch('os.walk', return_value=mock_walk_data):
            with patch.object(Path, 'is_file', return_value=True):
                with patch.object(Path, 'stat', mock_stat):
                    size = calculate_directory_size(job_dir)
                    
                    # Should calculate size for all mocked files
                    # 100 levels * 2 files * 1024 bytes = 204,800 bytes
                    expected_size = 100 * 2 * 1024
                    assert size == expected_size


class TestMinimalMockingScenarios:
    """Test with minimal, focused mocks for specific edge cases."""
    
    def test_cleanup_with_minimal_fixture_and_precise_mocking(self, tmp_path):
        """Test cleanup with minimal fixture and targeted mocking."""
        # Minimal fixture: single directory structure
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        hash_dir = storage_dir / "ab"
        hash_dir.mkdir()
        job_dir = hash_dir / "test_job"
        job_dir.mkdir()
        test_file = job_dir / "test.txt"
        test_file.write_text("test content")
        
        # Set old creation time
        old_time = (datetime.now(timezone.utc) - timedelta(days=35)).timestamp()
        os.utime(job_dir, (old_time, old_time))
        
        # Precise mock: only mock shutil.rmtree to test error handling
        with patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = PermissionError("Operation not permitted")
            
            with patch('core.cleanup.logger') as mock_logger:
                stats = cleanup_old_artifacts(
                    storage_dir=storage_dir,
                    retention_days=30
                )
                
                # Verify specific behavior
                assert stats['expired'] == 1
                assert stats['removed'] == 0
                assert stats['failed'] == 1
                
                # Verify precise logging
                mock_logger.error.assert_called_once()
                error_args = mock_logger.error.call_args
                assert "Failed to remove artifact directory" in error_args[0][0]
    
    def test_tiny_fixture_with_focused_assertion(self, tmp_path):
        """Test with minimal fixture focusing on single assertion."""
        # Tiny fixture: just what we need
        job_dir = tmp_path / "minimal_job"
        job_dir.mkdir()
        (job_dir / "file.txt").write_text("data")
        
        # Test single specific behavior: directory exists check
        result = remove_artifact_directory(job_dir, dry_run=True)
        
        # Single focused assertion
        assert result is True  # Dry run should always succeed
        assert job_dir.exists()  # Directory should remain in dry run