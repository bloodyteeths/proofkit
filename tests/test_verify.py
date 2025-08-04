"""
ProofKit Bundle Verification Tests

Comprehensive test suite for evidence bundle verification functionality including:
- Bundle integrity validation
- Hash verification and tamper detection  
- Decision re-computation and validation
- File corruption detection
- Manifest validation
- End-to-end verification workflows

Example usage:
    pytest tests/test_verify.py -v
"""

import pytest
import pandas as pd
import json
import zipfile
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

from core.verify import (
    verify_evidence_bundle,
    verify_bundle_integrity,
    verify_decision_consistency,
    calculate_manifest_hash,
    VerificationReport,
    VerificationError
)
from core.pack import create_evidence_bundle, calculate_content_hash
from core.models import SpecV1, DecisionResult
from core.decide import make_decision
from core.normalize import normalize_temperature_data


class TestBundleIntegrity:
    """Test evidence bundle integrity validation."""
    
    def test_valid_bundle_verification(self, temp_dir, simple_temp_data, example_spec):
        """Test verification of a valid evidence bundle."""
        # Create a valid bundle
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        # Save test data
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        # Create bundle
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        # Verify bundle
        report = verify_evidence_bundle(str(bundle_path))
        
        assert isinstance(report, VerificationReport)
        assert report.is_valid is True
        assert report.bundle_exists is True
        assert report.manifest_found is True
        assert report.manifest_valid is True
        assert report.decision_matches is True
        assert len(report.issues) == 0
        assert report.root_hash is not None
    
    def test_missing_bundle_file(self, temp_dir):
        """Test verification of non-existent bundle."""
        bundle_path = temp_dir / "nonexistent.zip"
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert report.bundle_exists is False
        assert "Bundle file not found" in report.issues
    
    def test_corrupted_zip_file(self, temp_dir):
        """Test verification of corrupted ZIP file."""
        bundle_path = temp_dir / "corrupted.zip"
        
        # Create corrupted ZIP file
        with open(bundle_path, 'wb') as f:
            f.write(b"This is not a valid ZIP file")
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert "Invalid ZIP file" in " ".join(report.issues)
    
    def test_missing_manifest(self, temp_dir, simple_temp_data, example_spec):
        """Test verification of bundle without manifest."""
        bundle_path = temp_dir / "no_manifest.zip"
        
        # Create ZIP without manifest
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            # Add some files but no manifest
            zf.writestr("data.csv", simple_temp_data.to_csv(index=False))
            zf.writestr("spec.json", json.dumps(example_spec.model_dump(), indent=2))
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert report.manifest_found is False
        assert "Manifest not found" in " ".join(report.issues)
    
    def test_invalid_manifest_format(self, temp_dir, simple_temp_data, example_spec):
        """Test verification of bundle with invalid manifest."""
        bundle_path = temp_dir / "invalid_manifest.zip"
        
        # Create ZIP with invalid manifest
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("data.csv", simple_temp_data.to_csv(index=False))
            zf.writestr("spec.json", json.dumps(example_spec.model_dump(), indent=2))
            zf.writestr("manifest.json", "This is not valid JSON")
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert report.manifest_valid is False
        assert "Invalid manifest format" in " ".join(report.issues)


class TestHashVerification:
    """Test file hash verification and tamper detection."""
    
    def test_hash_calculation_consistency(self, temp_dir, simple_temp_data):
        """Test that hash calculations are consistent."""
        csv_path = temp_dir / "test_data.csv"
        simple_temp_data.to_csv(csv_path, index=False)
        
        # Calculate hash twice
        hash1 = calculate_content_hash(str(csv_path))
        hash2 = calculate_content_hash(str(csv_path))
        
        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) > 0
    
    def test_hash_detects_tampering(self, temp_dir, simple_temp_data, example_spec):
        """Test that hash verification detects file tampering."""
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        # Create original bundle
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        # Tamper with the bundle by modifying a file inside
        with zipfile.ZipFile(bundle_path, 'a') as zf:
            # Overwrite data with modified content
            modified_data = simple_temp_data.copy()
            modified_data.iloc[0, 1] = 999.9  # Change first temperature value
            zf.writestr("data.csv", modified_data.to_csv(index=False))
        
        # Verification should detect tampering
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert "Hash mismatch" in " ".join(report.issues) or "tamper" in " ".join(report.issues).lower()
    
    def test_manifest_hash_validation(self, temp_dir, simple_temp_data, example_spec):
        """Test manifest hash validation against file contents."""
        # Create test files
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        # Calculate expected hashes
        csv_hash = calculate_content_hash(str(csv_path))
        spec_hash = calculate_content_hash(str(spec_path))
        
        # Create manifest
        manifest = {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": {
                "data.csv": {"hash": csv_hash, "size": csv_path.stat().st_size},
                "spec.json": {"hash": spec_hash, "size": spec_path.stat().st_size}
            }
        }
        
        manifest_hash = calculate_manifest_hash(manifest)
        
        # Hash should be deterministic
        manifest_hash2 = calculate_manifest_hash(manifest)
        assert manifest_hash == manifest_hash2


