"""
ProofKit Evidence Bundle Verification Tests

Comprehensive test suite for core.verify module to ensure ≥85% test coverage.
Tests bundle integrity verification, decision re-computation, tamper detection,
RFC 3161 timestamp verification, and error handling.

Key testing features:
- Uses test fixtures for deterministic evidence bundles
- Tests successful verification workflows
- Tests various failure scenarios (tampering, missing files, etc.)
- Tests RFC 3161 timestamp verification with mocked dependencies
- Comprehensive edge case coverage
"""

import pytest
import json
import tempfile
import zipfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, mock_open
import pandas as pd
import hashlib
import os

from core.verify import (
    verify_evidence_bundle,
    verify_bundle_quick,
    VerificationReport,
    VerificationError,
    extract_bundle_to_temp,
    verify_bundle_integrity,
    recompute_decision,
    compare_decisions,
    verify_rfc3161_timestamp,
    verify_proof_pdf,
    calculate_manifest_hash,
    verify_decision_consistency,
    RFC3161_VERIFICATION_AVAILABLE
)
from core.models import SpecV1, DecisionResult
from core.pack import create_evidence_bundle
from tests.helpers import (
    load_csv_fixture,
    load_spec_fixture,
    load_spec_fixture_validated,
    compute_sha256_file,
    create_minimal_zip
)


class TestVerificationReport:
    """Test VerificationReport class functionality."""
    
    def test_verification_report_initialization(self):
        """Test report initializes with correct defaults."""
        report = VerificationReport()
        
        assert report.bundle_path is None
        assert report.bundle_exists == False
        assert report.manifest_found == False
        assert report.root_hash is None
        assert report.is_valid == False
        assert len(report.issues) == 0
        assert len(report.warnings) == 0
        assert report.files_total == 0
        assert report.files_verified == 0
    
    def test_verification_report_add_issue(self):
        """Test adding issues and warnings to report."""
        report = VerificationReport()
        
        # Add regular issue
        report.add_issue("Test issue 1")
        assert len(report.issues) == 1
        assert "Test issue 1" in report.issues
        assert len(report.warnings) == 0
        
        # Add warning
        report.add_issue("Test warning 1", is_warning=True)
        assert len(report.issues) == 1
        assert len(report.warnings) == 1
        assert "Test warning 1" in report.warnings
    
    def test_verification_report_finalize_valid(self):
        """Test finalize with valid bundle."""
        report = VerificationReport()
        
        # Set up valid state
        report.bundle_exists = True
        report.manifest_found = True
        report.manifest_valid = True
        report.root_hash = "abc123" * 10  # 60 chars
        report.root_hash_valid = True
        report.files_total = 5
        report.files_verified = 5
        report.decision_recomputed = True
        report.decision_matches = True
        
        report.finalize()
        assert report.is_valid == True
    
    def test_verification_report_finalize_invalid(self):
        """Test finalize with various invalid states."""
        # Test missing manifest
        report = VerificationReport()
        report.bundle_exists = True
        report.manifest_found = False
        report.finalize()
        assert report.is_valid == False
        
        # Test hash mismatch
        report = VerificationReport()
        report.bundle_exists = True
        report.manifest_found = True
        report.manifest_valid = True
        report.root_hash_valid = False
        report.finalize()
        assert report.is_valid == False
        
        # Test file count mismatch
        report = VerificationReport()
        report.bundle_exists = True
        report.manifest_found = True
        report.manifest_valid = True
        report.root_hash_valid = True
        report.files_total = 5
        report.files_verified = 3
        report.finalize()
        assert report.is_valid == False
    
    def test_verification_report_generate_summary(self):
        """Test summary generation for different states."""
        # Valid report
        report = VerificationReport()
        report.is_valid = True
        report.root_hash = "abc123def456" * 5
        summary = report.generate_summary()
        assert "PASSED" in summary
        assert "abc123def456" in summary
        
        # Invalid report
        report = VerificationReport()
        report.is_valid = False
        report.issues = ["Issue 1", "Issue 2"]
        report.warnings = ["Warning 1"]
        summary = report.generate_summary()
        assert "FAILED" in summary
        assert "2 issues" in summary
        assert "1 warnings" in summary
    
    def test_verification_report_to_dict(self):
        """Test converting report to dictionary."""
        report = VerificationReport()
        report.bundle_path = "/test/evidence.zip"
        report.is_valid = True
        report.root_hash = "test_hash"
        report.issues = ["Test issue"]
        report.warnings = ["Test warning"]
        
        result_dict = report.to_dict()
        
        assert result_dict["bundle_path"] == "/test/evidence.zip"
        assert result_dict["is_valid"] == True
        assert result_dict["bundle_integrity"]["root_hash"] == "test_hash"
        assert "Test issue" in result_dict["issues"]
        assert "Test warning" in result_dict["warnings"]
        assert "verification_metadata" in result_dict
    
    def test_verification_report_str_representation(self):
        """Test string representation of report."""
        report = VerificationReport()
        report.bundle_path = "/test/evidence.zip"
        report.is_valid = False
        report.root_hash = "abc123" * 10
        report.files_verified = 3
        report.files_total = 5
        report.issues = ["Missing files", "Hash mismatch"]
        
        str_repr = str(report)
        
        assert "ProofKit Evidence Bundle Verification Report" in str_repr
        assert "Bundle: /test/evidence.zip" in str_repr
        assert "Status: INVALID" in str_repr
        assert "Files Verified: 3/5" in str_repr
        assert "Missing files" in str_repr
        assert "Hash mismatch" in str_repr


