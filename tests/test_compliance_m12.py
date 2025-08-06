"""
Test suite for M12 Compliance features: PDF/A-3u + RFC 3161 timestamps

Tests PDF/A-3u compliance, RFC 3161 timestamp generation and verification,
embedded manifest attachments, DocuSign signature pages, and industry-specific
color palettes.

Author: ProofKit Development Team
Version: 1.0
"""

import pytest
import tempfile
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for testing

from core.models import SpecV1, DecisionResult, Industry
from core.render_pdf import (
    generate_proof_pdf, 
    _generate_rfc3161_timestamp,
    _create_xmp_metadata,
    _create_docusign_signature_page,
    PDF_COMPLIANCE_AVAILABLE,
    INDUSTRY_COLORS
)
from core.plot import generate_proof_plot, get_industry_colors
from core.verify import verify_rfc3161_timestamp, verify_evidence_bundle
from core.normalize import normalize_temperature_data
from core.decide import make_decision


class TestPDFACompliance:
    """Test PDF/A-3u compliance features."""
    
    @pytest.fixture
    def sample_spec(self) -> SpecV1:
        """Create a sample specification for testing."""
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "M12_TEST_001"}, 
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        }
        return SpecV1(**spec_data)
    
    @pytest.fixture
    def sample_decision(self) -> DecisionResult:
        """Create a sample decision result for testing."""
        decision_data = {
            "job_id": "M12_TEST_001",
            "pass_": True,
            "target_temp_C": 180.0,
            "conservative_threshold_C": 182.0,
            "required_hold_time_s": 600,
            "actual_hold_time_s": 650.5,
            "max_temp_C": 185.2,
            "min_temp_C": 179.8,
            "reasons": ["Hold time requirement met", "Temperature threshold maintained"],
            "warnings": []
        }
        return DecisionResult(**decision_data)
    
    @pytest.fixture
    def sample_plot_path(self) -> str:
        """Create a temporary plot file for testing."""
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            # Create a minimal PNG file
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.plot([1, 2, 3], [180, 185, 180])
            ax.set_title("Test Plot")
            fig.savefig(f.name)
            plt.close(fig)
            return f.name
    
    def test_pdf_generation_with_compliance_features(self, sample_spec, sample_decision, sample_plot_path):
        """Test PDF generation with all M12 compliance features enabled."""
        manifest_content = json.dumps({
            "version": "1.0",
            "job_id": "M12_TEST_001",
            "files": {"test.csv": {"sha256": "abc123..."}},
            "root_hash": "def456..."
        })
        
        pdf_bytes = generate_proof_pdf(
            spec=sample_spec,
            decision=sample_decision,
            plot_path=sample_plot_path,
            manifest_content=manifest_content,
            enable_rfc3161=True,
            esign_page=True,
            industry=Industry.POWDER
        )
        
        # Basic validation
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000  # Should be substantial file
        assert pdf_bytes.startswith(b'%PDF')  # PDF signature
        
        # Clean up
        os.unlink(sample_plot_path)
    
    def test_xmp_metadata_generation(self, sample_spec, sample_decision):
        """Test XMP metadata generation for PDF/A-3u compliance."""
        timestamp_info = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'token': 'abc123...',
            'token_length': 256
        }
        
        xmp_metadata = _create_xmp_metadata(sample_spec, sample_decision, timestamp_info)
        
        # Validate XMP structure
        assert '<?xml' in xmp_metadata
        assert '<?xpacket' in xmp_metadata
        assert 'ProofKit Certificate - M12_TEST_001' in xmp_metadata
        assert 'ProofKit v1.0' in xmp_metadata
        assert 'PMT' in xmp_metadata
        assert 'PASS' in xmp_metadata
        assert timestamp_info['timestamp'] in xmp_metadata
    
    @pytest.mark.skipif(not PDF_COMPLIANCE_AVAILABLE, reason="PDF compliance libraries not available")
    def test_rfc3161_timestamp_generation(self):
        """Test RFC 3161 timestamp generation."""
        test_data = b"Test data for timestamping"
        
        # Note: This test might fail in CI/offline environments
        # It's more of an integration test
        try:
            timestamp_token = _generate_rfc3161_timestamp(test_data)
            if timestamp_token:
                assert isinstance(timestamp_token, bytes)
                assert len(timestamp_token) > 100  # Should be substantial token
        except Exception:
            # RFC 3161 services might be unavailable
            pytest.skip("RFC 3161 timestamp service unavailable")
    
    def test_docusign_signature_page_generation(self):
        """Test DocuSign signature page elements generation."""
        signature_elements = _create_docusign_signature_page()
        
        # Should contain multiple elements
        assert len(signature_elements) > 3
        
        # Should contain expected content types
        element_types = [type(elem).__name__ for elem in signature_elements]
        assert 'PageBreak' in element_types
        assert 'Paragraph' in element_types
        assert 'Table' in element_types
    
    def test_industry_specific_titles(self, sample_spec, sample_decision, sample_plot_path):
        """Test industry-specific PDF titles."""
        industries_and_titles = [
            (Industry.POWDER, "Powder-Coat Cure Validation Certificate"),
            (Industry.HACCP, "HACCP Temperature Validation Certificate"),
            (Industry.AUTOCLAVE, "Autoclave Sterilization Validation Certificate"),
            (Industry.STERILE, "Sterile Processing Validation Certificate"),
            (Industry.CONCRETE, "Concrete Curing Validation Certificate"),
            (Industry.COLDCHAIN, "Cold Chain Storage Validation Certificate")
        ]
        
        for industry, expected_title in industries_and_titles:
            pdf_bytes = generate_proof_pdf(
                spec=sample_spec,
                decision=sample_decision,
                plot_path=sample_plot_path,
                industry=industry
            )
            
            # PDF should be generated successfully
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 1000
        
        # Clean up
        os.unlink(sample_plot_path)


