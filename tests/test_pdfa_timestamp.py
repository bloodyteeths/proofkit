"""
ProofKit PDF/A-3 Compliance and RFC 3161 Timestamp Tests

Comprehensive test suite for PDF/A-3u compliance and RFC 3161 timestamp verification.
Tests include:
- PDF/A-3u compliance validation
- XMP metadata embedding
- File attachment capabilities
- RFC 3161 timestamp generation and verification
- Tamper-evident features
- Industry-specific compliance requirements

Tests are designed to work with and without external timestamp authorities,
falling back to mock/test implementations when needed.

Example usage:
    pytest tests/test_pdfa_timestamp.py -v
"""

import pytest
import tempfile
import json
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from unittest.mock import patch, MagicMock

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for testing

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from core.models import SpecV1, DecisionResult, Industry
from core.render_pdf import (
    generate_proof_pdf,
    _generate_rfc3161_timestamp,
    _create_xmp_metadata,
    _create_docusign_signature_page,
    PDF_COMPLIANCE_AVAILABLE,
    INDUSTRY_COLORS
)
from core.plot import generate_proof_plot
from core.normalize import normalize_temperature_data
from core.decide import make_decision
from core.verify import verify_rfc3161_timestamp, verify_evidence_bundle


class TestPDFACompliance:
    """Test PDF/A-3u compliance features."""
    
    @pytest.fixture
    def sample_spec(self, example_spec_data) -> SpecV1:
        """Create a sample specification for testing."""
        return SpecV1(**example_spec_data)
    
    @pytest.fixture
    def sample_data(self, simple_temp_data) -> pd.DataFrame:
        """Use simple temperature data for testing."""
        return simple_temp_data
    
    @pytest.fixture
    def sample_decision(self, sample_data, sample_spec) -> DecisionResult:
        """Create a sample decision result."""
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        return make_decision(normalized_df, sample_spec)
    
    @pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab not available")
    def test_pdf_generation_basic(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test basic PDF generation without compliance features."""
        plot_path = temp_dir / "test_plot.png"
        pdf_path = temp_dir / "test_proof.pdf"
        
        # Generate plot first
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        # Generate PDF
        generate_proof_pdf(
            normalized_df, sample_spec, sample_decision, 
            str(plot_path), str(pdf_path)
        )
        
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 5000  # Reasonable PDF size
        
        # Check that PDF contains expected content
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            assert b'PDF' in pdf_content[:10]  # PDF header
            assert sample_spec.job.job_id.encode() in pdf_content
    
    @pytest.mark.skipif(not PDF_COMPLIANCE_AVAILABLE, reason="PDF compliance features not available")
    def test_pdfa3_compliance_features(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test PDF/A-3u compliance features."""
        plot_path = temp_dir / "compliance_plot.png"
        pdf_path = temp_dir / "compliance_proof.pdf"
        
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        # Generate PDF with compliance features enabled
        generate_proof_pdf(
            normalized_df, sample_spec, sample_decision, 
            str(plot_path), str(pdf_path),
            compliance_mode="pdfa3"
        )
        
        assert pdf_path.exists()
        
        # Check for PDF/A-3 compliance markers
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            # Look for XMP metadata markers
            assert b'xmp:' in pdf_content or b'XMP' in pdf_content
            # Look for PDF/A compliance indicators
            assert b'pdfa:' in pdf_content or b'PDF/A' in pdf_content
    
    def test_xmp_metadata_creation(self, sample_spec, sample_decision):
        """Test XMP metadata creation for PDF/A-3."""
        metadata = _create_xmp_metadata(sample_spec, sample_decision)
        
        assert isinstance(metadata, str)
        assert len(metadata) > 100  # Should be substantial
        
        # Parse XML to validate structure
        try:
            root = ET.fromstring(metadata)
            assert root is not None
            # Check for basic XMP structure
            assert 'rdf' in root.tag.lower() or 'xmp' in metadata.lower()
        except ET.ParseError:
            # If not valid XML, should at least contain expected content
            assert sample_spec.job.job_id in metadata
            assert str(sample_decision.pass_).lower() in metadata.lower()
    
    def test_industry_specific_colors(self):
        """Test industry-specific color palettes for compliance."""
        # Test that all supported industries have color definitions
        required_industries = ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]
        
        for industry in required_industries:
            assert industry in INDUSTRY_COLORS
            colors = INDUSTRY_COLORS[industry]
            
            # Each industry should have primary and secondary colors
            assert "primary" in colors
            assert "secondary" in colors
            
            # Colors should be valid hex codes or color names
            assert isinstance(colors["primary"], str)
            assert isinstance(colors["secondary"], str)
            assert len(colors["primary"]) > 0
            assert len(colors["secondary"]) > 0
    
    def test_file_attachment_capability(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test PDF file attachment capabilities for evidence embedding."""
        plot_path = temp_dir / "attachment_plot.png"
        pdf_path = temp_dir / "attachment_proof.pdf"
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        
        # Create files to attach
        sample_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(sample_spec.model_dump(), f, indent=2)
        
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        # Generate PDF with attachments
        attachments = [
            {"path": str(csv_path), "description": "Raw temperature data"},
            {"path": str(spec_path), "description": "Process specification"}
        ]
        
        generate_proof_pdf(
            normalized_df, sample_spec, sample_decision,
            str(plot_path), str(pdf_path),
            attachments=attachments
        )
        
        assert pdf_path.exists()
        
        # Check that PDF is larger (contains attachments)
        base_size = 10000  # Approximate base PDF size
        assert pdf_path.stat().st_size > base_size
    
    def test_docusign_signature_page(self, sample_spec, sample_decision):
        """Test DocuSign signature page generation."""
        signature_content = _create_docusign_signature_page(sample_spec, sample_decision)
        
        assert isinstance(signature_content, str)
        assert len(signature_content) > 100
        
        # Should contain signature-related content
        signature_indicators = ["signature", "sign", "approve", "certify", "validate"]
        assert any(indicator in signature_content.lower() for indicator in signature_indicators)
        
        # Should contain job information
        assert sample_spec.job.job_id in signature_content
        assert str(sample_decision.pass_).lower() in signature_content.lower()


class TestRFC3161Timestamps:
    """Test RFC 3161 timestamp generation and verification."""
    
    @pytest.fixture
    def sample_hash(self) -> str:
        """Generate a sample hash for timestamp testing."""
        return hashlib.sha256(b"test_data_for_timestamp").hexdigest()
    
    def test_timestamp_generation_mock(self, sample_hash):
        """Test timestamp generation with mocked TSA."""
        with patch('core.render_pdf._get_timestamp_from_tsa') as mock_tsa:
            # Mock successful timestamp response
            mock_timestamp_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tsa_url": "http://test-tsa.example.com",
                "serial_number": "123456789",
                "hash_algorithm": "SHA-256",
                "signature": "mock_signature_data"
            }
            mock_tsa.return_value = mock_timestamp_data
            
            timestamp_result = _generate_rfc3161_timestamp(sample_hash)
            
            assert timestamp_result is not None
            assert "timestamp" in timestamp_result
            assert "tsa_url" in timestamp_result
            assert timestamp_result["hash_algorithm"] == "SHA-256"
    
    def test_timestamp_generation_fallback(self, sample_hash):
        """Test timestamp generation with TSA unavailable (fallback mode)."""
        with patch('core.render_pdf._get_timestamp_from_tsa') as mock_tsa:
            # Mock TSA failure
            mock_tsa.side_effect = Exception("TSA unavailable")
            
            # Should fall back to local timestamp
            timestamp_result = _generate_rfc3161_timestamp(sample_hash, fallback=True)
            
            assert timestamp_result is not None
            assert "timestamp" in timestamp_result
            assert "fallback" in timestamp_result
            assert timestamp_result["fallback"] is True
    
    def test_timestamp_verification_valid(self):
        """Test verification of valid RFC 3161 timestamps."""
        # Create a mock valid timestamp
        valid_timestamp = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tsa_url": "http://test-tsa.example.com",
            "serial_number": "123456789",
            "hash_algorithm": "SHA-256",
            "signature": "valid_signature_data",
            "certificate_chain": ["cert1", "cert2"]
        }
        
        with patch('core.verify._verify_timestamp_signature') as mock_verify:
            mock_verify.return_value = True
            
            result = verify_rfc3161_timestamp(valid_timestamp, "test_hash")
            
            assert result["valid"] is True
            assert "verification_time" in result
    
    def test_timestamp_verification_invalid(self):
        """Test verification of invalid RFC 3161 timestamps."""
        # Create a mock invalid timestamp
        invalid_timestamp = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tsa_url": "http://test-tsa.example.com",
            "serial_number": "123456789",
            "hash_algorithm": "SHA-256",
            "signature": "invalid_signature_data"
        }
        
        with patch('core.verify._verify_timestamp_signature') as mock_verify:
            mock_verify.return_value = False
            
            result = verify_rfc3161_timestamp(invalid_timestamp, "test_hash")
            
            assert result["valid"] is False
            assert "error" in result
    
    def test_timestamp_verification_expired(self):
        """Test verification of expired timestamps."""
        # Create timestamp that's too old
        old_timestamp = {
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
            "tsa_url": "http://test-tsa.example.com",
            "serial_number": "123456789",
            "hash_algorithm": "SHA-256",
            "signature": "signature_data"
        }
        
        result = verify_rfc3161_timestamp(old_timestamp, "test_hash", max_age_days=365)
        
        # Depending on implementation, might be valid but with warning
        assert "age_warning" in result or result["valid"] is False
    
    def test_timestamp_hash_mismatch(self):
        """Test timestamp verification with hash mismatch."""
        timestamp = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hash_algorithm": "SHA-256",
            "original_hash": "original_hash_value",
            "signature": "signature_data"
        }
        
        # Verify with different hash
        result = verify_rfc3161_timestamp(timestamp, "different_hash_value")
        
        assert result["valid"] is False
        assert "hash_mismatch" in result.get("error", "").lower()


class TestTamperEvidence:
    """Test tamper-evident features."""
    
    def test_pdf_with_embedded_timestamp(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test PDF generation with embedded RFC 3161 timestamp."""
        plot_path = temp_dir / "timestamp_plot.png"
        pdf_path = temp_dir / "timestamp_proof.pdf"
        
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.return_value = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tsa_url": "http://test-tsa.example.com",
                "hash_algorithm": "SHA-256",
                "signature": "embedded_signature"
            }
            
            generate_proof_pdf(
                normalized_df, sample_spec, sample_decision,
                str(plot_path), str(pdf_path),
                embed_timestamp=True
            )
        
        assert pdf_path.exists()
        
        # Check that timestamp data is embedded
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            assert b'timestamp' in pdf_content or b'rfc3161' in pdf_content
    
    def test_evidence_bundle_with_timestamps(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test evidence bundle creation with timestamps for all files."""
        from core.pack import create_evidence_bundle
        
        plot_path = temp_dir / "bundle_plot.png"
        pdf_path = temp_dir / "bundle_proof.pdf"
        bundle_path = temp_dir / "timestamped_evidence.zip"
        csv_path = temp_dir / "bundle_data.csv"
        
        # Create files
        sample_data.to_csv(csv_path, index=False)
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        generate_proof_pdf(normalized_df, sample_spec, sample_decision, str(plot_path), str(pdf_path))
        
        with patch('core.pack._generate_file_timestamp') as mock_file_timestamp:
            mock_file_timestamp.return_value = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "hash": "file_hash",
                "signature": "file_signature"
            }
            
            create_evidence_bundle(
                csv_path=str(csv_path),
                spec_path=None,
                spec_data=sample_spec.model_dump(),
                decision=sample_decision,
                plot_path=str(plot_path),
                pdf_path=str(pdf_path),
                output_path=str(bundle_path),
                timestamp_files=True
            )
        
        assert bundle_path.exists()
        
        # Verify bundle contains timestamp information
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
        assert "timestamps" in verification_result or verification_result.get("files_timestamped", 0) > 0
    
    def test_tamper_detection(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test detection of tampered evidence bundles."""
        from core.pack import create_evidence_bundle
        import zipfile
        
        plot_path = temp_dir / "tamper_plot.png"
        pdf_path = temp_dir / "tamper_proof.pdf"
        bundle_path = temp_dir / "tamper_evidence.zip"
        csv_path = temp_dir / "tamper_data.csv"
        
        # Create original bundle
        sample_data.to_csv(csv_path, index=False)
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        generate_proof_pdf(normalized_df, sample_spec, sample_decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=sample_spec.model_dump(),
            decision=sample_decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        # Verify original bundle
        original_result = verify_evidence_bundle(str(bundle_path))
        assert original_result["valid"] is True
        
        # Tamper with bundle
        with zipfile.ZipFile(bundle_path, 'a') as zf:
            zf.writestr("malicious_file.txt", "This file was added after creation")
        
        # Verify tampered bundle
        tampered_result = verify_evidence_bundle(str(bundle_path))
        
        # Should detect tampering (exact behavior depends on implementation)
        # At minimum, the hash verification should change
        assert tampered_result.get("files_verified", 0) != original_result.get("files_verified", 0) or \
               tampered_result.get("manifest_hash") != original_result.get("manifest_hash")


class TestComplianceIntegration:
    """Test integration of compliance features with industry requirements."""
    
    @pytest.fixture
    def industry_compliance_specs(self) -> Dict[str, Dict[str, Any]]:
        """Compliance requirements for different industries."""
        return {
            "pharmaceutical": {
                "requires_timestamp": True,
                "requires_signature": True,
                "retention_years": 25,
                "audit_trail": True
            },
            "medical_device": {
                "requires_timestamp": True,
                "requires_signature": True,
                "retention_years": 10,
                "audit_trail": True
            },
            "food_safety": {
                "requires_timestamp": False,
                "requires_signature": False,
                "retention_years": 7,
                "audit_trail": True
            },
            "manufacturing": {
                "requires_timestamp": False,
                "requires_signature": False,
                "retention_years": 5,
                "audit_trail": False
            }
        }
    
    def test_pharmaceutical_compliance(self, sample_data, example_spec_data, temp_dir, industry_compliance_specs):
        """Test compliance features for pharmaceutical industry."""
        # Modify spec for pharmaceutical use
        pharma_spec_data = {**example_spec_data}
        pharma_spec_data["industry"] = "autoclave"
        pharma_spec_data["compliance"] = industry_compliance_specs["pharmaceutical"]
        
        spec = SpecV1(**pharma_spec_data)
        normalized_df, _ = normalize_temperature_data(sample_data, spec)
        decision = make_decision(normalized_df, spec)
        
        plot_path = temp_dir / "pharma_plot.png"
        pdf_path = temp_dir / "pharma_proof.pdf"
        
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        
        # Generate PDF with pharmaceutical compliance
        with patch('core.render_pdf._generate_rfc3161_timestamp') as mock_timestamp:
            mock_timestamp.return_value = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tsa_url": "http://pharmaceutical-tsa.example.com",
                "certificate_authority": "FDA_APPROVED_CA"
            }
            
            generate_proof_pdf(
                normalized_df, spec, decision,
                str(plot_path), str(pdf_path),
                compliance_mode="pharmaceutical"
            )
        
        assert pdf_path.exists()
        
        # Check for pharmaceutical compliance markers
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            # Should contain FDA or pharmaceutical compliance references
            compliance_indicators = [b'fda', b'cfr', b'pharmaceutical', b'gmp']
            assert any(indicator in pdf_content.lower() for indicator in compliance_indicators)
    
    def test_medical_device_compliance(self, sample_data, example_spec_data, temp_dir, industry_compliance_specs):
        """Test compliance features for medical device industry."""
        medical_spec_data = {**example_spec_data}
        medical_spec_data["industry"] = "sterile"
        medical_spec_data["compliance"] = industry_compliance_specs["medical_device"]
        
        spec = SpecV1(**medical_spec_data)
        normalized_df, _ = normalize_temperature_data(sample_data, spec)
        decision = make_decision(normalized_df, spec)
        
        plot_path = temp_dir / "medical_plot.png"
        pdf_path = temp_dir / "medical_proof.pdf"
        
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(
            normalized_df, spec, decision,
            str(plot_path), str(pdf_path),
            compliance_mode="medical_device"
        )
        
        assert pdf_path.exists()
        
        # Check for medical device compliance
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            medical_indicators = [b'iso', b'13485', b'medical', b'device']
            assert any(indicator in pdf_content.lower() for indicator in medical_indicators)
    
    def test_audit_trail_generation(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test audit trail generation for compliance."""
        audit_trail = {
            "actions": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "data_uploaded",
                    "user": "operator@example.com",
                    "details": "CSV file uploaded with 25 data points"
                },
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "decision_made",
                    "user": "system",
                    "details": f"Automated decision: {'PASS' if sample_decision.pass_ else 'FAIL'}"
                },
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "pdf_generated",
                    "user": "system",
                    "details": "Compliance PDF generated with embedded timestamp"
                }
            ]
        }
        
        plot_path = temp_dir / "audit_plot.png"
        pdf_path = temp_dir / "audit_proof.pdf"
        
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        generate_proof_pdf(
            normalized_df, sample_spec, sample_decision,
            str(plot_path), str(pdf_path),
            audit_trail=audit_trail
        )
        
        assert pdf_path.exists()
        
        # Check that audit trail is embedded
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            assert b'audit' in pdf_content.lower() or b'trail' in pdf_content.lower()
            assert b'operator@example.com' in pdf_content


class TestComplianceEdgeCases:
    """Test edge cases and error conditions for compliance features."""
    
    def test_timestamp_service_unavailable(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test behavior when timestamp service is unavailable."""
        plot_path = temp_dir / "no_tsa_plot.png"
        pdf_path = temp_dir / "no_tsa_proof.pdf"
        
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        with patch('core.render_pdf._get_timestamp_from_tsa') as mock_tsa:
            mock_tsa.side_effect = Exception("Timestamp Authority unavailable")
            
            # Should still generate PDF (with fallback timestamp or warning)
            generate_proof_pdf(
                normalized_df, sample_spec, sample_decision,
                str(plot_path), str(pdf_path),
                embed_timestamp=True,
                timestamp_fallback=True
            )
        
        assert pdf_path.exists()
        
        # Should contain fallback timestamp or warning
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
            warning_indicators = [b'fallback', b'warning', b'unavailable', b'offline']
            assert any(indicator in pdf_content.lower() for indicator in warning_indicators)
    
    def test_malformed_compliance_config(self, sample_data, sample_spec, sample_decision, temp_dir):
        """Test handling of malformed compliance configuration."""
        plot_path = temp_dir / "malformed_plot.png"
        pdf_path = temp_dir / "malformed_proof.pdf"
        
        normalized_df, _ = normalize_temperature_data(sample_data, sample_spec)
        generate_proof_plot(normalized_df, sample_spec, sample_decision, str(plot_path))
        
        # Try to generate PDF with invalid compliance mode
        try:
            generate_proof_pdf(
                normalized_df, sample_spec, sample_decision,
                str(plot_path), str(pdf_path),
                compliance_mode="invalid_mode"
            )
            # Should still generate PDF (falling back to default)
            assert pdf_path.exists()
        except ValueError as e:
            # Or should raise clear error about invalid compliance mode
            assert "compliance" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_large_file_timestamp_performance(self, temp_dir):
        """Test timestamp generation performance with large files."""
        # Create a large mock file
        large_file_path = temp_dir / "large_file.txt"
        with open(large_file_path, 'w') as f:
            f.write("x" * (1024 * 1024))  # 1MB file
        
        # Calculate hash
        with open(large_file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Time the timestamp generation
        import time
        start_time = time.time()
        
        with patch('core.render_pdf._get_timestamp_from_tsa') as mock_tsa:
            mock_tsa.return_value = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "hash": file_hash
            }
            
            timestamp_result = _generate_rfc3161_timestamp(file_hash)
        
        end_time = time.time()
        
        # Should complete in reasonable time (< 5 seconds for mock)
        assert end_time - start_time < 5.0
        assert timestamp_result is not None