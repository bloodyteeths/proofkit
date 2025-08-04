#!/usr/bin/env python3
"""
ProofKit PDF Generation Example

Demonstrates how to generate proof certificates using the render_pdf module.
This example shows the complete workflow from loading spec and decision data
to generating a professional PDF certificate.

Usage:
    python3 examples/pdf_example.py
"""

import json
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import SpecV1, DecisionResult
from core.render_pdf import generate_proof_pdf, compute_pdf_hash


def main():
    """Generate example proof PDFs for all test cases."""
    print("ProofKit PDF Generation Example")
    print("=" * 40)
    
    # Define test cases
    test_cases = [
        {
            "name": "PASS - Continuous Hold",
            "spec_file": "spec_example.json",
            "decision_file": "outputs/decision_pass.json",
            "plot_file": "outputs/proof_plot_pass.png",
            "output_file": "outputs/proof_pass.pdf"
        },
        {
            "name": "FAIL - Short Hold Time",
            "spec_file": "spec_example.json",
            "decision_file": "outputs/decision_fail_short_hold.json",
            "plot_file": "outputs/proof_plot_fail_short_hold.png",
            "output_file": "outputs/proof_fail_short_hold.pdf"
        },
        {
            "name": "FAIL - No Threshold Reached",
            "spec_file": "spec_example.json",
            "decision_file": "outputs/decision_fail_no_threshold.json",
            "plot_file": "outputs/proof_plot_fail_no_threshold.png",
            "output_file": "outputs/proof_fail_no_threshold.pdf"
        }
    ]
    
    examples_dir = Path(__file__).parent
    
    for test_case in test_cases:
        print(f"\nGenerating: {test_case['name']}")
        print("-" * 30)
        
        try:
            # Load specification
            spec_path = examples_dir / test_case['spec_file']
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            # Load decision result
            decision_path = examples_dir / test_case['decision_file']
            with open(decision_path, 'r') as f:
                decision_data = json.load(f)
            decision = DecisionResult(**decision_data)
            
            # Check plot file exists
            plot_path = examples_dir / test_case['plot_file']
            if not plot_path.exists():
                print(f"  ⚠️  Plot file not found: {plot_path}")
                continue
            
            # Generate verification hash based on key data
            verification_data = f"{spec.job.job_id}:{decision.pass_}:{decision.actual_hold_time_s}"
            import hashlib
            verification_hash = hashlib.sha256(verification_data.encode()).hexdigest()
            
            # Generate PDF
            output_path = examples_dir / test_case['output_file']
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=str(plot_path),
                verification_hash=verification_hash,
                output_path=str(output_path)
            )
            
            # Compute PDF hash for verification
            pdf_hash = compute_pdf_hash(pdf_bytes)
            
            print(f"  ✅ Generated: {output_path}")
            print(f"  📄 Size: {len(pdf_bytes):,} bytes")
            print(f"  🔐 Hash: {pdf_hash[:16]}...{pdf_hash[-16:]}")
            print(f"  🔍 Verify: {verification_hash[:16]}...{verification_hash[-16:]}")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue
    
    print(f"\n{'='*40}")
    print("PDF generation example completed!")
    print("\nExample PDFs demonstrate:")
    print("  • Professional inspector-ready format")
    print("  • PASS/FAIL status with color coding")
    print("  • Specification and results boxes")
    print("  • Temperature profile charts")
    print("  • QR codes for verification")
    print("  • Deterministic rendering")
    print("\nUse these PDFs as templates for your powder-coat cure validation.")


if __name__ == "__main__":
    main()