class TestBundleExtraction:
    """Test bundle extraction functionality."""
    
    def test_extract_bundle_to_temp_success(self):
        """Test successful bundle extraction."""
        # Create a test bundle
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            bundle_path = tmp.name
            
        try:
            # Create test ZIP
            with zipfile.ZipFile(bundle_path, 'w') as zf:
                zf.writestr("manifest.json", '{"version": "1.0"}')
                zf.writestr("inputs/data.csv", "timestamp,temp_C\n2024-01-01,170.0")
                zf.writestr("outputs/proof.pdf", b"PDF content")
            
            # Extract bundle
            temp_dir, extracted_files = extract_bundle_to_temp(bundle_path)
            
            assert Path(temp_dir).exists()
            assert "manifest.json" in extracted_files
            assert "inputs/data.csv" in extracted_files
            assert "outputs/proof.pdf" in extracted_files
            
            # Check extracted content
            manifest_path = Path(extracted_files["manifest.json"])
            assert manifest_path.exists()
            with open(manifest_path, 'r') as f:
                data = json.load(f)
                assert data["version"] == "1.0"
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
        finally:
            os.unlink(bundle_path)
    
    def test_extract_bundle_not_found(self):
        """Test extraction with non-existent bundle."""
        with pytest.raises(VerificationError, match="Evidence bundle not found"):
            extract_bundle_to_temp("/nonexistent/bundle.zip")
    
    def test_extract_bundle_corrupted(self):
        """Test extraction with corrupted ZIP."""
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            bundle_path = tmp.name
            # Write invalid ZIP data
            tmp.write(b"This is not a valid ZIP file")
        
        try:
            with pytest.raises(VerificationError, match="Evidence bundle extraction failed"):
                extract_bundle_to_temp(bundle_path)
        finally:
            os.unlink(bundle_path)
    
    def test_extract_bundle_path_traversal(self):
        """Test extraction prevents path traversal attacks."""
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            bundle_path = tmp.name
        
        try:
            # Create ZIP with path traversal attempt
            with zipfile.ZipFile(bundle_path, 'w') as zf:
                # Try to write outside extraction directory
                zf.writestr("../../../etc/passwd", "malicious content")
            
            with pytest.raises(VerificationError, match="Unsafe archive path"):
                extract_bundle_to_temp(bundle_path)
                
        finally:
            os.unlink(bundle_path)


