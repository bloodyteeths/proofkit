"""
ProofKit Evidence Bundle Packing Tests

Comprehensive test suite for evidence bundle creation and verification including:
- Bundle creation from tiny inputs
- ZIP structure validation
- Manifest.json validation and SHA-256 hash verification
- Root hash calculation and verification
- Tamper detection
- File combinations and error handling
- Edge cases and boundary conditions

Example usage:
    pytest tests/test_pack.py -v --cov=core/pack
"""

import pytest
import json
import zipfile
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

from core.pack import (
    create_evidence_bundle,
    verify_evidence_bundle,
    extract_evidence_bundle,
    calculate_file_hash,
    calculate_content_hash,
    create_manifest,
    validate_required_files,
    PackingError
)
from tests.helpers import (
    read_zip_file,
    read_zip_file_text,
    compute_sha256_file,
    compute_sha256_bytes,
    load_csv_fixture,
    load_spec_fixture,
    fixtures_dir
)


class TestHashCalculation:
    """Test hash calculation functions."""
    
    def test_calculate_file_hash_consistency(self, temp_dir):
        """Test that file hash calculation is consistent."""
        test_file = temp_dir / "test.txt"
        test_content = "Hello, ProofKit test data!"
        test_file.write_text(test_content)
        
        # Calculate hash twice
        hash1 = calculate_file_hash(test_file)
        hash2 = calculate_file_hash(test_file)
        
        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex length
        
        # Verify against expected hash
        expected_hash = hashlib.sha256(test_content.encode('utf-8')).hexdigest()
        assert hash1 == expected_hash
    
    def test_calculate_file_hash_missing_file(self, temp_dir):
        """Test hash calculation with missing file."""
        missing_file = temp_dir / "nonexistent.txt"
        
        with pytest.raises(PackingError, match="File not found for hashing"):
            calculate_file_hash(missing_file)
    
    def test_calculate_content_hash(self):
        """Test content hash calculation."""
        test_content = b"ProofKit test content"
        
        hash1 = calculate_content_hash(test_content)
        hash2 = calculate_content_hash(test_content)
        
        assert hash1 == hash2
        assert len(hash1) == 64
        
        # Verify against hashlib
        expected_hash = hashlib.sha256(test_content).hexdigest()
        assert hash1 == expected_hash
    
    def test_hash_different_content(self, temp_dir):
        """Test that different content produces different hashes."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        
        file1.write_text("Content A")
        file2.write_text("Content B")
        
        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)
        
        assert hash1 != hash2


class TestManifestCreation:
    """Test manifest creation and root hash calculation."""
    
    def test_create_manifest_basic(self, temp_dir):
        """Test basic manifest creation."""
        # Create test files
        file1 = temp_dir / "test1.txt"
        file2 = temp_dir / "test2.txt"
        file1.write_text("Test content 1")
        file2.write_text("Test content 2")
        
        # Calculate hashes
        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)
        
        # Prepare file info
        file_info = [
            ("inputs/test1.txt", file1, hash1),
            ("outputs/test2.txt", file2, hash2)
        ]
        
        metadata = {"test": "metadata"}
        
        manifest, root_hash = create_manifest(file_info, metadata, deterministic=True)
        
        assert manifest["version"] == "1.0"
        assert manifest["created_at"] == "1980-01-01T00:00:00+00:00"  # Deterministic timestamp
        assert manifest["metadata"] == metadata
        assert len(manifest["files"]) == 2
        assert "inputs/test1.txt" in manifest["files"]
        assert "outputs/test2.txt" in manifest["files"]
        assert manifest["files"]["inputs/test1.txt"]["sha256"] == hash1
        assert manifest["files"]["outputs/test2.txt"]["sha256"] == hash2
        assert manifest["root_hash"] == root_hash
        assert len(root_hash) == 64
    
    def test_create_manifest_non_deterministic(self, temp_dir):
        """Test non-deterministic manifest creation has real timestamp."""
        file1 = temp_dir / "test.txt"
        file1.write_text("Test content")
        hash1 = calculate_file_hash(file1)
        
        file_info = [("test.txt", file1, hash1)]
        metadata = {}
        
        manifest, root_hash = create_manifest(file_info, metadata, deterministic=False)
        
        # Should have a real timestamp, not the fixed one
        assert manifest["created_at"] != "1980-01-01T00:00:00+00:00"
        created_at = datetime.fromisoformat(manifest["created_at"].replace('Z', '+00:00'))
        assert created_at.tzinfo is not None
    
    def test_root_hash_deterministic(self, temp_dir):
        """Test that root hash is deterministic based on file hashes."""
        file1 = temp_dir / "test1.txt"
        file2 = temp_dir / "test2.txt"
        file1.write_text("Content A")
        file2.write_text("Content B")
        
        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)
        
        # Create manifest with files in one order
        file_info_1 = [("a.txt", file1, hash1), ("b.txt", file2, hash2)]
        _, root_hash_1 = create_manifest(file_info_1, {}, deterministic=True)
        
        # Create manifest with files in reverse order
        file_info_2 = [("b.txt", file2, hash2), ("a.txt", file1, hash1)]
        _, root_hash_2 = create_manifest(file_info_2, {}, deterministic=True)
        
        # Root hash should be the same (sorted by archive path)
        assert root_hash_1 == root_hash_2
    
    def test_root_hash_changes_with_content(self, temp_dir):
        """Test that root hash changes when file content changes."""
        file1 = temp_dir / "test.txt"
        
        # First content
        file1.write_text("Original content")
        hash1 = calculate_file_hash(file1)
        file_info_1 = [("test.txt", file1, hash1)]
        _, root_hash_1 = create_manifest(file_info_1, {}, deterministic=True)
        
        # Modified content
        file1.write_text("Modified content")
        hash2 = calculate_file_hash(file1)
        file_info_2 = [("test.txt", file1, hash2)]
        _, root_hash_2 = create_manifest(file_info_2, {}, deterministic=True)
        
        assert root_hash_1 != root_hash_2


class TestFileValidation:
    """Test file validation functions."""
    
    def test_validate_required_files_all_present(self, temp_dir):
        """Test validation when all required files are present."""
        # Create all required files
        files = {}
        for name in ["raw.csv", "spec.json", "normalized.csv", "decision.json", "proof.pdf", "plot.png"]:
            file_path = temp_dir / name
            file_path.write_text(f"Content for {name}")
            files[name] = file_path
        
        errors = validate_required_files(
            raw_csv_path=files["raw.csv"],
            spec_json_path=files["spec.json"],
            normalized_csv_path=files["normalized.csv"],
            decision_json_path=files["decision.json"],
            proof_pdf_path=files["proof.pdf"],
            plot_png_path=files["plot.png"]
        )
        
        assert errors == []
    
    def test_validate_required_files_missing(self, temp_dir):
        """Test validation with missing files."""
        existing_file = temp_dir / "exists.txt"
        existing_file.write_text("I exist")
        missing_file = temp_dir / "missing.txt"
        
        errors = validate_required_files(
            raw_csv_path=existing_file,
            spec_json_path=missing_file,
            normalized_csv_path=None,
            decision_json_path=existing_file,
            proof_pdf_path=existing_file,
            plot_png_path=existing_file
        )
        
        assert len(errors) == 2
        assert any("not found" in error for error in errors)
        assert any("not provided" in error for error in errors)
    
    def test_validate_required_files_not_file(self, temp_dir):
        """Test validation with directories instead of files."""
        directory = temp_dir / "directory"
        directory.mkdir()
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")
        
        errors = validate_required_files(
            raw_csv_path=directory,
            spec_json_path=file_path,
            normalized_csv_path=file_path,
            decision_json_path=file_path,
            proof_pdf_path=file_path,
            plot_png_path=file_path
        )
        
        assert len(errors) == 1
        assert "is not a file" in errors[0]
    
    def test_validate_required_files_unreadable(self, temp_dir):
        """Test validation with unreadable files."""
        # Create file and make it unreadable (on Unix systems)
        unreadable_file = temp_dir / "unreadable.txt"
        unreadable_file.write_text("content")
        
        # Change permissions to make unreadable
        unreadable_file.chmod(0o000)
        
        readable_file = temp_dir / "readable.txt"
        readable_file.write_text("content")
        
        try:
            errors = validate_required_files(
                raw_csv_path=unreadable_file,
                spec_json_path=readable_file,
                normalized_csv_path=readable_file,
                decision_json_path=readable_file,
                proof_pdf_path=readable_file,
                plot_png_path=readable_file
            )
            
            # On some systems, this might not trigger a permission error
            # So we check if there's an error or if it passes
            if len(errors) > 0:
                assert any("cannot be read" in error for error in errors)
        finally:
            # Restore permissions for cleanup
            try:
                unreadable_file.chmod(0o644)
            except:
                pass


class TestEvidenceBundleCreation:
    """Test complete evidence bundle creation."""
    
    def test_create_minimal_evidence_bundle(self, temp_dir):
        """Test creating evidence bundle with minimal fixture data."""
        # Use the minimal fixture data
        fixtures_path = fixtures_dir()
        
        # Copy fixture files to temp directory
        raw_csv = temp_dir / "raw.csv"
        spec_json = temp_dir / "spec.json"
        
        # Load and save fixtures
        csv_data = load_csv_fixture("min_powder.csv")
        spec_data = load_spec_fixture("min_powder_spec.json")
        
        csv_data.to_csv(raw_csv, index=False)
        with open(spec_json, 'w') as f:
            json.dump(spec_data, f, indent=2)
        
        # Create other required files with minimal content
        normalized_csv = temp_dir / "normalized.csv"
        decision_json = temp_dir / "decision.json"
        proof_pdf = temp_dir / "proof.pdf"
        plot_png = temp_dir / "plot.png"
        
        normalized_csv.write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        decision_json.write_text('{"pass": true, "job_id": "test"}')
        proof_pdf.write_bytes(b"%PDF-1.4\nMinimal PDF content for testing")
        plot_png.write_bytes(b"\x89PNG\r\n\x1a\nMinimal PNG content")
        
        # Create evidence bundle
        bundle_path = temp_dir / "evidence.zip"
        
        result_path = create_evidence_bundle(
            raw_csv_path=str(raw_csv),
            spec_json_path=str(spec_json),
            normalized_csv_path=str(normalized_csv),
            decision_json_path=str(decision_json),
            proof_pdf_path=str(proof_pdf),
            plot_png_path=str(plot_png),
            output_path=str(bundle_path),
            job_id="test_minimal",
            deterministic=True
        )
        
        assert result_path == str(bundle_path.absolute())
        assert bundle_path.exists()
        assert bundle_path.stat().st_size > 0
    
    def test_evidence_bundle_zip_structure(self, temp_dir):
        """Test that evidence bundle has correct ZIP structure."""
        # Create minimal files
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Check ZIP contents
        zip_contents = read_zip_file(bundle_path)
        
        expected_files = {
            "inputs/raw_data.csv",
            "inputs/specification.json",
            "outputs/normalized_data.csv",
            "outputs/decision.json",
            "outputs/proof.pdf",
            "outputs/plot.png",
            "manifest.json"
        }
        
        assert set(zip_contents.keys()) == expected_files
        
        # Check that files have content
        for filename, content in zip_contents.items():
            assert len(content) > 0
    
    def test_evidence_bundle_manifest_validation(self, temp_dir):
        """Test that manifest.json contains correct SHA-256 hashes."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        # Calculate expected hashes
        expected_hashes = {}
        file_mapping = {
            "inputs/raw_data.csv": files["raw_csv"],
            "inputs/specification.json": files["spec_json"],
            "outputs/normalized_data.csv": files["normalized_csv"],
            "outputs/decision.json": files["decision_json"],
            "outputs/proof.pdf": files["proof_pdf"],
            "outputs/plot.png": files["plot_png"]
        }
        
        for archive_path, source_path in file_mapping.items():
            expected_hashes[archive_path] = calculate_file_hash(source_path)
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Extract and verify manifest
        zip_contents = read_zip_file_text(bundle_path)
        manifest_text = zip_contents["manifest.json"]
        manifest = json.loads(manifest_text)
        
        assert manifest["version"] == "1.0"
        assert manifest["created_at"] == "1980-01-01T00:00:00+00:00"
        assert "root_hash" in manifest
        assert len(manifest["root_hash"]) == 64
        
        # Verify file hashes
        for archive_path, expected_hash in expected_hashes.items():
            assert archive_path in manifest["files"]
            assert manifest["files"][archive_path]["sha256"] == expected_hash
    
    def test_evidence_bundle_root_hash_calculation(self, temp_dir):
        """Test that root hash equals manifest-of-manifest calculation."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Extract manifest
        zip_contents = read_zip_file_text(bundle_path)
        manifest = json.loads(zip_contents["manifest.json"])
        
        # Manually calculate root hash
        file_hashes = []
        for archive_path in sorted(manifest["files"].keys()):
            file_hashes.append(manifest["files"][archive_path]["sha256"])
        
        combined_hashes = "".join(file_hashes)
        expected_root_hash = hashlib.sha256(combined_hashes.encode('utf-8')).hexdigest()
        
        assert manifest["root_hash"] == expected_root_hash
    
    def test_deterministic_bundle_creation(self, temp_dir):
        """Test that deterministic bundles are identical."""
        files = self._create_minimal_files(temp_dir)
        
        bundle_path_1 = temp_dir / "evidence1.zip"
        bundle_path_2 = temp_dir / "evidence2.zip"
        
        # Create two identical bundles
        for bundle_path in [bundle_path_1, bundle_path_2]:
            create_evidence_bundle(
                raw_csv_path=str(files["raw_csv"]),
                spec_json_path=str(files["spec_json"]),
                normalized_csv_path=str(files["normalized_csv"]),
                decision_json_path=str(files["decision_json"]),
                proof_pdf_path=str(files["proof_pdf"]),
                plot_png_path=str(files["plot_png"]),
                output_path=str(bundle_path),
                job_id="deterministic_test",
                deterministic=True
            )
        
        # Compare file contents
        contents_1 = read_zip_file(bundle_path_1)
        contents_2 = read_zip_file(bundle_path_2)
        
        assert contents_1.keys() == contents_2.keys()
        for filename in contents_1.keys():
            assert contents_1[filename] == contents_2[filename]
    
    def _create_minimal_files(self, temp_dir: Path) -> Dict[str, Path]:
        """Helper to create minimal test files."""
        files = {}
        
        # Raw CSV
        files["raw_csv"] = temp_dir / "raw.csv"
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        # Spec JSON
        files["spec_json"] = temp_dir / "spec.json"
        files["spec_json"].write_text('{"version": "1.0", "spec": {"target_temp_C": 170.0}}')
        
        # Normalized CSV
        files["normalized_csv"] = temp_dir / "normalized.csv"
        files["normalized_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        # Decision JSON
        files["decision_json"] = temp_dir / "decision.json"
        files["decision_json"].write_text('{"pass": true, "job_id": "test"}')
        
        # Proof PDF
        files["proof_pdf"] = temp_dir / "proof.pdf"
        files["proof_pdf"].write_bytes(b"%PDF-1.4\nMinimal PDF for testing")
        
        # Plot PNG
        files["plot_png"] = temp_dir / "plot.png"
        files["plot_png"].write_bytes(b"\x89PNG\r\n\x1a\nMinimal PNG for testing")
        
        return files


class TestTamperDetection:
    """Test tamper detection capabilities."""
    
    def test_tamper_detection_modified_file(self, temp_dir):
        """Test that verify() fails when a file is modified after creation."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        # Create bundle
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Verify bundle is initially valid
        result = verify_evidence_bundle(str(bundle_path))
        assert result["valid"] is True
        
        # Tamper with bundle - modify a file inside
        self._tamper_with_zip_file(bundle_path, "inputs/raw_data.csv", b"TAMPERED,DATA\n2024-01-01T10:00:00Z,999.0\n")
        
        # Verify bundle is now invalid
        result = verify_evidence_bundle(str(bundle_path))
        assert result["valid"] is False
        assert len(result["hash_mismatches"]) > 0
        assert result["hash_mismatches"][0]["file"] == "inputs/raw_data.csv"
    
    def test_tamper_detection_single_byte_change(self, temp_dir):
        """Test detection of single byte changes."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Get original file content
        zip_contents = read_zip_file(bundle_path)
        original_content = zip_contents["outputs/decision.json"]
        
        # Flip one byte
        tampered_content = bytearray(original_content)
        tampered_content[10] = tampered_content[10] ^ 1  # Flip one bit
        
        # Replace file in ZIP
        self._tamper_with_zip_file(bundle_path, "outputs/decision.json", bytes(tampered_content))
        
        # Verify detection
        result = verify_evidence_bundle(str(bundle_path))
        assert result["valid"] is False
        assert any(mismatch["file"] == "outputs/decision.json" for mismatch in result["hash_mismatches"])
    
    def test_tamper_detection_missing_file(self, temp_dir):
        """Test detection of missing files."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Remove a file from the ZIP
        self._remove_file_from_zip(bundle_path, "outputs/plot.png")
        
        # Verify detection
        result = verify_evidence_bundle(str(bundle_path))
        assert result["valid"] is False
        assert "outputs/plot.png" in result["missing_files"]
    
    def test_tamper_detection_extra_file(self, temp_dir):
        """Test behavior with extra files in bundle."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Add an extra file to the ZIP
        with zipfile.ZipFile(bundle_path, 'a') as zipf:
            zipf.writestr("extra_file.txt", "This should not be here")
        
        # Verify - should still be valid as manifest only checks listed files
        result = verify_evidence_bundle(str(bundle_path))
        # The bundle should still be valid as extra files don't break manifest verification
        # The manifest only validates the files it lists
        assert result["valid"] is True
    
    def _tamper_with_zip_file(self, zip_path: Path, file_to_modify: str, new_content: bytes):
        """Helper to modify a specific file in a ZIP archive."""
        # Create a temporary copy
        temp_zip = zip_path.with_suffix('.tmp')
        
        with zipfile.ZipFile(zip_path, 'r') as source_zip:
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as target_zip:
                for item in source_zip.infolist():
                    if item.filename == file_to_modify:
                        # Replace with tampered content
                        target_zip.writestr(item, new_content)
                    else:
                        # Copy original content
                        target_zip.writestr(item, source_zip.read(item.filename))
        
        # Replace original with tampered version
        temp_zip.replace(zip_path)
    
    def _remove_file_from_zip(self, zip_path: Path, file_to_remove: str):
        """Helper to remove a specific file from a ZIP archive."""
        temp_zip = zip_path.with_suffix('.tmp')
        
        with zipfile.ZipFile(zip_path, 'r') as source_zip:
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as target_zip:
                for item in source_zip.infolist():
                    if item.filename != file_to_remove:
                        target_zip.writestr(item, source_zip.read(item.filename))
        
        temp_zip.replace(zip_path)
    
    def _create_minimal_files(self, temp_dir: Path) -> Dict[str, Path]:
        """Helper to create minimal test files."""
        files = {}
        
        files["raw_csv"] = temp_dir / "raw.csv"
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["spec_json"] = temp_dir / "spec.json"
        files["spec_json"].write_text('{"version": "1.0", "spec": {"target_temp_C": 170.0}}')
        
        files["normalized_csv"] = temp_dir / "normalized.csv"
        files["normalized_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["decision_json"] = temp_dir / "decision.json"
        files["decision_json"].write_text('{"pass": true, "job_id": "test"}')
        
        files["proof_pdf"] = temp_dir / "proof.pdf"
        files["proof_pdf"].write_bytes(b"%PDF-1.4\nMinimal PDF for testing")
        
        files["plot_png"] = temp_dir / "plot.png"
        files["plot_png"].write_bytes(b"\x89PNG\r\n\x1a\nMinimal PNG for testing")
        
        return files


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_missing_source_files(self, temp_dir):
        """Test error handling when source files are missing."""
        bundle_path = temp_dir / "evidence.zip"
        
        with pytest.raises(PackingError, match="Validation failed"):
            create_evidence_bundle(
                raw_csv_path=str(temp_dir / "missing.csv"),
                spec_json_path=str(temp_dir / "missing.json"),
                normalized_csv_path=str(temp_dir / "missing_norm.csv"),
                decision_json_path=str(temp_dir / "missing_decision.json"),
                proof_pdf_path=str(temp_dir / "missing.pdf"),
                plot_png_path=str(temp_dir / "missing.png"),
                output_path=str(bundle_path)
            )
    
    def test_invalid_output_path(self, temp_dir):
        """Test error handling with invalid output path."""
        files = self._create_minimal_files(temp_dir)
        
        # Try to write to a directory that doesn't exist and can't be created
        invalid_path = "/invalid/path/that/cannot/be/created/evidence.zip"
        
        with pytest.raises(PackingError):
            create_evidence_bundle(
                raw_csv_path=str(files["raw_csv"]),
                spec_json_path=str(files["spec_json"]),
                normalized_csv_path=str(files["normalized_csv"]),
                decision_json_path=str(files["decision_json"]),
                proof_pdf_path=str(files["proof_pdf"]),
                plot_png_path=str(files["plot_png"]),
                output_path=invalid_path
            )
    
    def test_verify_nonexistent_bundle(self, temp_dir):
        """Test verification of non-existent bundle."""
        bundle_path = temp_dir / "nonexistent.zip"
        
        with pytest.raises(PackingError, match="not found"):
            verify_evidence_bundle(str(bundle_path))
    
    def test_verify_invalid_zip(self, temp_dir):
        """Test verification of invalid ZIP file."""
        bundle_path = temp_dir / "invalid.zip"
        bundle_path.write_text("This is not a ZIP file")
        
        with pytest.raises(PackingError, match="verification failed"):
            verify_evidence_bundle(str(bundle_path))
    
    def test_verify_missing_manifest(self, temp_dir):
        """Test verification of ZIP without manifest."""
        bundle_path = temp_dir / "no_manifest.zip"
        
        with zipfile.ZipFile(bundle_path, 'w') as zipf:
            zipf.writestr("some_file.txt", "content")
        
        with pytest.raises(PackingError, match="Manifest not found"):
            verify_evidence_bundle(str(bundle_path))
    
    def test_verify_corrupted_manifest(self, temp_dir):
        """Test verification of ZIP with corrupted manifest."""
        bundle_path = temp_dir / "corrupt_manifest.zip"
        
        with zipfile.ZipFile(bundle_path, 'w') as zipf:
            zipf.writestr("manifest.json", "This is not valid JSON")
        
        with pytest.raises(PackingError, match="verification failed"):
            verify_evidence_bundle(str(bundle_path))
    
    def test_extract_nonexistent_bundle(self, temp_dir):
        """Test extraction of non-existent bundle."""
        bundle_path = temp_dir / "nonexistent.zip"
        extract_dir = temp_dir / "extract"
        
        with pytest.raises(PackingError, match="not found"):
            extract_evidence_bundle(str(bundle_path), str(extract_dir))
    
    def test_extract_invalid_zip(self, temp_dir):
        """Test extraction of invalid ZIP file."""
        bundle_path = temp_dir / "invalid.zip"
        bundle_path.write_text("Not a ZIP file")
        extract_dir = temp_dir / "extract"
        
        with pytest.raises(PackingError, match="extraction failed"):
            extract_evidence_bundle(str(bundle_path), str(extract_dir))
    
    def _create_minimal_files(self, temp_dir: Path) -> Dict[str, Path]:
        """Helper to create minimal test files."""
        files = {}
        
        files["raw_csv"] = temp_dir / "raw.csv"
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["spec_json"] = temp_dir / "spec.json"
        files["spec_json"].write_text('{"version": "1.0", "spec": {"target_temp_C": 170.0}}')
        
        files["normalized_csv"] = temp_dir / "normalized.csv"
        files["normalized_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["decision_json"] = temp_dir / "decision.json"
        files["decision_json"].write_text('{"pass": true, "job_id": "test"}')
        
        files["proof_pdf"] = temp_dir / "proof.pdf"
        files["proof_pdf"].write_bytes(b"%PDF-1.4\nMinimal PDF for testing")
        
        files["plot_png"] = temp_dir / "plot.png"
        files["plot_png"].write_bytes(b"\x89PNG\r\n\x1a\nMinimal PNG for testing")
        
        return files


class TestBundleExtraction:
    """Test evidence bundle extraction functionality."""
    
    def test_extract_valid_bundle(self, temp_dir):
        """Test extraction of valid evidence bundle."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        extract_dir = temp_dir / "extracted"
        
        # Create bundle
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Extract bundle
        extracted_files = extract_evidence_bundle(str(bundle_path), str(extract_dir))
        
        # Verify extraction
        assert len(extracted_files) == 7  # 6 data files + manifest
        
        expected_files = {
            "inputs/raw_data.csv",
            "inputs/specification.json", 
            "outputs/normalized_data.csv",
            "outputs/decision.json",
            "outputs/proof.pdf",
            "outputs/plot.png",
            "manifest.json"
        }
        
        assert set(extracted_files.keys()) == expected_files
        
        # Verify extracted files exist and have content
        for archive_path, extracted_path in extracted_files.items():
            extracted_file = Path(extracted_path)
            assert extracted_file.exists()
            assert extracted_file.stat().st_size > 0
    
    def test_extract_verify_file_contents(self, temp_dir):
        """Test that extracted files have correct content."""
        files = self._create_minimal_files(temp_dir)
        bundle_path = temp_dir / "evidence.zip"
        extract_dir = temp_dir / "extracted"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized_csv"]),
            decision_json_path=str(files["decision_json"]),
            proof_pdf_path=str(files["proof_pdf"]),
            plot_png_path=str(files["plot_png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        extracted_files = extract_evidence_bundle(str(bundle_path), str(extract_dir))
        
        # Compare content of original raw CSV with extracted version
        original_content = files["raw_csv"].read_text()
        extracted_content = Path(extracted_files["inputs/raw_data.csv"]).read_text()
        assert original_content == extracted_content
        
        # Verify manifest exists and is valid JSON
        manifest_content = Path(extracted_files["manifest.json"]).read_text()
        manifest = json.loads(manifest_content)
        assert manifest["version"] == "1.0"
        assert "root_hash" in manifest
    
    def _create_minimal_files(self, temp_dir: Path) -> Dict[str, Path]:
        """Helper to create minimal test files."""
        files = {}
        
        files["raw_csv"] = temp_dir / "raw.csv"
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["spec_json"] = temp_dir / "spec.json"
        files["spec_json"].write_text('{"version": "1.0", "spec": {"target_temp_C": 170.0}}')
        
        files["normalized_csv"] = temp_dir / "normalized.csv"
        files["normalized_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["decision_json"] = temp_dir / "decision.json"
        files["decision_json"].write_text('{"pass": true, "job_id": "test"}')
        
        files["proof_pdf"] = temp_dir / "proof.pdf"
        files["proof_pdf"].write_bytes(b"%PDF-1.4\nMinimal PDF for testing")
        
        files["plot_png"] = temp_dir / "plot.png"
        files["plot_png"].write_bytes(b"\x89PNG\r\n\x1a\nMinimal PNG for testing")
        
        return files


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_files(self, temp_dir):
        """Test handling of empty files."""
        files = {}
        
        # Create empty files
        for name in ["raw.csv", "spec.json", "normalized.csv", "decision.json", "proof.pdf", "plot.png"]:
            files[name] = temp_dir / name
            files[name].write_text("")  # Empty file
        
        bundle_path = temp_dir / "evidence.zip"
        
        # Should still create bundle successfully
        create_evidence_bundle(
            raw_csv_path=str(files["raw.csv"]),
            spec_json_path=str(files["spec.json"]),
            normalized_csv_path=str(files["normalized.csv"]),
            decision_json_path=str(files["decision.json"]),
            proof_pdf_path=str(files["proof.pdf"]),
            plot_png_path=str(files["plot.png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        assert bundle_path.exists()
        
        # Verify the bundle
        result = verify_evidence_bundle(str(bundle_path))
        assert result["valid"] is True
    
    def test_large_file_names(self, temp_dir):
        """Test handling of files with long paths."""
        # Create files with very long names
        long_name = "a" * 200 + ".csv"
        files = {}
        
        files["raw_csv"] = temp_dir / long_name
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        for name in ["spec.json", "normalized.csv", "decision.json", "proof.pdf", "plot.png"]:
            files[name] = temp_dir / name
            files[name].write_text("content")
        
        bundle_path = temp_dir / "evidence.zip"
        
        # Should handle long file names gracefully
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec.json"]),
            normalized_csv_path=str(files["normalized.csv"]),
            decision_json_path=str(files["decision.json"]),
            proof_pdf_path=str(files["proof.pdf"]),
            plot_png_path=str(files["plot.png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        assert bundle_path.exists()
    
    def test_unicode_content(self, temp_dir):
        """Test handling of files with Unicode content."""
        files = {}
        
        # Create files with Unicode content
        files["raw_csv"] = temp_dir / "raw.csv"
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0°C\n", encoding='utf-8')
        
        files["spec_json"] = temp_dir / "spec.json"
        files["spec_json"].write_text('{"version": "1.0", "comment": "Testing with 中文 and émojis 🧪"}', encoding='utf-8')
        
        for name in ["normalized.csv", "decision.json", "proof.pdf", "plot.png"]:
            files[name] = temp_dir / name
            files[name].write_text("content with unicode: 测试 🔬", encoding='utf-8')
        
        bundle_path = temp_dir / "evidence.zip"
        
        create_evidence_bundle(
            raw_csv_path=str(files["raw_csv"]),
            spec_json_path=str(files["spec_json"]),
            normalized_csv_path=str(files["normalized.csv"]),
            decision_json_path=str(files["decision.json"]),
            proof_pdf_path=str(files["proof.pdf"]),
            plot_png_path=str(files["plot.png"]),
            output_path=str(bundle_path),
            deterministic=True
        )
        
        # Verify Unicode content is preserved
        result = verify_evidence_bundle(str(bundle_path))
        assert result["valid"] is True
        
        # Extract and verify Unicode content
        extract_dir = temp_dir / "extracted"
        extracted_files = extract_evidence_bundle(str(bundle_path), str(extract_dir))
        
        extracted_spec = Path(extracted_files["inputs/specification.json"]).read_text(encoding='utf-8')
        assert "中文" in extracted_spec
        assert "🧪" in extracted_spec
    
    def test_metadata_variations(self, temp_dir):
        """Test different metadata configurations."""
        files = self._create_minimal_files(temp_dir)
        
        # Test with different job IDs
        for job_id in [None, "", "test_job_123", "job-with-dashes", "job_with_unicode_测试"]:
            bundle_path = temp_dir / f"evidence_{job_id or 'none'}.zip"
            
            create_evidence_bundle(
                raw_csv_path=str(files["raw_csv"]),
                spec_json_path=str(files["spec_json"]),
                normalized_csv_path=str(files["normalized_csv"]),
                decision_json_path=str(files["decision_json"]),
                proof_pdf_path=str(files["proof_pdf"]),
                plot_png_path=str(files["plot_png"]),
                output_path=str(bundle_path),
                job_id=job_id,
                deterministic=True
            )
            
            # Verify bundle and metadata
            zip_contents = read_zip_file_text(bundle_path)
            manifest = json.loads(zip_contents["manifest.json"])
            
            expected_job_id = job_id or "unknown"
            assert manifest["metadata"]["job_id"] == expected_job_id
    
    def _create_minimal_files(self, temp_dir: Path) -> Dict[str, Path]:
        """Helper to create minimal test files."""
        files = {}
        
        files["raw_csv"] = temp_dir / "raw.csv"
        files["raw_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["spec_json"] = temp_dir / "spec.json"
        files["spec_json"].write_text('{"version": "1.0", "spec": {"target_temp_C": 170.0}}')
        
        files["normalized_csv"] = temp_dir / "normalized.csv"
        files["normalized_csv"].write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
        
        files["decision_json"] = temp_dir / "decision.json"
        files["decision_json"].write_text('{"pass": true, "job_id": "test"}')
        
        files["proof_pdf"] = temp_dir / "proof.pdf"
        files["proof_pdf"].write_bytes(b"%PDF-1.4\nMinimal PDF for testing")
        
        files["plot_png"] = temp_dir / "plot.png"
        files["plot_png"].write_bytes(b"\x89PNG\r\n\x1a\nMinimal PNG for testing")
        
        return files