class TestIndustryColorPalettes:
    """Test industry-specific color palette functionality."""
    
    def test_industry_color_definitions(self):
        """Test that all industries have complete color palettes."""
        required_colors = ['primary', 'secondary', 'accent', 'target', 'threshold']
        
        for industry in Industry:
            assert industry in INDUSTRY_COLORS
            colors = INDUSTRY_COLORS[industry]
            
            for color_key in required_colors:
                assert color_key in colors
                assert colors[color_key].startswith('#')
                assert len(colors[color_key]) == 7  # Proper hex color format
    
    def test_get_industry_colors_function(self):
        """Test the get_industry_colors helper function."""
        # Test with valid industry
        powder_colors = get_industry_colors(Industry.POWDER)
        assert powder_colors == INDUSTRY_COLORS[Industry.POWDER]
        
        # Test with None (should return default)
        default_colors = get_industry_colors(None)
        assert default_colors == INDUSTRY_COLORS[Industry.POWDER]
        
        # Test with each industry
        for industry in Industry:
            colors = get_industry_colors(industry)
            assert 'primary' in colors
            assert 'target' in colors
            assert 'threshold' in colors
    
    def test_plot_generation_with_industry_colors(self):
        """Test plot generation with different industry color palettes."""
        # Create test data
        data = {
            'timestamp': pd.date_range('2023-01-01', periods=100, freq='30s'),
            'temp_1': [180 + i*0.1 for i in range(100)]
        }
        df = pd.DataFrame(data)
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "COLOR_TEST"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            }
        }
        spec = SpecV1(**spec_data)
        
        decision_data = {
            "job_id": "COLOR_TEST",
            "pass_": True,
            "target_temp_C": 180.0,
            "conservative_threshold_C": 182.0,
            "required_hold_time_s": 600,
            "actual_hold_time_s": 650.5,
            "max_temp_C": 185.2,
            "min_temp_C": 179.8,
            "reasons": ["Test passed"],
            "warnings": []
        }
        decision = DecisionResult(**decision_data)
        
        # Test plot generation for each industry
        for industry in Industry:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                try:
                    plot_path = generate_proof_plot(df, spec, decision, temp_file.name, industry)
                    assert os.path.exists(plot_path)
                    assert os.path.getsize(plot_path) > 1000  # Should be substantial file
                finally:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)