class TestBundleIntegrity:
    """Test bundle integrity verification."""
    
    def test_verify_bundle_integrity_valid(self):
        """Test integrity verification with valid bundle."""
        # Create extracted files structure
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create manifest
            manifest = {
                "version": "1.0",
                "created_at": "2024-01-01T00:00:00Z",
                "metadata": {"job_id": "test"},
                "files": {
                    "inputs/data.csv": {
                        "sha256": hashlib.sha256(b"csv_content").hexdigest(),
                        "size_bytes": 11
                    },
                    "outputs/proof.pdf": {
                        "sha256": hashlib.sha256(b"pdf_content").hexdigest(),
                        "size_bytes": 11
                    }
                },
                "root_hash": ""  # Will calculate
            }
            
            # Calculate root hash
            file_hashes = [
                manifest["files"]["inputs/data.csv"]["sha256"],
                manifest["files"]["outputs/proof.pdf"]["sha256"]
            ]
            root_hash = hashlib.sha256("".join(file_hashes).encode()).hexdigest()
            manifest["root_hash"] = root_hash
            
            # Write manifest
            manifest_path = temp_path / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f)
            
            # Write data files
            data_path = temp_path / "inputs" / "data.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_bytes(b"csv_content")
            
            pdf_path = temp_path / "outputs" / "proof.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"pdf_content")
            
            # Create extracted files mapping
            extracted_files = {
                "manifest.json": str(manifest_path),
                "inputs/data.csv": str(data_path),
                "outputs/proof.pdf": str(pdf_path)
            }
            
            # Verify integrity
            valid, details = verify_bundle_integrity("test.zip", extracted_files)
            
            assert valid == True
            assert details["manifest_found"] == True
            assert details["manifest_valid"] == True
            assert details["root_hash"] == root_hash
            assert details["root_hash_valid"] == True
            assert details["files_total"] == 2
            assert details["files_verified"] == 2
            assert len(details["missing_files"]) == 0
            assert len(details["hash_mismatches"]) == 0
    
    def test_verify_bundle_integrity_missing_manifest(self):
        """Test integrity verification with missing manifest."""
        extracted_files = {
            "inputs/data.csv": "/tmp/data.csv",
            "outputs/proof.pdf": "/tmp/proof.pdf"
        }
        
        valid, details = verify_bundle_integrity("test.zip", extracted_files)
        
        assert valid == False
        assert details["manifest_found"] == False
    
    def test_verify_bundle_integrity_hash_mismatch(self):
        """Test integrity verification with hash mismatch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create manifest with wrong hash
            manifest = {
                "version": "1.0",
                "files": {
                    "inputs/data.csv": {
                        "sha256": "wrong_hash_value" * 4,  # 64 chars
                        "size_bytes": 11
                    }
                },
                "root_hash": "also_wrong_hash" * 4
            }
            
            manifest_path = temp_path / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f)
            
            data_path = temp_path / "inputs" / "data.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_bytes(b"csv_content")
            
            extracted_files = {
                "manifest.json": str(manifest_path),
                "inputs/data.csv": str(data_path)
            }
            
            valid, details = verify_bundle_integrity("test.zip", extracted_files)
            
            assert valid == False
            assert len(details["hash_mismatches"]) == 1
            assert details["hash_mismatches"][0]["file"] == "inputs/data.csv"
    
    def test_verify_bundle_integrity_missing_file(self):
        """Test integrity verification with missing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manifest = {
                "version": "1.0",
                "files": {
                    "inputs/data.csv": {
                        "sha256": "some_hash" * 8,
                        "size_bytes": 100
                    }
                },
                "root_hash": "root_hash" * 8
            }
            
            manifest_path = temp_path / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f)
            
            extracted_files = {
                "manifest.json": str(manifest_path)
                # Missing inputs/data.csv
            }
            
            valid, details = verify_bundle_integrity("test.zip", extracted_files)
            
            assert valid == False
            assert "inputs/data.csv" in details["missing_files"]
    
    def test_verify_bundle_integrity_extra_files(self):
        """Test integrity verification detects extra files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manifest = {
                "version": "1.0",
                "files": {},
                "root_hash": hashlib.sha256(b"").hexdigest()
            }
            
            manifest_path = temp_path / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f)
            
            extra_path = temp_path / "extra_file.txt"
            extra_path.write_text("should not be here")
            
            extracted_files = {
                "manifest.json": str(manifest_path),
                "extra_file.txt": str(extra_path)  # Not in manifest
            }
            
            valid, details = verify_bundle_integrity("test.zip", extracted_files)
            
            assert "extra_file.txt" in details["extra_files"]


class TestDecisionRecomputation:
    """Test decision algorithm re-computation."""
    
    def test_recompute_decision_success(self):
        """Test successful decision recomputation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create directory structure
            inputs_dir = temp_path / "inputs"
            outputs_dir = temp_path / "outputs"
            inputs_dir.mkdir()
            outputs_dir.mkdir()
            
            # Copy test fixtures
            csv_fixture = load_csv_fixture("min_powder.csv")
            csv_path = inputs_dir / "raw_data.csv"
            csv_fixture.to_csv(csv_path, index=False)
            
            spec_data = load_spec_fixture("min_powder_spec.json")
            spec_path = inputs_dir / "specification.json"
            with open(spec_path, 'w') as f:
                json.dump(spec_data, f)
            
            # Create decision file
            decision_data = {
                "job_id": "test",
                "pass_": True,
                "target_temp_C": 170.0,
                "conservative_threshold_C": 172.0,
                "required_hold_time_s": 480,
                "actual_hold_time_s": 510,
                "max_temp_C": 174.5,
                "min_temp_C": 168.0,
                "reasons": []
            }
            decision_path = outputs_dir / "decision.json"
            with open(decision_path, 'w') as f:
                json.dump(decision_data, f)
            
            extracted_files = {
                "inputs/raw_data.csv": str(csv_path),
                "inputs/specification.json": str(spec_path),
                "outputs/decision.json": str(decision_path)
            }
            
            # Recompute decision
            success, decision, issues = recompute_decision(extracted_files)
            
            assert success == True
            assert decision is not None
            assert isinstance(decision, DecisionResult)
            assert len(issues) == 0
    
    def test_recompute_decision_missing_files(self):
        """Test decision recomputation with missing files."""
        extracted_files = {
            "inputs/raw_data.csv": "/tmp/data.csv"
            # Missing specification.json and decision.json
        }
        
        success, decision, issues = recompute_decision(extracted_files)
        
        assert success == False
        assert decision is None
        assert len(issues) > 0
        assert any("specification" in issue for issue in issues)
    
    def test_recompute_decision_invalid_spec(self):
        """Test decision recomputation with invalid specification."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create files
            csv_path = temp_path / "raw_data.csv"
            csv_path.write_text("timestamp,temp_C\n2024-01-01,170")
            
            spec_path = temp_path / "specification.json"
            spec_path.write_text('{"invalid": "spec"}')  # Invalid spec format
            
            decision_path = temp_path / "decision.json"
            decision_path.write_text('{"job_id": "test"}')
            
            extracted_files = {
                "inputs/raw_data.csv": str(csv_path),
                "inputs/specification.json": str(spec_path),
                "outputs/decision.json": str(decision_path)
            }
            
            success, decision, issues = recompute_decision(extracted_files)
            
            assert success == False
            assert decision is None
            assert any("Invalid specification" in issue for issue in issues)
    
    def test_recompute_decision_normalization_failure(self):
        """Test decision recomputation with data normalization failure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create invalid CSV data
            csv_path = temp_path / "raw_data.csv"
            csv_path.write_text("invalid,csv,format\nno,temp,data")
            
            spec_data = load_spec_fixture("min_powder_spec.json")
            spec_path = temp_path / "specification.json"
            with open(spec_path, 'w') as f:
                json.dump(spec_data, f)
            
            decision_path = temp_path / "decision.json"
            decision_path.write_text('{"job_id": "test"}')
            
            extracted_files = {
                "inputs/raw_data.csv": str(csv_path),
                "inputs/specification.json": str(spec_path),
                "outputs/decision.json": str(decision_path)
            }
            
            success, decision, issues = recompute_decision(extracted_files)
            
            assert success == False
            assert decision is None
            assert any("normalization failed" in issue for issue in issues)


