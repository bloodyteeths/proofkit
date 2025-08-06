"""
ProofKit Edge Case Tests for render_pdf and verify

Tests edge cases for render_pdf.py and verify.py modules including:
- render_pdf: invalid image handling
- render_pdf: font setup branch coverage  
- verify: tampered manifest vs tampered file detection
- Uses mocks and tiny fixtures under 200 lines

Example: pytest tests/test_render_verify_edge.py -v
"""

import pytest
import tempfile
import json
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.models import SpecV1, DecisionResult
from core.render_pdf import generate_proof_pdf, _setup_fonts
from core.verify import verify_evidence_bundle, verify_bundle_integrity, VerificationReport


@pytest.fixture
def minimal_spec():
    """Create minimal test spec."""
    return SpecV1(
        job={"job_id": "edge_test_001"},
        spec={
            "method": "PMT",
            "target_temp_C": 170.0,
            "hold_time_s": 480,
            "sensor_uncertainty_C": 2.0
        },
        data_requirements={
            "max_sample_period_s": 60.0,
            "allowed_gaps_s": 30.0
        }
    )


@pytest.fixture
def minimal_decision():
    """Create minimal test decision."""
    return DecisionResult(
        pass_=True,
        job_id="edge_test_001",
        target_temp_C=170.0,
        conservative_threshold_C=172.0,
        actual_hold_time_s=500.0,
        required_hold_time_s=480,
        max_temp_C=175.0,
        min_temp_C=168.0,
        reasons=["Test passed"],
        warnings=[]
    )


class TestRenderPDFEdgeCases:
    """Test edge cases for render_pdf module."""
    
    def test_plot_path_invalid_image_error(self, minimal_spec, minimal_decision, temp_dir):
        """Test render_pdf behavior with invalid image file."""
        # Create a file that exists but is not a valid image
        fake_plot = temp_dir / "fake_plot.png"
        fake_plot.write_bytes(b"this is not a valid PNG file at all")
        
        # Current implementation does not handle this gracefully - it raises an exception
        # This test documents the current behavior
        with pytest.raises(Exception):  # PIL.UnidentifiedImageError or wrapped variant
            generate_proof_pdf(
                spec=minimal_spec,
                decision=minimal_decision,
                plot_path=fake_plot,
                verification_hash="runtime_error_test"
            )
    
    def test_missing_font_fallback(self):
        """Test font setup function behaves correctly."""
        # Test that _setup_fonts runs without errors (it's a no-op function)
        try:
            _setup_fonts()  # Should not raise - it's an empty function
            # Function should complete successfully
            assert True
        except Exception as e:
            pytest.fail(f"_setup_fonts() raised {e} unexpectedly!")


class TestVerifyEdgeCases:
    """Test edge cases for verify module."""
    
    def test_tampered_manifest_vs_file(self, temp_dir):
        """Test detection of tampered file vs manifest."""
        bundle_path = temp_dir / "tampered_test.zip" 
        fake_content = b"test_content"
        fake_hash = hashlib.sha256(fake_content).hexdigest()
        manifest_data = {
            "files": {"test.csv": {"sha256": fake_hash, "size": len(fake_content)}},
            "metadata": {"created": "2024-01-01T00:00:00Z"},
            "root_hash": hashlib.sha256(fake_hash.encode()).hexdigest()
        }
        
        # Create ZIP with tampered file content
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))
            zf.writestr("test.csv", b"TAMPERED_CONTENT")  # Wrong content
        
        # Test integrity check
        temp_extract_dir = tempfile.mkdtemp()
        try:
            extracted_files = {}
            with zipfile.ZipFile(bundle_path, 'r') as zf:
                for name in zf.namelist():
                    extract_path = Path(temp_extract_dir) / name
                    extract_path.parent.mkdir(parents=True, exist_ok=True)
                    extract_path.write_bytes(zf.read(name))
                    extracted_files[name] = str(extract_path)
            
            integrity_valid, details = verify_bundle_integrity(str(bundle_path), extracted_files)
            assert not integrity_valid
            assert len(details["hash_mismatches"]) == 1
        finally:
            import shutil
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
    
    def test_tampered_manifest_hash(self, temp_dir):
        """Test detection of tampered manifest with wrong root hash."""
        bundle_path = temp_dir / "tampered_manifest.zip"
        fake_content = b"test_content"
        fake_hash = hashlib.sha256(fake_content).hexdigest()
        manifest_data = {
            "files": {"test_file.txt": {"sha256": fake_hash, "size": len(fake_content)}},
            "metadata": {"created": "2024-01-01T00:00:00Z"}, 
            "root_hash": "wrong_root_hash_intentionally_bad"
        }
        
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("manifest.json", json.dumps(manifest_data))
            zf.writestr("test_file.txt", fake_content)
        
        report = verify_evidence_bundle(str(bundle_path), verify_decision=False)
        assert not report.is_valid
        assert not report.root_hash_valid
    
    def test_verification_error_handling(self, temp_dir):
        """Test verification error handling with corrupted bundle."""
        # Create a fake ZIP file with invalid content
        bad_bundle = temp_dir / "corrupted.zip"
        bad_bundle.write_bytes(b"This is not a valid ZIP file")
        
        # Should handle corruption gracefully
        report = verify_evidence_bundle(str(bad_bundle))
        
        assert not report.is_valid
        assert not report.bundle_exists or len(report.issues) > 0
    
    def test_missing_bundle_file(self, temp_dir):
        """Test verification of non-existent bundle."""
        missing_bundle = temp_dir / "does_not_exist.zip"
        
        report = verify_evidence_bundle(str(missing_bundle))
        
        assert not report.is_valid
        assert not report.bundle_exists
        assert any("not found" in issue.lower() for issue in report.issues)


class TestMockingScenarios:
    """Test scenarios using mocks for tiny fixtures."""
    
    def test_mock_pdf_generation_failure(self, minimal_spec, minimal_decision, temp_dir):
        """Test PDF generation with mocked ReportLab failure."""
        fake_plot = temp_dir / "mock_plot.png"
        fake_plot.write_bytes(b"fake_png_data")
        
        with patch('core.render_pdf.SimpleDocTemplate') as mock_doc:
            mock_doc.side_effect = Exception("ReportLab initialization failed")
            with pytest.raises(Exception):
                generate_proof_pdf(spec=minimal_spec, decision=minimal_decision, plot_path=fake_plot)
    
    def test_mock_verification_missing_rfc3161(self):
        """Test verification with mocked missing RFC3161 dependencies."""
        with patch('core.verify.RFC3161_VERIFICATION_AVAILABLE', False):
            report = VerificationReport()
            report.bundle_exists = True
            report.manifest_found = True
            assert not report.rfc3161_found
            report.finalize()