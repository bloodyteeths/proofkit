"""
PDF Smoke Tests

Simple smoke tests for PDF generation to verify basic functionality
across all status types (PASS, FAIL, INDETERMINATE) with minimal setup.

Tests:
- Basic PDF generation for PASS status
- Basic PDF generation for FAIL status
- Basic PDF generation for INDETERMINATE status
- Auto-detected sensors handling (fallback_used flag)

Example usage:
    pytest tests/test_pdf_smoke.py -v
"""

import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timezone

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for testing
import matplotlib.pyplot as plt

from core.models import SpecV1, DecisionResult, JobInfo, CureSpec, CureMethod
from core.render_pdf import generate_proof_pdf
from core.render_certificate import generate_certificate_pdf


def create_simple_plot() -> Path:
    """Create a minimal test plot."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2, 3, 4], [180, 182, 181, 183])
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature (°C)")
    
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()
    
    return Path(temp_file.name)


def create_test_spec() -> SpecV1:
    """Create minimal test specification."""
    return SpecV1(
        version="1.0",
        industry="powder",
        job=JobInfo(job_id="smoke_test_001"),
        spec=CureSpec(
            method=CureMethod.PMT,
            target_temp_C=180.0,
            hold_time_s=600,
            sensor_uncertainty_C=2.0
        )
    )


def create_pass_decision() -> DecisionResult:
    """Create PASS decision result."""
    return DecisionResult(
        pass_=True,
        status="PASS",
        job_id="smoke_test_001",
        target_temp_C=180.0,
        conservative_threshold_C=182.0,
        actual_hold_time_s=650.0,
        required_hold_time_s=600,
        max_temp_C=185.0,
        min_temp_C=178.0,
        reasons=["Temperature maintained above threshold for required duration"],
        warnings=[],
        flags={}
    )


def create_fail_decision() -> DecisionResult:
    """Create FAIL decision result."""
    return DecisionResult(
        pass_=False,
        status="FAIL",
        job_id="smoke_test_001",
        target_temp_C=180.0,
        conservative_threshold_C=182.0,
        actual_hold_time_s=300.0,
        required_hold_time_s=600,
        max_temp_C=183.0,
        min_temp_C=175.0,
        reasons=["Insufficient hold time: 300s < 600s required"],
        warnings=["Temperature briefly dropped below threshold"],
        flags={}
    )


def create_indeterminate_decision() -> DecisionResult:
    """Create INDETERMINATE decision result."""
    return DecisionResult(
        pass_=False,
        status="INDETERMINATE",
        job_id="smoke_test_001", 
        target_temp_C=180.0,
        conservative_threshold_C=182.0,
        actual_hold_time_s=0.0,
        required_hold_time_s=600,
        max_temp_C=175.0,
        min_temp_C=170.0,
        reasons=["Required sensors missing: pressure data not found"],
        warnings=["Data quality insufficient for validation"],
        flags={
            "fallback_used": True,
            "required_sensors": ["temperature", "pressure"],
            "present_sensors": ["temperature"]
        }
    )


class TestPDFSmoke:
    """Smoke tests for PDF generation."""
    
    def test_pass_pdf_generation(self):
        """Test basic PDF generation for PASS status."""
        spec = create_test_spec()
        decision = create_pass_decision()
        plot_path = create_simple_plot()
        
        try:
            # Test main PDF renderer
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_pass",
                user_plan="free"
            )
            
            assert len(pdf_bytes) > 1000, "PDF should not be empty"
            assert pdf_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
            # Test certificate renderer
            cert_bytes = generate_certificate_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_pass_cert"
            )
            
            assert len(cert_bytes) > 1000, "Certificate PDF should not be empty"
            assert cert_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
        finally:
            plot_path.unlink(missing_ok=True)
    
    def test_fail_pdf_generation(self):
        """Test basic PDF generation for FAIL status."""
        spec = create_test_spec()
        decision = create_fail_decision()
        plot_path = create_simple_plot()
        
        try:
            # Test main PDF renderer
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_fail",
                user_plan="free"
            )
            
            assert len(pdf_bytes) > 1000, "PDF should not be empty"
            assert pdf_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
            # Test certificate renderer
            cert_bytes = generate_certificate_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_fail_cert"
            )
            
            assert len(cert_bytes) > 1000, "Certificate PDF should not be empty"
            assert cert_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
        finally:
            plot_path.unlink(missing_ok=True)
    
    def test_indeterminate_pdf_generation(self):
        """Test basic PDF generation for INDETERMINATE status."""
        spec = create_test_spec()
        decision = create_indeterminate_decision()
        plot_path = create_simple_plot()
        
        try:
            # Test main PDF renderer
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_indeterminate",
                user_plan="free"
            )
            
            assert len(pdf_bytes) > 1000, "PDF should not be empty"
            assert pdf_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
            # Test certificate renderer
            cert_bytes = generate_certificate_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_indeterminate_cert"
            )
            
            assert len(cert_bytes) > 1000, "Certificate PDF should not be empty"
            assert cert_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
        finally:
            plot_path.unlink(missing_ok=True)
    
    def test_fallback_sensors_pdf_generation(self):
        """Test PDF generation with fallback_used flag."""
        spec = create_test_spec()
        decision = create_indeterminate_decision()  # Already has fallback_used: True
        plot_path = create_simple_plot()
        
        try:
            # Test main PDF renderer with fallback flag
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_fallback",
                user_plan="pro"  # Test different plan
            )
            
            assert len(pdf_bytes) > 1000, "PDF should not be empty"
            assert pdf_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
            # Test certificate renderer with fallback flag
            cert_bytes = generate_certificate_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_fallback_cert"
            )
            
            assert len(cert_bytes) > 1000, "Certificate PDF should not be empty"
            assert cert_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
        finally:
            plot_path.unlink(missing_ok=True)
    
    def test_pdf_generation_missing_fields(self):
        """Test PDF generation with None/missing fields."""
        spec = create_test_spec()
        
        # Create decision with minimal data (some fields might be None)
        decision = DecisionResult(
            pass_=True,
            status="PASS",
            job_id="smoke_test_minimal",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=600.0,
            required_hold_time_s=600,
            max_temp_C=185.0,
            min_temp_C=175.0,
            reasons=[],  # Empty reasons
            warnings=[],  # Empty warnings
            flags={}  # Empty flags
        )
        
        plot_path = create_simple_plot()
        
        try:
            # Should handle missing/empty fields gracefully
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_minimal",
                user_plan="starter"
            )
            
            assert len(pdf_bytes) > 1000, "PDF should not be empty"
            assert pdf_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
            # Test certificate renderer with minimal data
            cert_bytes = generate_certificate_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                verification_hash="test_hash_minimal_cert"
            )
            
            assert len(cert_bytes) > 1000, "Certificate PDF should not be empty"
            assert cert_bytes.startswith(b'%PDF'), "Should be valid PDF format"
            
        finally:
            plot_path.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])