class TestDecisionComparison:
    """Test decision comparison functionality."""
    
    def test_compare_decisions_identical(self):
        """Test comparing identical decisions."""
        decision1 = DecisionResult(
            job_id="test",
            pass_=True,
            target_temp_C=170.0,
            conservative_threshold_C=172.0,
            required_hold_time_s=480,
            actual_hold_time_s=510.5,
            max_temp_C=174.5,
            min_temp_C=168.0,
            reasons=["All requirements met"]
        )
        
        decision2 = DecisionResult(
            job_id="test",
            pass_=True,
            target_temp_C=170.0,
            conservative_threshold_C=172.0,
            required_hold_time_s=480,
            actual_hold_time_s=510.5,
            max_temp_C=174.5,
            min_temp_C=168.0,
            reasons=["All requirements met"]
        )
        
        match, discrepancies = compare_decisions(decision1, decision2)
        
        assert match == True
        assert len(discrepancies) == 0
    
    def test_compare_decisions_pass_fail_mismatch(self):
        """Test comparing decisions with different pass/fail status."""
        decision1 = DecisionResult(
            job_id="test",
            pass_=True,
            target_temp_C=170.0,
            conservative_threshold_C=172.0,
            required_hold_time_s=480,
            actual_hold_time_s=510,
            max_temp_C=174.5,
            min_temp_C=168.0
        )
        
        decision2 = decision1.model_copy()
        decision2.pass_ = False
        
        match, discrepancies = compare_decisions(decision1, decision2)
        
        assert match == False
        assert len(discrepancies) > 0
        assert any("Pass/Fail status" in d for d in discrepancies)
    
    def test_compare_decisions_numerical_tolerance(self):
        """Test numerical tolerance in decision comparison."""
        decision1 = DecisionResult(
            job_id="test",
            pass_=True,
            target_temp_C=170.0,
            conservative_threshold_C=172.0,
            required_hold_time_s=480,
            actual_hold_time_s=510.0,
            max_temp_C=174.5,
            min_temp_C=168.0
        )
        
        # Small difference within tolerance
        decision2 = decision1.model_copy()
        decision2.actual_hold_time_s = 510.05  # 0.05 difference < 0.1 tolerance
        
        match, discrepancies = compare_decisions(decision1, decision2)
        assert match == True
        assert len(discrepancies) == 0
        
        # Large difference outside tolerance
        decision3 = decision1.model_copy()
        decision3.actual_hold_time_s = 511.0  # 1.0 difference > 0.1 tolerance
        
        match, discrepancies = compare_decisions(decision1, decision3)
        assert match == False
        assert any("Actual hold time" in d for d in discrepancies)
    
    def test_compare_decisions_different_reasons(self):
        """Test comparing decisions with different reasons."""
        decision1 = DecisionResult(
            job_id="test",
            pass_=False,
            target_temp_C=170.0,
            conservative_threshold_C=172.0,
            required_hold_time_s=480,
            actual_hold_time_s=300,
            max_temp_C=171.0,
            min_temp_C=168.0,
            reasons=["Temperature below threshold", "Insufficient hold time"]
        )
        
        decision2 = decision1.model_copy()
        decision2.reasons = ["Temperature below threshold", "Data quality issues"]
        
        match, discrepancies = compare_decisions(decision1, decision2)
        
        assert match == False
        assert any("Missing reasons" in d for d in discrepancies)
        assert any("Extra reasons" in d for d in discrepancies)
    
    def test_verify_decision_consistency_alias(self):
        """Test verify_decision_consistency is an alias for compare_decisions."""
        decision1 = DecisionResult(
            job_id="test",
            pass_=True,
            target_temp_C=170.0,
            conservative_threshold_C=172.0,
            required_hold_time_s=480,
            actual_hold_time_s=510,
            max_temp_C=174.5,
            min_temp_C=168.0
        )
        
        decision2 = decision1.model_copy()
        
        # Both functions should return identical results
        match1, disc1 = compare_decisions(decision1, decision2)
        match2, disc2 = verify_decision_consistency(decision1, decision2)
        
        assert match1 == match2
        assert disc1 == disc2


