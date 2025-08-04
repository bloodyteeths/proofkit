#!/usr/bin/env python3
"""
ProofKit Evidence Bundle Creation Example

Demonstrates how to create tamper-evident evidence bundles using the pack.py module.
This example shows the complete workflow from individual proof components to
a verified evidence bundle suitable for compliance workflows.

Usage:
    python examples/pack_example.py
"""

import sys
import tempfile
from pathlib import Path

# Add core modules to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pack import create_evidence_bundle, verify_evidence_bundle, extract_evidence_bundle


def create_example_evidence_bundle():
    """
    Create an example evidence bundle using the provided example files.
    
    This demonstrates the M4 milestone requirements:
    - Zip manifest with SHA-256 per file + root hash
    - evidence.zip (inputs, normalized.csv, decision.json, plot.png, manifest with SHA-256)
    - Tamper-evident bundle for verification workflows
    """
    print("ProofKit Evidence Bundle Creation Example")
    print("=" * 50)
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    examples_dir = Path(__file__).parent
    outputs_dir = examples_dir / "outputs"
    temp_dir = Path(tempfile.mkdtemp())
    
    print(f"Working directory: {temp_dir}")
    
    # Create example raw CSV data
    raw_csv_path = temp_dir / "cure_temperature_log.csv"
    raw_csv_content = """# Job: example_batch_001
# Equipment: PMT Cure Oven #3
# Operator: Quality Inspector
# Date: 2024-01-15
# Part: Aluminum Widget Frame
# Powder: Polyester White RAL9010
timestamp,pmt_sensor_1,pmt_sensor_2,oven_air_temp
2024-01-15T08:00:00Z,22.1,22.3,21.8
2024-01-15T08:00:30Z,28.5,28.2,27.9
2024-01-15T08:01:00Z,45.2,44.8,45.1
2024-01-15T08:01:30Z,67.3,66.9,67.0
2024-01-15T08:02:00Z,89.1,88.7,88.9
2024-01-15T08:02:30Z,112.4,111.8,112.1
2024-01-15T08:03:00Z,138.2,137.6,137.9
2024-01-15T08:03:30Z,165.7,165.1,165.4
2024-01-15T08:04:00Z,179.8,179.2,179.5
2024-01-15T08:04:30Z,180.1,179.8,180.0
2024-01-15T08:05:00Z,180.3,180.1,180.2
2024-01-15T08:05:30Z,180.5,180.3,180.4
2024-01-15T08:06:00Z,180.2,180.0,180.1
2024-01-15T08:06:30Z,180.4,180.2,180.3
2024-01-15T08:07:00Z,180.1,179.9,180.0
2024-01-15T08:07:30Z,180.3,180.1,180.2
2024-01-15T08:08:00Z,180.0,179.8,179.9
2024-01-15T08:08:30Z,180.2,180.0,180.1
2024-01-15T08:09:00Z,179.9,179.7,179.8
2024-01-15T08:09:30Z,180.1,179.9,180.0
2024-01-15T08:10:00Z,180.3,180.1,180.2
2024-01-15T08:10:30Z,180.0,179.8,179.9
2024-01-15T08:11:00Z,179.8,179.6,179.7
2024-01-15T08:11:30Z,180.0,179.8,179.9
2024-01-15T08:12:00Z,180.2,180.0,180.1
2024-01-15T08:12:30Z,179.9,179.7,179.8
2024-01-15T08:13:00Z,180.1,179.9,180.0
2024-01-15T08:13:30Z,180.3,180.1,180.2
2024-01-15T08:14:00Z,180.0,179.8,179.9
2024-01-15T08:14:30Z,179.7,179.5,179.6
2024-01-15T08:15:00Z,179.2,179.0,179.1
"""
    raw_csv_path.write_text(raw_csv_content)
    
    # Create normalized CSV (would normally come from normalize.py)
    normalized_csv_path = temp_dir / "normalized.csv"
    normalized_csv_content = """timestamp,pmt_sensor_1,pmt_sensor_2,oven_air_temp
2024-01-15T08:00:00+00:00,22.1,22.3,21.8
2024-01-15T08:00:30+00:00,28.5,28.2,27.9
2024-01-15T08:01:00+00:00,45.2,44.8,45.1
2024-01-15T08:01:30+00:00,67.3,66.9,67.0
2024-01-15T08:02:00+00:00,89.1,88.7,88.9
2024-01-15T08:02:30+00:00,112.4,111.8,112.1
2024-01-15T08:03:00+00:00,138.2,137.6,137.9
2024-01-15T08:03:30+00:00,165.7,165.1,165.4
2024-01-15T08:04:00+00:00,179.8,179.2,179.5
2024-01-15T08:04:30+00:00,180.1,179.8,180.0
2024-01-15T08:05:00+00:00,180.3,180.1,180.2
2024-01-15T08:05:30+00:00,180.5,180.3,180.4
2024-01-15T08:06:00+00:00,180.2,180.0,180.1
2024-01-15T08:06:30+00:00,180.4,180.2,180.3
2024-01-15T08:07:00+00:00,180.1,179.9,180.0
2024-01-15T08:07:30+00:00,180.3,180.1,180.2
2024-01-15T08:08:00+00:00,180.0,179.8,179.9
2024-01-15T08:08:30+00:00,180.2,180.0,180.1
2024-01-15T08:09:00+00:00,179.9,179.7,179.8
2024-01-15T08:09:30+00:00,180.1,179.9,180.0
2024-01-15T08:10:00+00:00,180.3,180.1,180.2
2024-01-15T08:10:30+00:00,180.0,179.8,179.9
2024-01-15T08:11:00+00:00,179.8,179.6,179.7
2024-01-15T08:11:30+00:00,180.0,179.8,179.9
2024-01-15T08:12:00+00:00,180.2,180.0,180.1
2024-01-15T08:12:30+00:00,179.9,179.7,179.8
2024-01-15T08:13:00+00:00,180.1,179.9,180.0
2024-01-15T08:13:30+00:00,180.3,180.1,180.2
2024-01-15T08:14:00+00:00,180.0,179.8,179.9
2024-01-15T08:14:30+00:00,179.7,179.5,179.6
2024-01-15T08:15:00+00:00,179.2,179.0,179.1
"""
    normalized_csv_path.write_text(normalized_csv_content)
    
    # Use existing example files
    spec_json_path = examples_dir / "spec_example.json"
    decision_json_path = outputs_dir / "decision_pass.json"
    proof_pdf_path = outputs_dir / "proof_pass.pdf"
    plot_png_path = outputs_dir / "proof_plot_pass.png"
    
    # Verify all required files exist
    required_files = {
        "Raw CSV": raw_csv_path,
        "Spec JSON": spec_json_path,
        "Normalized CSV": normalized_csv_path,
        "Decision JSON": decision_json_path,
        "Proof PDF": proof_pdf_path,
        "Plot PNG": plot_png_path
    }
    
    missing_files = []
    for name, path in required_files.items():
        if not path.exists():
            missing_files.append(f"{name}: {path}")
    
    if missing_files:
        print("❌ Missing required files:")
        for missing in missing_files:
            print(f"   {missing}")
        return False
    
    print("\n1. Input Files Validation")
    print("-" * 25)
    for name, path in required_files.items():
        size = path.stat().st_size
        print(f"✅ {name}: {path.name} ({size:,} bytes)")
    
    # Create evidence bundle
    print("\n2. Creating Evidence Bundle")
    print("-" * 30)
    
    bundle_path = temp_dir / "example_evidence.zip"
    
    try:
        result_path = create_evidence_bundle(
            raw_csv_path=str(raw_csv_path),
            spec_json_path=str(spec_json_path),
            normalized_csv_path=str(normalized_csv_path),
            decision_json_path=str(decision_json_path),
            proof_pdf_path=str(proof_pdf_path),
            plot_png_path=str(plot_png_path),
            output_path=str(bundle_path),
            job_id="example_batch_001"
        )
        
        bundle_size = Path(result_path).stat().st_size
        print(f"✅ Evidence bundle created successfully")
        print(f"   📦 Path: {result_path}")
        print(f"   📏 Size: {bundle_size:,} bytes")
        print(f"   🏷️  Job ID: example_batch_001")
        
    except Exception as e:
        print(f"❌ Failed to create evidence bundle: {e}")
        return False
    
    # Verify bundle integrity
    print("\n3. Bundle Integrity Verification")
    print("-" * 35)
    
    try:
        verification = verify_evidence_bundle(result_path)
        
        if verification["valid"]:
            print("✅ Bundle verification PASSED")
            print(f"   🔒 Root hash: {verification['root_hash'][:32]}...")
            print(f"   📁 Files verified: {verification['files_verified']}/{verification['files_total']}")
            print(f"   ✅ Manifest integrity: OK")
            print(f"   ✅ File integrity: OK")
        else:
            print("❌ Bundle verification FAILED")
            if verification['hash_mismatches']:
                print(f"   Hash mismatches: {len(verification['hash_mismatches'])}")
            if verification['missing_files']:
                print(f"   Missing files: {len(verification['missing_files'])}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to verify bundle: {e}")
        return False
    
    # Extract and inspect bundle contents
    print("\n4. Bundle Contents Inspection")
    print("-" * 33)
    
    try:
        extract_dir = temp_dir / "bundle_contents"
        extracted_files = extract_evidence_bundle(result_path, str(extract_dir))
        
        print(f"✅ Bundle extracted to: {extract_dir}")
        print("   📂 Bundle structure:")
        
        # Read and display manifest
        import json
        manifest_path = extract_dir / "manifest.json"
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        print(f"      📋 manifest.json (v{manifest['version']})")
        print(f"         Created: {manifest['created_at']}")
        print(f"         Root hash: {manifest['root_hash'][:16]}...")
        
        print("      📁 inputs/")
        for file_path in ["inputs/raw_data.csv", "inputs/specification.json"]:
            if file_path in manifest['files']:
                file_info = manifest['files'][file_path]
                print(f"         📄 {file_path.split('/')[-1]} ({file_info['size_bytes']:,} bytes)")
                print(f"            SHA-256: {file_info['sha256'][:16]}...")
        
        print("      📁 outputs/")
        for file_path in ["outputs/normalized_data.csv", "outputs/decision.json", "outputs/proof.pdf", "outputs/plot.png"]:
            if file_path in manifest['files']:
                file_info = manifest['files'][file_path]
                print(f"         📄 {file_path.split('/')[-1]} ({file_info['size_bytes']:,} bytes)")
                print(f"            SHA-256: {file_info['sha256'][:16]}...")
        
    except Exception as e:
        print(f"❌ Failed to extract bundle: {e}")
        return False
    
    # Summary
    print("\n" + "=" * 50)
    print("EVIDENCE BUNDLE CREATION SUMMARY")
    print("=" * 50)
    print(f"✅ Bundle created: {Path(result_path).name}")
    print(f"✅ Bundle verified: Integrity checks passed")
    print(f"✅ Bundle extracted: Contents inspected")
    print(f"📦 Bundle location: {result_path}")
    print(f"🔒 Root hash: {verification['root_hash']}")
    print("\nThe evidence bundle is ready for:")
    print("  • Compliance workflows")
    print("  • Third-party verification")
    print("  • Long-term archival")
    print("  • Audit trail documentation")
    
    print(f"\n📚 CLI Usage Examples:")
    print(f"   # Verify bundle")
    print(f"   python -m cli.main verify {result_path}")
    print(f"   # Extract bundle")  
    print(f"   python -m cli.main extract {result_path}")
    
    return True


if __name__ == "__main__":
    success = create_example_evidence_bundle()
    sys.exit(0 if success else 1)