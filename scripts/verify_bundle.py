#!/usr/bin/env python3
"""Evidence bundle verifier with strong assertions."""

import sys
import json
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def compute_root_hash(manifest: Dict) -> str:
    """Compute root hash using deterministic algorithm matching pack.py."""
    concat_str = ""
    
    # Handle both old format (files as list) and new format (files as dict)
    if isinstance(manifest.get("files"), dict):
        for path in sorted(manifest["files"].keys()):
            file_info = manifest["files"][path]
            size = file_info.get("size_bytes", 0)
            concat_str += f"sha256 {size} {path}\n"
    else:
        for file_entry in sorted(manifest.get("files", []), key=lambda x: x.get("name", "")):
            size = file_entry.get("size", 0)
            path = file_entry.get("name", "")
            concat_str += f"sha256 {size} {path}\n"
    
    return hashlib.sha256(concat_str.encode()).hexdigest()

def verify_bundle(bundle_path: str) -> Dict:
    """Verify evidence bundle integrity with comprehensive assertions."""
    result = {
        "path": bundle_path,
        "exists": Path(bundle_path).exists(),
        "valid_zip": False,
        "manifest_valid": False,
        "hashes_match": False,
        "root_hash": None,
        "root_hash_match": False,
        "root_hash_calculated": None,
        "decision_match": False,
        "api_status": None,
        "local_status": None,
        "files": [],
        "assertions_passed": False,
        "validation_gates_checked": False,
        "pdf_validation_status": None,
        "contract_violations": []
    }
    
    if not result["exists"]:
        return result
    
    try:
        with zipfile.ZipFile(bundle_path, 'r') as zf:
            result["valid_zip"] = True
            result["files"] = zf.namelist()
            
            # Extract to temp directory
            extract_dir = Path(bundle_path).parent / "bundle_extract"
            extract_dir.mkdir(exist_ok=True)
            zf.extractall(extract_dir)
            
            # Check for manifest
            manifest_path = extract_dir / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                result["manifest_valid"] = True
                
                # Verify file hashes - handle both dict and list formats
                all_match = True
                hash_mismatches = []
                
                files_data = manifest.get("files", {})
                if isinstance(files_data, dict):
                    # New format: files as dict
                    for file_path, file_info in files_data.items():
                        expected_hash = file_info["sha256"]
                        
                        extracted_file = extract_dir / file_path
                        if extracted_file.exists():
                            actual_hash = compute_sha256(extracted_file)
                            if actual_hash != expected_hash:
                                all_match = False
                                hash_mismatches.append({
                                    "file": file_path,
                                    "expected": expected_hash[:16],
                                    "actual": actual_hash[:16]
                                })
                else:
                    # Old format: files as list
                    for file_entry in files_data:
                        file_name = file_entry["name"]
                        expected_hash = file_entry["sha256"]
                        
                        file_path = extract_dir / file_name
                        if file_path.exists():
                            actual_hash = compute_sha256(file_path)
                            if actual_hash != expected_hash:
                                all_match = False
                                hash_mismatches.append({
                                    "file": file_name,
                                    "expected": expected_hash[:16],
                                    "actual": actual_hash[:16]
                                })
                
                result["hashes_match"] = all_match
                if hash_mismatches:
                    result["hash_mismatches"] = hash_mismatches
                
                # Verify root hash (check both old and new field names)
                result["root_hash"] = manifest.get("root_sha256") or manifest.get("root_hash")
                if result["root_hash"]:
                    computed_root = compute_root_hash(manifest)
                    result["root_hash_calculated"] = computed_root
                    result["root_hash_match"] = (computed_root == result["root_hash"])
                    if not result["root_hash_match"]:
                        result["computed_root_hash"] = computed_root[:16]
                        result["expected_root_hash"] = result["root_hash"][:16]
            
            # Load and verify decision
            decision_path = extract_dir / "decision.json"
            normalized_path = extract_dir / "normalized.csv"
            spec_path = extract_dir / "spec.json"
            
            if decision_path.exists():
                decision = json.loads(decision_path.read_text())
                result["api_status"] = decision.get("outcome")
                
                # Try to recompute locally if we have the files
                if normalized_path.exists() and spec_path.exists():
                    try:
                        # Import decision engine
                        sys.path.insert(0, str(Path(__file__).parent.parent))
                        from core.decide import make_decision
                        
                        df = pd.read_csv(normalized_path)
                        spec = json.loads(spec_path.read_text())
                        
                        # Recompute decision
                        local_decision = make_decision(df, spec)
                        
                        # Compare outcomes
                        result["local_status"] = local_decision.get("outcome")
                        result["decision_match"] = (
                            result["local_status"] == result["api_status"]
                        )
                        
                        # Compare key metrics
                        metric_diffs = []
                        if "metrics" in decision and "metrics" in local_decision:
                            for key in decision["metrics"]:
                                if key in local_decision["metrics"]:
                                    orig = decision["metrics"][key]
                                    local = local_decision["metrics"][key]
                                    # Allow small floating point differences
                                    if isinstance(orig, (int, float)) and isinstance(local, (int, float)):
                                        if abs(orig - local) > 0.01:
                                            metric_diffs.append({
                                                "metric": key,
                                                "api": orig,
                                                "local": local
                                            })
                                    elif orig != local:
                                        metric_diffs.append({
                                            "metric": key,
                                            "api": orig,
                                            "local": local
                                        })
                        
                        if metric_diffs:
                            result["metric_diffs"] = metric_diffs
                        
                    except Exception as e:
                        result["recompute_error"] = str(e)
                
                # Check PDF validation gates if PDF is present
                pdf_path = extract_dir / "outputs" / "proof.pdf"
                if pdf_path.exists():
                    try:
                        # Check for PDF validation issues
                        from core.render_pdf import check_pdf_validation_gates, PDFValidationError
                        from core.models import DecisionResult
                        
                        # Create minimal decision result for gate checking
                        decision_data = json.loads(decision_path.read_text()) if decision_path.exists() else {}
                        
                        # Mock decision result for validation
                        class MockDecision:
                            def __init__(self, data):
                                self.status = data.get("status", "PASS" if data.get("pass", False) else "FAIL")
                                self.pass_ = data.get("pass", False)
                        
                        mock_decision = MockDecision(decision_data)
                        
                        # Check validation gates
                        gate_result = check_pdf_validation_gates(mock_decision)
                        result["validation_gates_checked"] = True
                        result["pdf_validation_status"] = gate_result.get("gate_status", "UNKNOWN")
                        
                        # Add contract violation if PDF should be blocked but exists
                        if gate_result.get("should_block", False):
                            result["contract_violations"].append("PDF exists but validation gates indicate it should be blocked")
                            
                    except PDFValidationError as e:
                        result["validation_gates_checked"] = True
                        result["pdf_validation_status"] = "BLOCKED"
                        result["pdf_validation_error"] = str(e)
                    except Exception as e:
                        result["pdf_validation_check_error"] = str(e)
            
            # Clean up extraction
            import shutil
            shutil.rmtree(extract_dir)
            
    except zipfile.BadZipFile:
        result["valid_zip"] = False
        result["error"] = "Invalid ZIP file"
    except Exception as e:
        result["error"] = str(e)
    
    # Perform assertions
    assertions_passed = True
    assertions = []
    
    # Assert valid ZIP
    if not result["valid_zip"]:
        assertions.append("Bundle must be valid ZIP file")
        assertions_passed = False
    
    # Assert manifest exists and is valid
    if not result["manifest_valid"]:
        assertions.append("Manifest must exist and be valid JSON")
        assertions_passed = False
    
    # Assert hashes match
    if not result["hashes_match"]:
        assertions.append("All file hashes must match manifest")
        assertions_passed = False
    
    # Assert root hash matches
    if result["root_hash"] and not result["root_hash_match"]:
        assertions.append("Root hash must match computed value")
        assertions_passed = False
    
    # Assert decision matches
    if result["api_status"] and result["local_status"] and not result["decision_match"]:
        assertions.append(f"API status ({result['api_status']}) must match local recompute ({result['local_status']})")
        assertions_passed = False
    
    # Assert no contract violations
    if result["contract_violations"]:
        for violation in result["contract_violations"]:
            assertions.append(f"Contract violation: {violation}")
        assertions_passed = False
    
    # Assert PDF validation if checked
    if result["validation_gates_checked"] and result.get("pdf_validation_error"):
        assertions.append(f"PDF validation error: {result['pdf_validation_error']}")
        assertions_passed = False
    
    result["assertions_passed"] = assertions_passed
    result["assertions"] = assertions
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_bundle.py <bundle_path>")
        sys.exit(1)
    
    bundle_path = sys.argv[1]
    result = verify_bundle(bundle_path)
    
    print(json.dumps(result, indent=2))
    
    # Quick summary with assertions
    print("\n=== Bundle Verification Summary ===")
    print(f"File: {bundle_path}")
    print(f"Valid ZIP: {'✓' if result['valid_zip'] else '✗'}")
    
    if result['valid_zip']:
        print(f"Files: {len(result['files'])}")
        print(f"Manifest: {'✓' if result['manifest_valid'] else '✗'}")
        print(f"Hashes: {'✓' if result['hashes_match'] else '✗'}")
        print(f"Root Hash: {result['root_hash'][:16]}..." if result['root_hash'] else "Root Hash: None")
        print(f"Root Hash Match: {'✓' if result['root_hash_match'] else '✗'}")
        print(f"API Status: {result['api_status']}")
        print(f"Local Status: {result['local_status']}")
        print(f"Decision Match: {'✓' if result['decision_match'] else '✗'}")
        
        # PDF Validation Gates
        if result['validation_gates_checked']:
            print(f"PDF Validation: {result['pdf_validation_status']}")
        
        # Contract Violations
        if result['contract_violations']:
            print(f"Contract Violations: {len(result['contract_violations'])}")
            for violation in result['contract_violations']:
                print(f"  - {violation}")
        
        if not result['assertions_passed']:
            print("\n⚠️ Assertions Failed:")
            for assertion in result.get('assertions', []):
                print(f"  - {assertion}")
        else:
            print("\n✅ All assertions passed")
    
    # Exit with error if assertions failed
    if not result['assertions_passed']:
        sys.exit(1)

if __name__ == "__main__":
    main()