class TestRFC3161Verification:
    """Test RFC 3161 timestamp verification."""
    
    def test_verify_rfc3161_timestamp_not_available(self):
        """Test RFC 3161 verification when libraries not available."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            pdf_path = tmp.name
            tmp.write(b"PDF content")
        
        try:
            with patch('core.verify.RFC3161_VERIFICATION_AVAILABLE', False):
                valid, details = verify_rfc3161_timestamp(pdf_path)
                
                assert valid == False
                assert details["rfc3161_found"] == False
                assert "not available" in details["rfc3161_issues"][0]
        finally:
            os.unlink(pdf_path)
    
    @pytest.mark.skipif(not RFC3161_VERIFICATION_AVAILABLE, reason="RFC3161 libs not available")
    def test_verify_rfc3161_timestamp_found(self):
        """Test RFC 3161 verification with timestamp found."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            pdf_path = tmp.name
        
        try:
            # Mock PyPDF2 reader
            mock_metadata = {
                '/CreationDate': f'D:{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}',
                '/Title': 'Test PDF with timestamp'
            }
            
            with patch('PyPDF2.PdfReader') as mock_reader_class:
                mock_reader = MagicMock()
                mock_reader.metadata = mock_metadata
                mock_reader_class.return_value = mock_reader
                
                valid, details = verify_rfc3161_timestamp(pdf_path, grace_period_s=86400)
                
                # Should find timestamp in metadata
                assert details["rfc3161_found"] == True
                assert details["rfc3161_timestamp"] is not None
        finally:
            os.unlink(pdf_path)
    
    def test_verify_rfc3161_timestamp_no_metadata(self):
        """Test RFC 3161 verification with no PDF metadata."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            pdf_path = tmp.name
        
        try:
            with patch('PyPDF2.PdfReader') as mock_reader_class:
                mock_reader = MagicMock()
                mock_reader.metadata = None
                mock_reader_class.return_value = mock_reader
                
                valid, details = verify_rfc3161_timestamp(pdf_path)
                
                assert valid == False
                assert details["rfc3161_found"] == False
                assert "No PDF metadata found" in details["rfc3161_issues"][0]
        finally:
            os.unlink(pdf_path)
    
    def test_verify_proof_pdf_basic(self):
        """Test basic PDF verification."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            pdf_path = tmp.name
            tmp.write(b"PDF test content")
        
        try:
            result = verify_proof_pdf(pdf_path)
            
            assert result is not None
            assert result["valid"] == True
            assert result["file_size"] == 16
            assert "verified_at" in result
        finally:
            os.unlink(pdf_path)
    
    def test_verify_proof_pdf_not_found(self):
        """Test PDF verification with non-existent file."""
        result = verify_proof_pdf("/nonexistent/file.pdf")
        
        assert result["valid"] == False
        assert result["error"] == "PDF file not found"


