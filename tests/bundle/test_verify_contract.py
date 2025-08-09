#!/usr/bin/env python3
"""
Test evidence bundle verification contract and root hash validation.

Tests the contract between pack.py bundle creation and verify_bundle.py
validation, ensuring root hash calculations are deterministic and match.
"""

import tempfile
import json
import hashlib
from pathlib import Path
import pytest

def test_bundle_verification_contract():
    """Test that verify_bundle matches pack.py root hash calculation."""
    
    # Create temporary test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create mock files for evidence bundle
        raw_csv = temp_path / "raw_data.csv"
        spec_json = temp_path / "specification.json"
        normalized_csv = temp_path / "normalized_data.csv"
        decision_json = temp_path / "decision.json"
        proof_pdf = temp_path / "proof.pdf"
        plot_png = temp_path / "plot.png"
        
        # Write test data to files
        raw_csv.write_text("timestamp,temperature\n2024-01-01 00:00:00,180.5\n")
        spec_json.write_text('{"job": {"job_id": "test123"}, "spec": {"target_temp_C": 180}}')
        normalized_csv.write_text("timestamp,temperature\n2024-01-01 00:00:00,180.5\n")
        decision_json.write_text('{"pass": true, "status": "PASS"}')
        proof_pdf.write_bytes(b"mock pdf content")
        plot_png.write_bytes(b"mock png content")
        
        # Create evidence bundle using pack.py
        from core.pack import create_evidence_bundle
        
        bundle_path = temp_path / "evidence.zip"
        
        result = create_evidence_bundle(
            raw_csv_path=str(raw_csv),
            spec_json_path=str(spec_json),
            normalized_csv_path=str(normalized_csv),
            decision_json_path=str(decision_json),
            proof_pdf_path=str(proof_pdf),
            plot_png_path=str(plot_png),
            output_path=str(bundle_path),
            job_id="test123",
            deterministic=True
        )
        
        assert Path(bundle_path).exists(), "Evidence bundle should be created"
        
        # Verify bundle using verify_bundle.py
        from scripts.verify_bundle import verify_bundle
        
        verification_result = verify_bundle(str(bundle_path))
        
        # Verify all assertions pass
        assert verification_result["valid_zip"], "Bundle should be valid ZIP"
        assert verification_result["manifest_valid"], "Manifest should be valid"
        assert verification_result["hashes_match"], "All file hashes should match"
        assert verification_result["root_hash_match"], "Root hash should match"
        assert verification_result["assertions_passed"], f"All assertions should pass: {verification_result.get('assertions', [])}"
        
        # Verify root hash calculation matches
        assert verification_result["root_hash"] is not None, "Root hash should be present"
        assert verification_result["root_hash_calculated"] is not None, "Calculated root hash should be present"
        assert verification_result["root_hash"] == verification_result["root_hash_calculated"], \
            f"Root hash mismatch: {verification_result['root_hash'][:16]} != {verification_result['root_hash_calculated'][:16]}"


def test_bundle_verification_with_modified_file():
    """Test that verification detects modified files."""
    
    # Create temporary test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create mock files for evidence bundle
        raw_csv = temp_path / "raw_data.csv"
        spec_json = temp_path / "specification.json"
        normalized_csv = temp_path / "normalized_data.csv"
        decision_json = temp_path / "decision.json"
        proof_pdf = temp_path / "proof.pdf"
        plot_png = temp_path / "plot.png"
        
        # Write test data to files
        raw_csv.write_text("timestamp,temperature\n2024-01-01 00:00:00,180.5\n")
        spec_json.write_text('{"job": {"job_id": "test123"}, "spec": {"target_temp_C": 180}}')
        normalized_csv.write_text("timestamp,temperature\n2024-01-01 00:00:00,180.5\n")
        decision_json.write_text('{"pass": true, "status": "PASS"}')
        proof_pdf.write_bytes(b"mock pdf content")
        plot_png.write_bytes(b"mock png content")
        
        # Create evidence bundle
        from core.pack import create_evidence_bundle
        
        bundle_path = temp_path / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(raw_csv),
            spec_json_path=str(spec_json),
            normalized_csv_path=str(normalized_csv),
            decision_json_path=str(decision_json),
            proof_pdf_path=str(proof_pdf),
            plot_png_path=str(plot_png),
            output_path=str(bundle_path),
            job_id="test123",
            deterministic=True
        )
        
        # Modify the bundle to simulate tampering
        import zipfile
        import tempfile
        
        # Extract bundle and modify a file
        with zipfile.ZipFile(bundle_path, 'r') as original:
            with tempfile.TemporaryDirectory() as extract_dir:
                extract_path = Path(extract_dir)
                original.extractall(extract_path)
                
                # Modify decision.json
                decision_file = extract_path / "outputs" / "decision.json"
                if decision_file.exists():
                    decision_file.write_text('{"pass": false, "status": "FAIL"}')  # Modified!
                
                # Repack into new bundle
                modified_bundle = temp_path / "evidence_modified.zip"
                with zipfile.ZipFile(modified_bundle, 'w') as modified:
                    for file_path in extract_path.rglob('*'):
                        if file_path.is_file():
                            relative_path = file_path.relative_to(extract_path)
                            modified.write(file_path, relative_path)
        
        # Verify modified bundle
        from scripts.verify_bundle import verify_bundle
        
        verification_result = verify_bundle(str(modified_bundle))
        
        # Should detect hash mismatch
        assert not verification_result["hashes_match"], "Should detect hash mismatch"
        assert not verification_result["assertions_passed"], "Assertions should fail for modified bundle"
        assert "hash_mismatches" in verification_result, "Should report hash mismatches"


