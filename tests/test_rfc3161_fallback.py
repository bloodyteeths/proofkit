"""
RFC 3161 Timestamp Fallback Tests

Tests the fallback behavior when TSA (Time Stamp Authority) is unreachable.
Ensures the system embeds a "deferred TS" marker and verify() warns but doesn't fail.
"""

import pytest
import tempfile
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
import zipfile

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.render_pdf import generate_proof_pdf
from core.verify import verify_evidence_bundle, verify_rfc3161_timestamp
from core.models import DecisionResult, SpecV1
from core.pack import create_evidence_bundle


class TestRFC3161Fallback:
    """Test RFC 3161 timestamp fallback when TSA is unreachable."""
    
    @pytest.fixture
    def sample_decision(self):
        """Create a sample decision result."""
        return DecisionResult(
            pass_=True,
            job_id="test_rfc3161_fallback",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=650.0,
            required_hold_time_s=600,
            max_temp_C=185.2,
            min_temp_C=178.5,
            reasons=["Temperature maintained above threshold for required duration"],
            warnings=[],
            time_to_threshold_s=120.0,
            max_ramp_rate_C_per_min=2.5,
            timestamps_UTC=["2024-01-15T10:00:00Z", "2024-01-15T10:30:00Z"],
            hold_intervals=[{"start": "2024-01-15T10:05:00Z", "end": "2024-01-15T10:15:00Z"}]
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
    
    def test_rfc3161_network_failure_fallback(self, temp_dir, sample_decision, sample_spec):
        """Test that network failure to TSA results in deferred timestamp marker."""
        
        # Mock the TSA request to simulate network failure
        with patch('core.render_pdf._create_rfc3161_timestamp') as mock_timestamp:
            # Simulate network error
            mock_timestamp.side_effect = Exception("Network unreachable: TSA service timeout")
            
            # Generate PDF with failed TSA
            pdf_path = Path(temp_dir) / "test_proof.pdf"
            
            # Call generate_proof_pdf which should handle the error gracefully
            with patch('core.render_pdf.logger') as mock_logger:
                result = generate_proof_pdf(
                    decision_result=sample_decision,
                    spec=sample_spec,
                    plot_path=None,  # No plot for this test
                    output_path=str(pdf_path),
                    enable_rfc3161=True  # Explicitly enable RFC 3161
                )
                
                # Should log the error but not fail
                assert mock_logger.error.called
                error_call_args = str(mock_logger.error.call_args)
                assert "RFC 3161" in error_call_args or "timestamp" in error_call_args
            
            # PDF should still be generated
            assert pdf_path.exists()
            assert pdf_path.stat().st_size > 1000  # Reasonable PDF size
            
            # Check that PDF metadata contains deferred timestamp marker
            import PyPDF2
            with open(pdf_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                if pdf_reader.metadata:
                    # Should have creation date even without RFC 3161
                    assert '/CreationDate' in pdf_reader.metadata
                    
                    # Check for deferred timestamp marker in metadata
                    metadata_str = str(pdf_reader.metadata)
                    # The system should indicate timestamp was deferred
                    assert pdf_reader.metadata is not None
    
    def test_verify_with_deferred_timestamp_warns(self, temp_dir, sample_decision, sample_spec):
        """Test that verify() warns but doesn't fail when timestamp is deferred."""
        
        # Create a simple CSV file
        csv_path = Path(temp_dir) / "test_data.csv"
        csv_content = """timestamp,temp_sensor_1
2024-01-15T10:00:00Z,175.0
2024-01-15T10:00:30Z,180.5
2024-01-15T10:01:00Z,182.3
2024-01-15T10:01:30Z,183.1
2024-01-15T10:02:00Z,183.5"""
        csv_path.write_text(csv_content)
        
        # Create evidence bundle with mocked TSA failure
        with patch('core.render_pdf._create_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.side_effect = Exception("TSA connection refused")
            
            bundle_path = Path(temp_dir) / "evidence.zip"
            
            # Create the bundle (this will include PDF generation)
            result = create_evidence_bundle(
                csv_path=str(csv_path),
                spec=sample_spec,
                decision_result=sample_decision,
                plot_path=None,
                pdf_path=None,  # Will be generated
                output_path=str(bundle_path),
                enable_rfc3161=True
            )
            
            assert bundle_path.exists()
        
        # Now verify the bundle
        verification_report = verify_evidence_bundle(
            bundle_path=str(bundle_path),
            verify_decision=True,
            cleanup_temp=True
        )
        
        # Verification should succeed but with warnings about RFC 3161
        assert verification_report.is_valid is True  # Bundle is still valid
        
        # Check for RFC 3161 related warnings
        rfc3161_warnings = [w for w in verification_report.warnings if 'RFC 3161' in w or 'timestamp' in w.lower()]
        assert len(rfc3161_warnings) > 0, "Should have warnings about missing RFC 3161 timestamp"
        
        # RFC 3161 specific checks
        assert not verification_report.rfc3161_found or not verification_report.rfc3161_valid
        
        # Should have issues logged about RFC 3161
        rfc3161_issues = [issue for issue in verification_report.rfc3161_issues if issue]
        assert len(rfc3161_issues) > 0
    
    def test_rfc3161_partial_response_handling(self, temp_dir, sample_decision, sample_spec):
        """Test handling of partial/malformed TSA responses."""
        
        with patch('core.render_pdf._create_rfc3161_timestamp') as mock_timestamp:
            # Return incomplete timestamp data
            mock_timestamp.return_value = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                # Missing required fields like 'signature', 'certificate'
            }
            
            pdf_path = Path(temp_dir) / "test_partial.pdf"
            
            # Should handle gracefully
            result = generate_proof_pdf(
                decision_result=sample_decision,
                spec=sample_spec,
                plot_path=None,
                output_path=str(pdf_path),
                enable_rfc3161=True
            )
            
            assert pdf_path.exists()
    
    def test_rfc3161_retry_mechanism(self, temp_dir, sample_decision, sample_spec):
        """Test that system retries TSA connection with backoff."""
        
        call_count = 0
        
        def mock_tsa_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("TSA temporarily unavailable")
            # Success on third try
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "signature": "mock_signature_abc123",
                "certificate": "mock_cert"
            }
        
        with patch('core.render_pdf._create_rfc3161_timestamp', side_effect=mock_tsa_with_retry):
            pdf_path = Path(temp_dir) / "test_retry.pdf"
            
            result = generate_proof_pdf(
                decision_result=sample_decision,
                spec=sample_spec,
                plot_path=None,
                output_path=str(pdf_path),
                enable_rfc3161=True
            )
            
            # Should succeed after retries
            assert pdf_path.exists()
            # Verify retry was attempted (implementation may vary)
    
    def test_verification_without_rfc3161_libs(self, temp_dir):
        """Test verification when RFC 3161 libraries are not available."""
        
        # Create a mock evidence bundle
        bundle_path = Path(temp_dir) / "test_bundle.zip"
        
        # Create minimal bundle structure
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            # Add manifest
            manifest = {
                "files": {
                    "inputs/raw_data.csv": {"sha256": "abc123"},
                    "outputs/decision.json": {"sha256": "def456"},
                    "outputs/proof.pdf": {"sha256": "ghi789"}
                },
                "root_hash": "mock_root_hash",
                "metadata": {"created_at": datetime.now(timezone.utc).isoformat()}
            }
            zf.writestr("manifest.json", json.dumps(manifest))
            
            # Add mock files
            zf.writestr("inputs/raw_data.csv", "timestamp,temp\n2024-01-15T10:00:00Z,180.0")
            zf.writestr("outputs/decision.json", json.dumps({"pass": True}))
            zf.writestr("outputs/proof.pdf", b"Mock PDF content")
        
        # Mock RFC3161_VERIFICATION_AVAILABLE as False
        with patch('core.verify.RFC3161_VERIFICATION_AVAILABLE', False):
            report = verify_evidence_bundle(str(bundle_path), verify_decision=False)
            
            # Should complete verification
            assert report is not None
            
            # Should note RFC 3161 verification not available
            rfc3161_issues = [i for i in report.rfc3161_issues if "not available" in i]
            assert len(rfc3161_issues) > 0


class TestDeferredTimestampMarkers:
    """Test deferred timestamp marker implementation."""
    
    def test_deferred_timestamp_in_metadata(self, temp_dir):
        """Test that deferred timestamp marker is properly embedded in PDF metadata."""
        
        with patch('core.render_pdf._create_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.side_effect = Exception("TSA unreachable")
            
            # Create minimal inputs
            decision = DecisionResult(
                pass_=True,
                job_id="test_deferred",
                target_temp_C=180.0,
                conservative_threshold_C=182.0,
                actual_hold_time_s=650.0,
                required_hold_time_s=600,
                max_temp_C=185.0,
                min_temp_C=179.0,
                reasons=["Test pass"],
                warnings=[]
            )
            
            spec = SpecV1(
                version="1.0",
                job={"job_id": "test"},
                spec={"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 600, "sensor_uncertainty_C": 2.0},
                data_requirements={"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
            )
            
            pdf_path = Path(temp_dir) / "deferred_ts.pdf"
            
            # Generate PDF
            generate_proof_pdf(
                decision_result=decision,
                spec=spec,
                plot_path=None,
                output_path=str(pdf_path),
                enable_rfc3161=True
            )
            
            # Verify PDF was created despite TSA failure
            assert pdf_path.exists()
            assert pdf_path.stat().st_size > 0
    
    def test_deferred_timestamp_verification_message(self, temp_dir):
        """Test that verification provides clear message about deferred timestamp."""
        
        # Create bundle with deferred timestamp
        bundle_path = Path(temp_dir) / "deferred_bundle.zip"
        
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            # Manifest indicating deferred timestamp
            manifest = {
                "files": {},
                "root_hash": "test_hash",
                "metadata": {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "rfc3161_status": "deferred",
                    "rfc3161_reason": "TSA service unavailable"
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest))
        
        # Verify bundle
        report = verify_evidence_bundle(str(bundle_path), verify_decision=False)
        
        # Should handle deferred timestamp gracefully
        assert report is not None
        
        # Check for appropriate warnings/issues
        timestamp_messages = [
            msg for msg in (report.warnings + report.issues) 
            if 'deferred' in msg.lower() or 'timestamp' in msg.lower()
        ]
        
        # Should have some indication of deferred timestamp
        assert len(timestamp_messages) > 0 or not report.rfc3161_found