class TestManifestHash:
    """Test manifest hash calculation."""
    
    def test_calculate_manifest_hash(self):
        """Test calculating hash of manifest."""
        manifest = {
            "version": "1.0",
            "created_at": "2024-01-01T00:00:00Z",
            "files": {
                "test.txt": {"sha256": "abc123", "size": 100}
            },
            "root_hash": "xyz789"  # Should be excluded from hash
        }
        
        hash1 = calculate_manifest_hash(manifest)
        assert len(hash1) == 64  # SHA-256 hash length
        
        # Same manifest should produce same hash
        hash2 = calculate_manifest_hash(manifest.copy())
        assert hash1 == hash2
        
        # Different manifest should produce different hash
        manifest2 = manifest.copy()
        manifest2["version"] = "2.0"
        hash3 = calculate_manifest_hash(manifest2)
        assert hash1 != hash3
    
    def test_calculate_manifest_hash_excludes_root_hash(self):
        """Test that root_hash is excluded from manifest hash calculation."""
        manifest1 = {
            "version": "1.0",
            "files": {"test.txt": {"sha256": "abc123"}},
            "root_hash": "hash1"
        }
        
        manifest2 = manifest1.copy()
        manifest2["root_hash"] = "different_hash"
        
        # Hashes should be the same since root_hash is excluded
        hash1 = calculate_manifest_hash(manifest1)
        hash2 = calculate_manifest_hash(manifest2)
        assert hash1 == hash2


