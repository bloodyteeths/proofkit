#!/usr/bin/env python3
"""
Test PDF download blocking based on validation failures.

Tests the PDF validation gates that block download when compliance
requirements cannot be met (ENFORCE_PDF_A3=1 or BLOCK_IF_NO_TSA=1).
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from core.models import SpecV1, DecisionResult, Job, Spec
from core.render_pdf import (
    generate_proof_pdf, 
    check_pdf_validation_gates, 
    PDFValidationError,
    PDF_COMPLIANCE_AVAILABLE
)


def create_test_spec() -> SpecV1:
    """Create a test specification."""
    return SpecV1(
        job=Job(job_id="test123"),
        spec=Spec(
            method="powder",
            target_temp_C=180.0,
            hold_time_s=600,
            sensor_uncertainty_C=2.0
        )
    )


def create_test_decision(status: str = "PASS") -> DecisionResult:
    """Create a test decision result."""
    return DecisionResult(
        pass_=status == "PASS",
        status=status,
        actual_hold_time_s=650.0,
        required_hold_time_s=600.0,
        max_temp_C=185.0,
        min_temp_C=175.0,
        conservative_threshold_C=182.0,
        reasons=[] if status == "PASS" else ["Insufficient hold time"],
        warnings=[]
    )


def create_test_plot(temp_dir: Path) -> Path:
    """Create a mock plot file."""
    plot_path = temp_dir / "test_plot.png"
    plot_path.write_bytes(b"mock png data")
    return plot_path


class TestPDFValidationGates:
    """Test PDF validation gate functionality."""
    
    def test_pdf_validation_gates_pass_default(self):
        """Test that validation gates pass by default."""
        decision = create_test_decision("PASS")
        
        result = check_pdf_validation_gates(decision)
        
        assert result["gate_status"] == "PASS"
        assert not result["should_block"]
        assert len(result["blocking_reasons"]) == 0
    
    @patch.dict(os.environ, {"ENFORCE_PDF_A3": "1"})
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False)
    def test_pdf_validation_gates_block_pdf_a3(self):
        """Test that PDF/A-3 enforcement blocks when dependencies unavailable."""
        decision = create_test_decision("PASS")
        
        with pytest.raises(PDFValidationError, match="PDF/A-3 compliance required"):
            check_pdf_validation_gates(decision)
    
    @patch.dict(os.environ, {"BLOCK_IF_NO_TSA": "1"})
    def test_pdf_validation_gates_block_no_tsa(self):
        """Test that TSA enforcement blocks when timestamp unavailable."""
        decision = create_test_decision("PASS")
        
        with pytest.raises(PDFValidationError, match="RFC 3161 timestamp required"):
            check_pdf_validation_gates(
                decision, 
                enable_rfc3161=True, 
                timestamp_available=False
            )
    
    @patch.dict(os.environ, {"ENFORCE_PDF_A3": "1", "BLOCK_IF_NO_TSA": "1"})
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False)
    def test_pdf_validation_gates_multiple_blocks(self):
        """Test that multiple validation failures are reported."""
        decision = create_test_decision("PASS")
        
        with pytest.raises(PDFValidationError) as excinfo:
            check_pdf_validation_gates(
                decision, 
                enable_rfc3161=True, 
                timestamp_available=False
            )
        
        error_msg = str(excinfo.value)
        assert "PDF/A-3 compliance required" in error_msg
        assert "RFC 3161 timestamp required" in error_msg


class TestPDFGenerationBlocking:
    """Test PDF generation blocking based on validation gates."""
    
    def test_pdf_generation_without_blocking(self):
        """Test PDF generation succeeds when no blocking conditions."""
        spec = create_test_spec()
        decision = create_test_decision("PASS")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            # Should succeed without error
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                check_validation_gates=True
            )
            
            assert len(pdf_bytes) > 0, "PDF should be generated"
            assert pdf_bytes.startswith(b"%PDF"), "Should be valid PDF"
    
    @patch.dict(os.environ, {"ENFORCE_PDF_A3": "1"})
    @patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False)
    def test_pdf_generation_blocked_pdf_a3(self):
        """Test PDF generation blocked by PDF/A-3 enforcement."""
        spec = create_test_spec()
        decision = create_test_decision("PASS")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            # Should raise PDFValidationError
            with pytest.raises(PDFValidationError, match="PDF/A-3 compliance required"):
                generate_proof_pdf(
                    spec=spec,
                    decision=decision,
                    plot_path=plot_path,
                    check_validation_gates=True
                )
    
    @patch.dict(os.environ, {"BLOCK_IF_NO_TSA": "1"})
    def test_pdf_generation_blocked_no_tsa(self):
        """Test PDF generation blocked by TSA requirement."""
        spec = create_test_spec()
        decision = create_test_decision("PASS")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            # Should raise PDFValidationError
            with pytest.raises(PDFValidationError, match="RFC 3161 timestamp required"):
                generate_proof_pdf(
                    spec=spec,
                    decision=decision,
                    plot_path=plot_path,
                    enable_rfc3161=True,
                    timestamp_provider=lambda: None,  # Force timestamp failure
                    check_validation_gates=True
                )
    
    def test_pdf_generation_bypass_gates(self):
        """Test PDF generation can bypass validation gates when disabled."""
        spec = create_test_spec()
        decision = create_test_decision("PASS")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            # Should succeed even with strict environment
            with patch.dict(os.environ, {"ENFORCE_PDF_A3": "1", "BLOCK_IF_NO_TSA": "1"}):
                with patch('core.render_pdf.PDF_COMPLIANCE_AVAILABLE', False):
                    pdf_bytes = generate_proof_pdf(
                        spec=spec,
                        decision=decision,
                        plot_path=plot_path,
                        check_validation_gates=False  # Bypass gates
                    )
                    
                    assert len(pdf_bytes) > 0, "PDF should be generated when gates bypassed"


class TestINDETERMINATEWatermark:
    """Test INDETERMINATE status watermark and notes."""
    
    def test_indeterminate_pdf_generation(self):
        """Test PDF generation with INDETERMINATE status includes proper notes."""
        spec = create_test_spec()
        decision = create_test_decision("INDETERMINATE")
        decision.reasons = ["Missing required pressure sensor"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                check_validation_gates=False  # Skip gates for this test
            )
            
            assert len(pdf_bytes) > 0, "PDF should be generated for INDETERMINATE"
            # Note: We would need to parse PDF to check for specific text
            # For now, just verify PDF is created
    
    def test_indeterminate_with_missing_sensors_flag(self):
        """Test INDETERMINATE with missing sensors flag generates proper watermark."""
        spec = create_test_spec()
        decision = create_test_decision("INDETERMINATE")
        
        # Mock flags attribute
        class MockFlags:
            missing_required_sensors = ["pressure", "temperature_2"]
            
        decision.flags = MockFlags()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                check_validation_gates=False
            )
            
            assert len(pdf_bytes) > 0, "PDF should be generated for INDETERMINATE with flags"


class TestEnvironmentVariableIntegration:
    """Test integration with environment variables."""
    
    def test_default_environment_allows_pdf(self):
        """Test that default environment allows PDF generation."""
        # Clear any existing environment variables
        env_vars = ["ENFORCE_PDF_A3", "BLOCK_IF_NO_TSA"]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]
        
        spec = create_test_spec()
        decision = create_test_decision("PASS")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            # Should succeed in default environment
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                check_validation_gates=True
            )
            
            assert len(pdf_bytes) > 0, "PDF should be generated in default environment"
    
    @patch.dict(os.environ, {"ENFORCE_PDF_A3": "0", "BLOCK_IF_NO_TSA": "0"})
    def test_explicitly_disabled_gates(self):
        """Test that explicitly disabled gates allow PDF generation."""
        spec = create_test_spec()
        decision = create_test_decision("PASS")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plot_path = create_test_plot(temp_path)
            
            # Should succeed when explicitly disabled
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                check_validation_gates=True
            )
            
            assert len(pdf_bytes) > 0, "PDF should be generated when gates disabled"


def test_integration_with_bundle_verification():
    """Test integration between PDF blocking and bundle verification."""
    spec = create_test_spec()
    decision = create_test_decision("INDETERMINATE")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        plot_path = create_test_plot(temp_path)
        
        # Create mock evidence bundle directory structure
        bundle_dir = temp_path / "bundle"
        bundle_dir.mkdir()
        outputs_dir = bundle_dir / "outputs"
        outputs_dir.mkdir()
        
        # Generate PDF (should succeed without gates)
        pdf_bytes = generate_proof_pdf(
            spec=spec,
            decision=decision,
            plot_path=plot_path,
            check_validation_gates=False
        )
        
        # Save PDF to bundle structure
        pdf_path = outputs_dir / "proof.pdf"
        pdf_path.write_bytes(pdf_bytes)
        
        # Save decision.json
        decision_path = outputs_dir / "decision.json"
        decision_path.write_text('{"pass": false, "status": "INDETERMINATE"}')
        
        # Test bundle verification would detect this scenario
        # (This would be tested in verify_bundle integration tests)
        assert pdf_path.exists(), "PDF should exist in bundle"
        assert decision_path.exists(), "Decision should exist in bundle"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])