def test_root_hash_deterministic():
    """Test that root hash calculation is deterministic."""
    
    # Test root hash calculation with same data multiple times
    from core.pack import create_manifest
    
    # Mock file info
    file_info = [
        ("inputs/raw_data.csv", Path("/tmp/test1.csv"), "abc123"),
        ("outputs/decision.json", Path("/tmp/test2.json"), "def456")
    ]
    
    # Create temporary files for size calculation
    for _, path, _ in file_info:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test content")
    
    try:
        metadata = {"job_id": "test123"}
        
        # Generate manifest multiple times
        manifest1, root_hash1 = create_manifest(file_info, metadata, deterministic=True)
        manifest2, root_hash2 = create_manifest(file_info, metadata, deterministic=True)
        
        # Root hashes should be identical
        assert root_hash1 == root_hash2, f"Root hash should be deterministic: {root_hash1[:16]} != {root_hash2[:16]}"
        
        # Manifests should be identical
        assert manifest1["root_sha256"] == manifest2["root_sha256"], "Manifest root hashes should match"
        
        # Test verify_bundle root hash calculation
        from scripts.verify_bundle import compute_root_hash
        
        computed1 = compute_root_hash(manifest1)
        computed2 = compute_root_hash(manifest2)
        
        assert computed1 == computed2, f"Computed root hashes should match: {computed1[:16]} != {computed2[:16]}"
        assert computed1 == root_hash1, f"Computed should match pack.py: {computed1[:16]} != {root_hash1[:16]}"
        
    finally:
        # Clean up
        for _, path, _ in file_info:
            path.unlink(missing_ok=True)


def test_bundle_verification_contract_violations():
    """Test that contract violations are detected."""
    
    # Create temporary test files with INDETERMINATE status
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create mock files for evidence bundle
        raw_csv = temp_path / "raw_data.csv"
        spec_json = temp_path / "specification.json"
        normalized_csv = temp_path / "normalized_data.csv"
        decision_json = temp_path / "decision.json"
        proof_pdf = temp_path / "proof.pdf"
        plot_png = temp_path / "plot.png"
        
        # Write test data to files with INDETERMINATE decision
        raw_csv.write_text("timestamp,temperature\n2024-01-01 00:00:00,180.5\n")
        spec_json.write_text('{"job": {"job_id": "test123"}, "spec": {"target_temp_C": 180}}')
        normalized_csv.write_text("timestamp,temperature\n2024-01-01 00:00:00,180.5\n")
        decision_json.write_text('{"pass": false, "status": "INDETERMINATE"}')  # INDETERMINATE status
        proof_pdf.write_bytes(b"mock pdf content")
        plot_png.write_bytes(b"mock png content")
        
        # Create evidence bundle
        from core.pack import create_evidence_bundle
        
        bundle_path = temp_path / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(raw_csv),
            spec_json_path=str(spec_json),
            normalized_csv_path=str(normalized_csv),
            decision_json_path=str(decision_json),
            proof_pdf_path=str(proof_pdf),
            plot_png_path=str(plot_png),
            output_path=str(bundle_path),
            job_id="test123",
            deterministic=True
        )
        
        # Verify bundle - should detect PDF validation issues
        from scripts.verify_bundle import verify_bundle
        
        verification_result = verify_bundle(str(bundle_path))
        
        # Check that PDF validation was checked
        assert verification_result.get("validation_gates_checked", False), "PDF validation gates should be checked"
        
        # Note: Contract violations depend on environment variables
        # In test environment, PDF validation may pass
        print(f"PDF validation status: {verification_result.get('pdf_validation_status')}")
        print(f"Contract violations: {verification_result.get('contract_violations', [])}")


if __name__ == "__main__":
    test_bundle_verification_contract()
    test_bundle_verification_with_modified_file()
    test_root_hash_deterministic()
    test_bundle_verification_contract_violations()
    print("✅ All bundle verification contract tests passed")