class TestFullVerificationWorkflow:
    """Test complete verification workflows."""
    
    def test_verify_evidence_bundle_success(self):
        """Test successful verification of valid evidence bundle."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a valid evidence bundle using pack module
            csv_path = temp_path / "data.csv"
            df = load_csv_fixture("min_powder.csv")
            df.to_csv(csv_path, index=False)
            
            spec_path = temp_path / "spec.json"
            spec_data = load_spec_fixture("min_powder_spec.json")
            with open(spec_path, 'w') as f:
                json.dump(spec_data, f)
            
            # Create dummy output files
            normalized_path = temp_path / "normalized.csv"
            df.to_csv(normalized_path, index=False)
            
            decision_path = temp_path / "decision.json"
            decision_data = {
                "job_id": "test",
                "pass_": True,
                "target_temp_C": 170.0,
                "conservative_threshold_C": 172.0,
                "required_hold_time_s": 480,
                "actual_hold_time_s": 510,
                "max_temp_C": 174.5,
                "min_temp_C": 168.0,
                "reasons": []
            }
            with open(decision_path, 'w') as f:
                json.dump(decision_data, f)
            
            proof_path = temp_path / "proof.pdf"
            proof_path.write_bytes(b"PDF content")
            
            plot_path = temp_path / "plot.png"
            plot_path.write_bytes(b"PNG content")
            
            bundle_path = temp_path / "evidence.zip"
            
            # Create bundle
            create_evidence_bundle(
                str(csv_path),
                str(spec_path),
                str(normalized_path),
                str(decision_path),
                str(proof_path),
                str(plot_path),
                str(bundle_path),
                deterministic=True
            )
            
            # Verify bundle
            report = verify_evidence_bundle(str(bundle_path), verify_decision=False)
            
            assert report.is_valid == True
            assert report.bundle_exists == True
            assert report.manifest_found == True
            assert report.root_hash_valid == True
            assert report.files_verified == report.files_total
            assert len(report.issues) == 0
    
    def test_verify_evidence_bundle_tampered(self):
        """Test verification detects tampered bundle."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a bundle first
            csv_path = temp_path / "data.csv"
            df = load_csv_fixture("min_powder.csv")
            df.to_csv(csv_path, index=False)
            
            spec_path = temp_path / "spec.json"
            spec_data = load_spec_fixture("min_powder_spec.json")
            with open(spec_path, 'w') as f:
                json.dump(spec_data, f)
            
            # Create dummy files
            normalized_path = temp_path / "normalized.csv"
            df.to_csv(normalized_path, index=False)
            
            decision_path = temp_path / "decision.json"
            with open(decision_path, 'w') as f:
                json.dump({"job_id": "test", "pass_": True}, f)
            
            proof_path = temp_path / "proof.pdf"
            proof_path.write_bytes(b"PDF")
            
            plot_path = temp_path / "plot.png"
            plot_path.write_bytes(b"PNG")
            
            bundle_path = temp_path / "evidence.zip"
            
            # Create bundle
            create_evidence_bundle(
                str(csv_path),
                str(spec_path),
                str(normalized_path),
                str(decision_path),
                str(proof_path),
                str(plot_path),
                str(bundle_path),
                deterministic=True
            )
            
            # Tamper with the bundle - modify a file inside
            with zipfile.ZipFile(str(bundle_path), 'a') as zf:
                # Read original content
                original_csv = zf.read("inputs/raw_data.csv")
                # Modify it
                tampered_csv = original_csv + b"\n2024-01-01,999.9"
                # Remove original and add tampered version
                zf.writestr("inputs/raw_data.csv", tampered_csv)
            
            # Verify tampered bundle
            report = verify_evidence_bundle(str(bundle_path), verify_decision=False)
            
            assert report.is_valid == False
            assert len(report.hash_mismatches) > 0
            assert any("raw_data.csv" in mismatch["file"] for mismatch in report.hash_mismatches)
    
    def test_verify_evidence_bundle_with_decision_verification(self):
        """Test full verification including decision re-computation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Load test data
            df = load_csv_fixture("min_powder.csv")
            spec = load_spec_fixture_validated("min_powder_spec.json")
            
            # Run actual decision algorithm
            from core.decide import make_decision
            from core.normalize import normalize_temperature_data
            
            normalized_df = normalize_temperature_data(df, 30.0, 120.0, 60.0)
            decision = make_decision(normalized_df, spec)
            
            # Create files
            csv_path = temp_path / "data.csv"
            df.to_csv(csv_path, index=False)
            
            spec_path = temp_path / "spec.json"
            with open(spec_path, 'w') as f:
                json.dump(spec.model_dump(), f)
            
            normalized_path = temp_path / "normalized.csv"
            normalized_df.to_csv(normalized_path, index=False)
            
            decision_path = temp_path / "decision.json"
            with open(decision_path, 'w') as f:
                json.dump(decision.model_dump(), f)
            
            proof_path = temp_path / "proof.pdf"
            proof_path.write_bytes(b"PDF")
            
            plot_path = temp_path / "plot.png"
            plot_path.write_bytes(b"PNG")
            
            bundle_path = temp_path / "evidence.zip"
            
            # Create bundle
            create_evidence_bundle(
                str(csv_path),
                str(spec_path),
                str(normalized_path),
                str(decision_path),
                str(proof_path),
                str(plot_path),
                str(bundle_path),
                deterministic=True
            )
            
            # Verify with decision re-computation
            report = verify_evidence_bundle(str(bundle_path), verify_decision=True)
            
            assert report.is_valid == True
            assert report.decision_recomputed == True
            assert report.decision_matches == True
            assert len(report.decision_discrepancies) == 0
    
    def test_verify_bundle_quick(self):
        """Test quick verification (integrity only)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create minimal bundle
            csv_path = temp_path / "data.csv"
            csv_path.write_text("timestamp,temp_C\n2024-01-01,170")
            
            spec_path = temp_path / "spec.json"
            spec_data = load_spec_fixture("min_powder_spec.json")
            with open(spec_path, 'w') as f:
                json.dump(spec_data, f)
            
            # Create dummy files
            for name in ["normalized.csv", "decision.json", "proof.pdf", "plot.png"]:
                (temp_path / name).write_bytes(b"dummy content")
            
            bundle_path = temp_path / "evidence.zip"
            
            create_evidence_bundle(
                str(csv_path),
                str(spec_path),
                str(temp_path / "normalized.csv"),
                str(temp_path / "decision.json"),
                str(temp_path / "proof.pdf"),
                str(temp_path / "plot.png"),
                str(bundle_path),
                deterministic=True
            )
            
            # Quick verify
            result = verify_bundle_quick(str(bundle_path))
            
            assert "valid" in result
            assert "root_hash" in result
            assert "files_verified" in result
            assert result["valid"] == True
    
    def test_verify_evidence_bundle_cleanup(self):
        """Test temporary directory cleanup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create minimal bundle
            bundle_path = temp_path / "test.zip"
            with zipfile.ZipFile(bundle_path, 'w') as zf:
                zf.writestr("manifest.json", '{"version": "1.0", "files": {}}')
            
            # Track temp directories created
            temp_dirs = []
            original_mkdtemp = tempfile.mkdtemp
            
            def track_mkdtemp(*args, **kwargs):
                temp_dir = original_mkdtemp(*args, **kwargs)
                temp_dirs.append(temp_dir)
                return temp_dir
            
            with patch('tempfile.mkdtemp', side_effect=track_mkdtemp):
                # Verify with cleanup
                report = verify_evidence_bundle(str(bundle_path), cleanup_temp=True)
                
                # Check temp dir was created and cleaned up
                assert len(temp_dirs) == 1
                assert not Path(temp_dirs[0]).exists()
    
    def test_verify_evidence_bundle_no_cleanup(self):
        """Test preserving temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create minimal bundle
            bundle_path = temp_path / "test.zip"
            with zipfile.ZipFile(bundle_path, 'w') as zf:
                zf.writestr("manifest.json", '{"version": "1.0", "files": {}}')
            
            # Verify without cleanup
            extract_dir = temp_path / "extracted"
            report = verify_evidence_bundle(
                str(bundle_path), 
                extract_dir=str(extract_dir),
                cleanup_temp=False
            )
            
            # Extract dir should still exist
            assert extract_dir.exists()
            assert (extract_dir / "manifest.json").exists()


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_verify_nonexistent_bundle(self):
        """Test verifying non-existent bundle."""
        report = verify_evidence_bundle("/nonexistent/bundle.zip")
        
        assert report.is_valid == False
        assert report.bundle_exists == False
        assert len(report.issues) > 0
        assert any("not found" in issue for issue in report.issues)
    
    def test_verify_corrupted_bundle(self):
        """Test verifying corrupted ZIP file."""
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            bundle_path = tmp.name
            tmp.write(b"This is not a valid ZIP file")
        
        try:
            report = verify_evidence_bundle(bundle_path)
            
            assert report.is_valid == False
            assert len(report.issues) > 0
            assert any("extraction failed" in issue for issue in report.issues)
        finally:
            os.unlink(bundle_path)
    
    def test_verify_bundle_with_exception_in_process(self):
        """Test handling exceptions during verification process."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "test.zip"
            
            # Create valid ZIP structure
            with zipfile.ZipFile(bundle_path, 'w') as zf:
                zf.writestr("manifest.json", '{"version": "1.0"}')
            
            # Mock an exception during extraction
            with patch('core.verify.extract_bundle_to_temp', side_effect=Exception("Test error")):
                report = verify_evidence_bundle(str(bundle_path))
                
                assert report.is_valid == False
                assert len(report.issues) > 0
                assert any("Test error" in issue for issue in report.issues)


# Example usage in comments (for module documentation)
"""
Example usage for ProofKit verification testing:

# Run all verification tests
pytest tests/test_verify.py -v

# Run specific test class
pytest tests/test_verify.py::TestBundleIntegrity -v

# Run with coverage
pytest tests/test_verify.py --cov=core.verify --cov-report=html

# Test quick verification
from tests.test_verify import TestFullVerificationWorkflow
test_instance = TestFullVerificationWorkflow()
test_instance.test_verify_bundle_quick()
"""