class TestDecisionConsistency:
    """Test decision re-computation and consistency validation."""
    
    def test_decision_recomputation_matches(self, temp_dir, simple_temp_data, example_spec):
        """Test that re-computed decisions match original."""
        # Create bundle with decision
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        # Verify decision consistency
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.decision_matches is True
        assert report.original_decision is not None
        assert report.recomputed_decision is not None
        assert report.original_decision.pass_ == report.recomputed_decision.pass_
        assert abs(report.original_decision.actual_hold_time_s - 
                  report.recomputed_decision.actual_hold_time_s) < 1.0
    
    def test_decision_mismatch_detection(self, temp_dir, simple_temp_data, example_spec):
        """Test detection of decision mismatches."""
        # Create bundle
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        # Create bundle manually to inject wrong decision
        original_decision = make_decision(simple_temp_data, example_spec)
        
        # Create fake decision with different result
        fake_decision = DecisionResult(
            pass_=not original_decision.pass_,  # Flip the result
            job_id=original_decision.job_id,
            target_temp_C=original_decision.target_temp_C,
            conservative_threshold_C=original_decision.conservative_threshold_C,
            actual_hold_time_s=100.0,  # Wrong value
            required_hold_time_s=original_decision.required_hold_time_s,
            max_temp_C=original_decision.max_temp_C,
            min_temp_C=original_decision.min_temp_C,
            reasons=["Fake decision for testing"],
            warnings=[]
        )
        
        # Create bundle with fake decision
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("data.csv", simple_temp_data.to_csv(index=False))
            zf.writestr("spec.json", json.dumps(example_spec.model_dump(), indent=2))
            zf.writestr("decision.json", json.dumps(fake_decision.model_dump(), indent=2))
            
            # Create manifest
            manifest = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {
                    "data.csv": {"hash": "dummy_hash", "size": 1000},
                    "spec.json": {"hash": "dummy_hash", "size": 500},
                    "decision.json": {"hash": "dummy_hash", "size": 300}
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        # Verification should detect decision mismatch
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.decision_matches is False
        assert "Decision mismatch" in " ".join(report.issues)
    
    def test_missing_decision_file(self, temp_dir, simple_temp_data, example_spec):
        """Test verification of bundle missing decision file."""
        bundle_path = temp_dir / "no_decision.zip"
        
        # Create ZIP without decision file
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("data.csv", simple_temp_data.to_csv(index=False))
            zf.writestr("spec.json", json.dumps(example_spec.model_dump(), indent=2))
            
            manifest = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {
                    "data.csv": {"hash": "dummy_hash", "size": 1000},
                    "spec.json": {"hash": "dummy_hash", "size": 500}
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert "Decision file not found" in " ".join(report.issues)


class TestCorruptionDetection:
    """Test detection of various types of data corruption."""
    
    def test_csv_structure_corruption(self, temp_dir, example_spec):
        """Test detection of CSV structure corruption."""
        bundle_path = temp_dir / "corrupt_csv.zip"
        
        # Create bundle with corrupted CSV
        corrupted_csv = "timestamp,temp1,temp2\nThis is not valid CSV data\n123,abc,def"
        
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("data.csv", corrupted_csv)
            zf.writestr("spec.json", json.dumps(example_spec.model_dump(), indent=2))
            
            manifest = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {
                    "data.csv": {"hash": hashlib.sha256(corrupted_csv.encode()).hexdigest(), "size": len(corrupted_csv)},
                    "spec.json": {"hash": "dummy_hash", "size": 500}
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert any("CSV" in issue or "data" in issue for issue in report.issues)
    
    def test_spec_corruption(self, temp_dir, simple_temp_data):
        """Test detection of specification file corruption."""
        bundle_path = temp_dir / "corrupt_spec.zip"
        
        # Create bundle with corrupted spec
        corrupted_spec = "This is not valid JSON for a specification"
        
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("data.csv", simple_temp_data.to_csv(index=False))
            zf.writestr("spec.json", corrupted_spec)
            
            manifest = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {
                    "data.csv": {"hash": "dummy_hash", "size": 1000},
                    "spec.json": {"hash": hashlib.sha256(corrupted_spec.encode()).hexdigest(), "size": len(corrupted_spec)}
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert any("spec" in issue.lower() or "json" in issue.lower() for issue in report.issues)
    
    def test_size_mismatch_detection(self, temp_dir, simple_temp_data, example_spec):
        """Test detection of file size mismatches."""
        bundle_path = temp_dir / "size_mismatch.zip"
        csv_content = simple_temp_data.to_csv(index=False)
        spec_content = json.dumps(example_spec.model_dump(), indent=2)
        
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            zf.writestr("data.csv", csv_content)
            zf.writestr("spec.json", spec_content)
            
            # Create manifest with wrong file sizes
            manifest = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {
                    "data.csv": {"hash": hashlib.sha256(csv_content.encode()).hexdigest(), "size": 999999},  # Wrong size
                    "spec.json": {"hash": hashlib.sha256(spec_content.encode()).hexdigest(), "size": len(spec_content)}
                }
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        report = verify_evidence_bundle(str(bundle_path))
        
        assert report.is_valid is False
        assert any("size" in issue.lower() for issue in report.issues)


class TestVerificationReport:
    """Test VerificationReport functionality."""
    
    def test_report_structure(self, temp_dir, simple_temp_data, example_spec):
        """Test verification report structure and contents."""
        # Create valid bundle
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        report = verify_evidence_bundle(str(bundle_path))
        
        # Check all expected attributes
        assert hasattr(report, 'bundle_path')
        assert hasattr(report, 'timestamp')
        assert hasattr(report, 'bundle_exists')
        assert hasattr(report, 'manifest_found')
        assert hasattr(report, 'manifest_valid')
        assert hasattr(report, 'root_hash')
        assert hasattr(report, 'file_hashes_valid')
        assert hasattr(report, 'decision_matches')
        assert hasattr(report, 'original_decision')
        assert hasattr(report, 'recomputed_decision')
        assert hasattr(report, 'is_valid')
        assert hasattr(report, 'issues')
        assert hasattr(report, 'warnings')
        
        # Check report validity summary
        assert report.is_valid == (len(report.issues) == 0)
    
    def test_report_serialization(self, temp_dir, simple_temp_data, example_spec):
        """Test that verification reports can be serialized."""
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        report = verify_evidence_bundle(str(bundle_path))
        
        # Should be able to convert to dictionary
        report_dict = report.to_dict()
        assert isinstance(report_dict, dict)
        assert 'bundle_path' in report_dict
        assert 'is_valid' in report_dict
        assert 'issues' in report_dict
    
    def test_report_summary_generation(self, temp_dir, simple_temp_data, example_spec):
        """Test generation of verification report summaries."""
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        report = verify_evidence_bundle(str(bundle_path))
        summary = report.generate_summary()
        
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "verification" in summary.lower()
        if report.is_valid:
            assert "valid" in summary.lower() or "pass" in summary.lower()
        else:
            assert "invalid" in summary.lower() or "fail" in summary.lower()


class TestEndToEndVerification:
    """Test complete end-to-end verification workflows."""
    
    def test_complete_workflow_pass(self, temp_dir, simple_temp_data, example_spec):
        """Test complete verification workflow with passing data."""
        # Create and verify bundle
        csv_path = temp_dir / "passing_data.csv"
        spec_path = temp_dir / "spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        report = verify_evidence_bundle(str(bundle_path))
        
        # All checks should pass
        assert report.is_valid is True
        assert report.bundle_exists is True
        assert report.manifest_found is True
        assert report.manifest_valid is True
        assert report.file_hashes_valid is True
        assert report.decision_matches is True
        assert len(report.issues) == 0
        
        # Decision should be PASS
        assert report.original_decision.pass_ is True
        assert report.recomputed_decision.pass_ is True
    
    def test_complete_workflow_fail(self, temp_dir, failing_temp_data, example_spec):
        """Test complete verification workflow with failing data."""
        csv_path = temp_dir / "failing_data.csv"
        spec_path = temp_dir / "spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        failing_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        report = verify_evidence_bundle(str(bundle_path))
        
        # Bundle should be valid but decision should be FAIL
        assert report.is_valid is True
        assert report.decision_matches is True
        assert report.original_decision.pass_ is False
        assert report.recomputed_decision.pass_ is False
    
    def test_multiple_bundle_verification(self, temp_dir, simple_temp_data, failing_temp_data, example_spec):
        """Test verification of multiple bundles."""
        bundles = []
        
        # Create multiple bundles
        for i, data in enumerate([simple_temp_data, failing_temp_data]):
            csv_path = temp_dir / f"data_{i}.csv"
            spec_path = temp_dir / f"spec_{i}.json"
            bundle_path = temp_dir / f"evidence_{i}.zip"
            
            data.to_csv(csv_path, index=False)
            with open(spec_path, 'w') as f:
                json.dump(example_spec.model_dump(), f, indent=2)
            
            create_evidence_bundle(
                csv_path=str(csv_path),
                spec_path=str(spec_path),
                output_path=str(bundle_path)
            )
            
            bundles.append(str(bundle_path))
        
        # Verify all bundles
        reports = []
        for bundle_path in bundles:
            report = verify_evidence_bundle(bundle_path)
            reports.append(report)
        
        # All bundles should be valid (though decisions may differ)
        for report in reports:
            assert report.is_valid is True
            assert report.bundle_exists is True
            assert report.decision_matches is True
        
        # First should pass, second should fail
        assert reports[0].original_decision.pass_ is True
        assert reports[1].original_decision.pass_ is False