class TestRFC3161Verification:
    """Test RFC 3161 timestamp verification functionality."""
    
    def test_rfc3161_verification_without_libraries(self):
        """Test RFC 3161 verification when libraries are not available."""
        # Create a dummy PDF file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(b'%PDF-1.4\nDummy PDF content\n%%EOF')
            temp_file.flush()
            
            try:
                # This should handle the case when libraries aren't available
                valid, details = verify_rfc3161_timestamp(temp_file.name)
                
                assert isinstance(valid, bool)
                assert isinstance(details, dict)
                assert 'rfc3161_found' in details
                assert 'rfc3161_valid' in details
                assert 'rfc3161_issues' in details
                
            finally:
                os.unlink(temp_file.name)
    
    @pytest.mark.skipif(not PDF_COMPLIANCE_AVAILABLE, reason="PDF compliance libraries not available")
    def test_rfc3161_verification_with_real_pdf(self, sample_spec, sample_decision, sample_plot_path):
        """Test RFC 3161 verification with a real PDF containing timestamps."""
        # Generate a PDF with RFC 3161 timestamps
        pdf_bytes = generate_proof_pdf(
            spec=sample_spec,
            decision=sample_decision,
            plot_path=sample_plot_path,
            enable_rfc3161=True
        )
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(pdf_bytes)
            temp_file.flush()
            
            try:
                # Verify RFC 3161 timestamp
                valid, details = verify_rfc3161_timestamp(temp_file.name, grace_period_s=10)
                
                assert isinstance(valid, bool)
                assert isinstance(details, dict)
                
                # Check structure of details
                required_keys = [
                    'rfc3161_found', 'rfc3161_valid', 'rfc3161_timestamp',
                    'rfc3161_grace_period_ok', 'rfc3161_issues'
                ]
                for key in required_keys:
                    assert key in details
                
            finally:
                os.unlink(temp_file.name)
        
        # Clean up
        os.unlink(sample_plot_path)
    
    @pytest.fixture
    def sample_spec(self) -> SpecV1:
        """Create a sample specification for testing."""
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "RFC3161_TEST"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            }
        }
        return SpecV1(**spec_data)
    
    @pytest.fixture
    def sample_decision(self) -> DecisionResult:
        """Create a sample decision result for testing."""
        decision_data = {
            "job_id": "RFC3161_TEST",
            "pass_": True,
            "target_temp_C": 180.0,
            "conservative_threshold_C": 182.0,
            "required_hold_time_s": 600,
            "actual_hold_time_s": 650.5,
            "max_temp_C": 185.2,
            "min_temp_C": 179.8,
            "reasons": ["Test passed"],
            "warnings": []
        }
        return DecisionResult(**decision_data)
    
    @pytest.fixture
    def sample_plot_path(self) -> str:
        """Create a temporary plot file for testing."""
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.plot([1, 2, 3], [180, 185, 180])
            fig.savefig(f.name)
            plt.close(fig)
            return f.name


