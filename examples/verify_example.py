#!/usr/bin/env python3
"""
ProofKit Verification Example

Demonstrates the comprehensive evidence bundle verification system
including integrity checks and decision re-computation.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.verify import verify_evidence_bundle, verify_bundle_quick, VerificationReport
import json


def main():
    """
    Example usage of ProofKit verification system.
    """
    print("ProofKit Evidence Bundle Verification Example")
    print("=" * 50)
    
    # Example bundle path (you would replace this with actual bundle)
    example_bundle = Path("examples/outputs/evidence.zip")
    
    if not example_bundle.exists():
        print(f"Example bundle not found: {example_bundle}")
        print("This example requires an existing evidence bundle to verify.")
        print("You can create one using the pack_example.py script first.")
        return
    
    print(f"Verifying bundle: {example_bundle}")
    print()
    
    # Example 1: Quick verification (integrity only)
    print("1. Quick Verification (integrity only)")
    print("-" * 30)
    
    try:
        quick_result = verify_bundle_quick(str(example_bundle))
        
        print(f"Valid: {quick_result['valid']}")
        print(f"Bundle exists: {quick_result['bundle_exists']}")
        print(f"Manifest found: {quick_result['manifest_found']}")
        print(f"Root hash: {quick_result.get('root_hash', 'N/A')}")
        print(f"Root hash valid: {quick_result['root_hash_valid']}")
        print(f"Files verified: {quick_result['files_verified']}/{quick_result['files_total']}")
        print(f"Issues: {quick_result['issues_count']}")
        print(f"Warnings: {quick_result['warnings_count']}")
        
        if quick_result['valid']:
            print("✓ Quick verification PASSED")
        else:
            print("✗ Quick verification FAILED")
            
    except Exception as e:
        print(f"Quick verification error: {e}")
    
    print("\n" + "=" * 50)
    
    # Example 2: Full verification with decision re-computation
    print("2. Full Verification (integrity + decision validation)")
    print("-" * 50)
    
    try:
        # Perform comprehensive verification
        report = verify_evidence_bundle(
            str(example_bundle),
            verify_decision=True,
            cleanup_temp=True
        )
        
        print(f"Bundle Path: {report.bundle_path}")
        print(f"Verification Timestamp: {report.timestamp}")
        print()
        
        print("Bundle Integrity:")
        print(f"  Manifest found: {'✓' if report.manifest_found else '✗'}")
        print(f"  Manifest valid: {'✓' if report.manifest_valid else '✗'}")
        print(f"  Files verified: {report.files_verified}/{report.files_total}")
        
        if report.root_hash:
            print(f"  Root hash: {report.root_hash[:16]}...")
            print(f"  Root hash valid: {'✓' if report.root_hash_valid else '✗'}")
        
        if report.decision_recomputed:
            print("\nDecision Verification:")
            print(f"  Decision re-computed: {'✓' if report.decision_recomputed else '✗'}")
            print(f"  Decision matches: {'✓' if report.decision_matches else '✗'}")
            
            if report.original_decision and report.recomputed_decision:
                print(f"  Original result: {'PASS' if report.original_decision.pass_ else 'FAIL'}")
                print(f"  Recomputed result: {'PASS' if report.recomputed_decision.pass_ else 'FAIL'}")
                print(f"  Hold time (original): {report.original_decision.actual_hold_time_s:.1f}s")
                print(f"  Hold time (recomputed): {report.recomputed_decision.actual_hold_time_s:.1f}s")
            
            if report.decision_discrepancies:
                print(f"  Discrepancies ({len(report.decision_discrepancies)}):")
                for discrepancy in report.decision_discrepancies:
                    print(f"    - {discrepancy}")
        
        # Show issues and warnings
        if report.issues:
            print(f"\nIssues ({len(report.issues)}):")
            for issue in report.issues:
                print(f"  ✗ {issue}")
        
        if report.warnings:
            print(f"\nWarnings ({len(report.warnings)}):")
            for warning in report.warnings:
                print(f"  ⚠ {warning}")
        
        # Bundle metadata
        if report.bundle_metadata:
            print(f"\nBundle Metadata:")
            for key, value in report.bundle_metadata.items():
                print(f"  {key}: {value}")
        
        # Final result
        print("\n" + "=" * 30)
        if report.is_valid:
            print("✓ VERIFICATION PASSED")
            print("  Bundle integrity confirmed")
            if report.decision_recomputed:
                print("  Decision algorithm results verified")
        else:
            print("✗ VERIFICATION FAILED")
            print(f"  Found {len(report.issues)} issues")
            if report.decision_recomputed and not report.decision_matches:
                print("  Decision results do not match original")
        
        # Example 3: Save detailed report as JSON
        print("\n" + "=" * 50)
        print("3. Detailed Report Export")
        print("-" * 30)
        
        report_file = Path("examples/outputs/verification_report.json")
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        print(f"Detailed verification report saved to: {report_file}")
        print(f"Report size: {report_file.stat().st_size:,} bytes")
        
        # Example 4: Pretty-print the report
        print("\n" + "=" * 50)
        print("4. Human-Readable Report")
        print("-" * 30)
        print(str(report))
        
    except Exception as e:
        print(f"Full verification error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()