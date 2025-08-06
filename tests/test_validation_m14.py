"""
Tests for M14 Validation Pack Generator.
"""

import pytest
import json
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from core.validation import (
    get_git_commit_hash,
    get_software_version,
    create_filled_pdf,
    create_validation_pack,
    get_validation_pack_info
)


class TestValidationPack:
    """Test validation pack generation."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_git_commit_hash(self):
        """Test git commit hash retrieval."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "abc123def456\n"
            
            hash_result = get_git_commit_hash()
            assert hash_result == "abc123de"
    
    def test_get_git_commit_hash_failure(self):
        """Test git commit hash retrieval failure."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            
            hash_result = get_git_commit_hash()
            assert hash_result == "unknown"
    
    def test_get_software_version(self):
        """Test software version retrieval."""
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = 'version = "1.2.3"'
                
                version = get_software_version()
                assert version == "1.2.3"
    
    def test_get_software_version_fallback(self):
        """Test software version fallback."""
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = False
            
            version = get_software_version()
            assert version == "0.1.0"
    
    def test_create_filled_pdf(self):
        """Test PDF creation from template."""
        output_path = self.temp_path / "test.pdf"
        
        # Mock template path
        template_path = Path("dummy_template.pdf")
        
        data = {
            "Software Version": "1.0.0",
            "Job ID": "test123",
            "Creator": "test@example.com"
        }
        
        success = create_filled_pdf(template_path, output_path, data)
        assert success is True
        assert output_path.exists()
    
    def test_create_validation_pack(self):
        """Test validation pack creation."""
        job_id = "test123"
        job_meta = {
            "creator": {"email": "test@example.com", "role": "op"},
            "approved": True,
            "approved_by": "qa@example.com",
            "approved_at": "2024-08-05T10:00:00Z"
        }
        
        output_path = self.temp_path / "validation_pack.zip"
        
        success = create_validation_pack(job_id, job_meta, output_path)
        assert success is True
        assert output_path.exists()
        
        # Verify ZIP contents
        with zipfile.ZipFile(output_path, 'r') as zipf:
            files = zipf.namelist()
            assert "IQ_Installation_Qualification.pdf" in files
            assert "OQ_Operational_Qualification.pdf" in files
            assert "PQ_Performance_Qualification.pdf" in files
            assert "manifest.json" in files
            
            # Check manifest content
            manifest_content = zipf.read("manifest.json")
            manifest = json.loads(manifest_content)
            
            assert manifest["validation_pack"]["job_id"] == job_id
            assert manifest["validation_pack"]["creator"] == "test@example.com"
            assert manifest["validation_pack"]["approved"] is True
            assert "file_hashes" in manifest["validation_pack"]
    
    def test_get_validation_pack_info(self):
        """Test validation pack info retrieval."""
        job_id = "test123"
        job_meta = {
            "creator": {"email": "test@example.com", "role": "op"},
            "approved": False,
            "created_at": "2024-08-05T10:00:00Z"
        }
        
        info = get_validation_pack_info(job_id, job_meta)
        
        assert info["job_id"] == job_id
        assert info["creator"] == "test@example.com"
        assert info["approved"] is False
        assert "software_version" in info
        assert "commit_hash" in info
        assert "files" in info
        assert len(info["files"]) == 4  # IQ, OQ, PQ, manifest
    
    def test_validation_pack_approved_job(self):
        """Test validation pack for approved job."""
        job_id = "test123"
        job_meta = {
            "creator": {"email": "test@example.com", "role": "op"},
            "approved": True,
            "approved_by": "qa@example.com",
            "approved_at": "2024-08-05T10:00:00Z"
        }
        
        output_path = self.temp_path / "validation_pack.zip"
        
        success = create_validation_pack(job_id, job_meta, output_path)
        assert success is True
        
        # Verify manifest includes approval info
        with zipfile.ZipFile(output_path, 'r') as zipf:
            manifest_content = zipf.read("manifest.json")
            manifest = json.loads(manifest_content)
            
            assert manifest["validation_pack"]["approved"] is True
            assert manifest["validation_pack"]["approved_by"] == "qa@example.com"
            assert manifest["validation_pack"]["approved_at"] == "2024-08-05T10:00:00Z"
    
    def test_validation_pack_file_hashes(self):
        """Test that file hashes are included in manifest."""
        job_id = "test123"
        job_meta = {
            "creator": {"email": "test@example.com", "role": "op"},
            "approved": False
        }
        
        output_path = self.temp_path / "validation_pack.zip"
        
        success = create_validation_pack(job_id, job_meta, output_path)
        assert success is True
        
        # Verify file hashes are present
        with zipfile.ZipFile(output_path, 'r') as zipf:
            manifest_content = zipf.read("manifest.json")
            manifest = json.loads(manifest_content)
            
            file_hashes = manifest["validation_pack"]["file_hashes"]
            assert "IQ_Installation_Qualification.pdf" in file_hashes
            assert "OQ_Operational_Qualification.pdf" in file_hashes
            assert "PQ_Performance_Qualification.pdf" in file_hashes
            assert "manifest.json" in file_hashes
            
            # Verify hashes are valid SHA-256
            for filename, file_hash in file_hashes.items():
                assert len(file_hash) == 64  # SHA-256 hex length
                assert all(c in '0123456789abcdef' for c in file_hash.lower())


if __name__ == "__main__":
    pytest.main([__file__]) 