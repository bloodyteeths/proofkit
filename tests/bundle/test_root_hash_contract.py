#!/usr/bin/env python3
"""Test root hash contract between pack and verify."""

import hashlib
import tempfile
import json
from pathlib import Path

def test_root_hash_computation():
    """Test root hash is computed identically."""
    
    # Mock manifest structure
    files_dict = {
        "inputs/data.csv": {"sha256": "abc123", "size_bytes": 1000},
        "outputs/decision.json": {"sha256": "def456", "size_bytes": 500}
    }
    
    # Expected computation
    concat_str = ""
    for path in sorted(files_dict.keys()):
        info = files_dict[path]
        concat_str += f"sha256 {info['size_bytes']} {path}\n"
    
    expected_hash = hashlib.sha256(concat_str.encode()).hexdigest()
    
    # Test verify_bundle computation
    from scripts.verify_bundle import compute_root_hash
    
    manifest = {"files": files_dict}
    computed_hash = compute_root_hash(manifest)
    
    assert computed_hash == expected_hash, f"Hash mismatch: {computed_hash[:16]} != {expected_hash[:16]}"

def test_manifest_format():
    """Test manifest includes root_sha256."""
    from core.pack import create_manifest
    
    # Mock file info
    file_info = [
        ("inputs/data.csv", Path("/tmp/data.csv"), "abc123"),
        ("outputs/decision.json", Path("/tmp/decision.json"), "def456")
    ]
    
    # Create temp files for size calculation
    for _, path, _ in file_info:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    
    metadata = {"job_id": "test123"}
    manifest, root_hash = create_manifest(file_info, metadata, deterministic=True)
    
    assert "root_sha256" in manifest
    assert manifest["root_sha256"] == root_hash
    
    # Cleanup
    for _, path, _ in file_info:
        path.unlink(missing_ok=True)

if __name__ == "__main__":
    test_root_hash_computation()
    test_manifest_format()
    print("✓ All root hash tests passed")