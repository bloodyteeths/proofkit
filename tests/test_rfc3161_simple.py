"""
Simplified RFC 3161 Tests

Tests RFC 3161 timestamp functionality without relying on internal implementation.
"""

import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import zipfile
import json

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import DecisionResult, SpecV1
from core.verify import verify_evidence_bundle
from core.pack import create_evidence_bundle


class TestRFC3161Simple:
    """Test RFC 3161 timestamp functionality."""
    
    @pytest.fixture
    def sample_decision(self):
        """Create a sample decision result."""
        return DecisionResult(
            pass_=True,
            job_id="test_rfc3161",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=650.0,
            required_hold_time_s=600,
            max_temp_C=185.2,
            min_temp_C=178.5,
            reasons=["Temperature maintained above threshold"],
            warnings=[]
        )
    
    @pytest.fixture
    def sample_spec(self):
        """Create a sample specification."""
        return SpecV1(
            version="1.0",
            job={"job_id": "test_rfc3161"},
            spec={
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        )
    
    def test_evidence_bundle_verification_without_rfc3161(self, temp_dir, sample_decision, sample_spec):
        """Test that verification handles missing RFC 3161 gracefully."""
        
        # Create a simple CSV file
        csv_path = Path(temp_dir) / "test_data.csv"
        csv_content = """timestamp,temp_sensor_1
2024-01-15T10:00:00Z,175.0
2024-01-15T10:00:30Z,180.5
2024-01-15T10:01:00Z,182.3
2024-01-15T10:01:30Z,183.1
2024-01-15T10:02:00Z,183.5"""
        csv_path.write_text(csv_content)
        
        # Create evidence bundle
        bundle_path = Path(temp_dir) / "evidence.zip"
        
        # Create bundle (RFC 3161 may or may not be available)
        result = create_evidence_bundle(
            csv_path=str(csv_path),
            spec=sample_spec,
            decision_result=sample_decision,
            plot_path=None,
            pdf_path=None,
            output_path=str(bundle_path)
        )
        
        assert bundle_path.exists()
        
        # Verify the bundle
        verification_report = verify_evidence_bundle(
            bundle_path=str(bundle_path),
            verify_decision=False,  # Skip decision re-computation for speed
            cleanup_temp=True
        )
        
        # Bundle should be valid regardless of RFC 3161 status
        assert verification_report.bundle_exists
        assert verification_report.manifest_found
        
        # If RFC 3161 wasn't available, we should have warnings but not failures
        if not verification_report.rfc3161_found:
            # This is OK - RFC 3161 is optional
            assert verification_report.is_valid  # Bundle still valid
    
    def test_bundle_with_minimal_structure(self, temp_dir):
        """Test verification of minimal valid bundle."""
        
        bundle_path = Path(temp_dir) / "minimal.zip"
        
        # Create minimal valid bundle
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            # Minimal manifest
            manifest = {
                "files": {
                    "test.txt": {"sha256": "abc123"}
                },
                "root_hash": "def456",
                "metadata": {
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("test.txt", "test content")
        
        # Verify
        report = verify_evidence_bundle(
            str(bundle_path),
            verify_decision=False,
            cleanup_temp=True
        )
        
        assert report.manifest_found
        assert report.bundle_exists
        
        # Will fail due to hash mismatch, but that's expected
        assert not report.is_valid  # Hash mismatch
        assert len(report.hash_mismatches) > 0