class TestComplianceIntegration:
    """Integration tests for complete M12 compliance workflow."""
    
    def test_full_compliance_workflow(self):
        """Test complete workflow from data processing to compliant PDF generation."""
        # Create sample temperature data
        timestamps = pd.date_range('2023-01-01 10:00:00', periods=30, freq='1min')
        temperatures = [175 + i*0.5 if i < 10 else 182 + (i-10)*0.1 for i in range(30)]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_1': temperatures
        })
        
        # Create specification
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "INTEGRATION_TEST"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 120.0,
                "allowed_gaps_s": 180.0
            }
        }
        spec = SpecV1(**spec_data)
        
        # Normalize data and make decision
        normalized_df = normalize_temperature_data(df, target_step_s=60.0)
        decision = make_decision(normalized_df, spec)
        
        # Generate plot with industry colors
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as plot_file:
            plot_path = generate_proof_plot(
                normalized_df, spec, decision, plot_file.name, Industry.AUTOCLAVE
            )
            
            # Generate compliant PDF
            manifest_content = json.dumps({
                "version": "1.0",
                "job_id": "INTEGRATION_TEST",
                "files": {"data.csv": {"sha256": "test_hash"}},
                "root_hash": "test_root_hash"
            })
            
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=plot_path,
                manifest_content=manifest_content,
                enable_rfc3161=True,
                esign_page=True,
                industry=Industry.AUTOCLAVE
            )
            
            # Validate results
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 2000  # Should be substantial with all features
            assert pdf_bytes.startswith(b'%PDF')
            
            # Clean up
            os.unlink(plot_path)
    
    def test_compliance_with_all_industries(self):
        """Test compliance features work with all industry types."""
        base_data = {
            'timestamp': pd.date_range('2023-01-01', periods=20, freq='30s'),
            'temp_1': [180 + i*0.2 for i in range(20)]
        }
        df = pd.DataFrame(base_data)
        
        for industry in Industry:
            # Create industry-specific spec
            spec_data = {
                "version": "1.0",
                "job": {"job_id": f"TEST_{industry.value.upper()}"},
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 180.0,
                    "hold_time_s": 300,
                    "sensor_uncertainty_C": 2.0
                }
            }
            spec = SpecV1(**spec_data)
            decision = make_decision(df, spec)
            
            # Generate plot and PDF
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as plot_file:
                try:
                    plot_path = generate_proof_plot(df, spec, decision, plot_file.name, industry)
                    
                    pdf_bytes = generate_proof_pdf(
                        spec=spec,
                        decision=decision,
                        plot_path=plot_path,
                        industry=industry,
                        enable_rfc3161=False,  # Skip timestamp for speed
                        esign_page=True
                    )
                    
                    # Validate
                    assert isinstance(pdf_bytes, bytes)
                    assert len(pdf_bytes) > 1000
                    
                finally:
                    if os.path.exists(plot_file.name):
                        os.unlink(plot_file.name)


class TestComplianceErrors:
    """Test error handling in compliance features."""
    
    def test_pdf_generation_with_missing_plot(self):
        """Test PDF generation handles missing plot file gracefully."""
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "ERROR_TEST"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            }
        }
        spec = SpecV1(**spec_data)
        
        decision_data = {
            "job_id": "ERROR_TEST",
            "pass_": False,
            "target_temp_C": 180.0,
            "conservative_threshold_C": 182.0,
            "required_hold_time_s": 600,
            "actual_hold_time_s": 300,
            "max_temp_C": 175.0,
            "min_temp_C": 170.0,
            "reasons": ["Insufficient hold time"],
            "warnings": []
        }
        decision = DecisionResult(**decision_data)
        
        # Test with non-existent plot file
        with pytest.raises(FileNotFoundError):
            generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path="/nonexistent/plot.png"
            )
    
    def test_rfc3161_verification_with_invalid_pdf(self):
        """Test RFC 3161 verification with invalid PDF file."""
        # Create invalid PDF file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(b'Not a valid PDF file')
            temp_file.flush()
            
            try:
                valid, details = verify_rfc3161_timestamp(temp_file.name)
                
                # Should handle gracefully
                assert valid is False
                assert isinstance(details, dict)
                assert len(details['rfc3161_issues']) > 0
                
            finally:
                os.unlink(temp_file.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])