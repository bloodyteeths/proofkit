#!/usr/bin/env python3
"""Debug script to find the exact location of the .industry access error."""

import traceback
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def run_audit_with_debug():
    """Run a single audit test with full error reporting."""
    try:
        from cli.audit_runner import run_single_test, discover_test_fixtures
        
        # Get first test case
        audit_dir = Path('./audit')
        fixtures = discover_test_fixtures(audit_dir)
        
        if not fixtures:
            print("No fixtures found")
            return
            
        test_case = fixtures[0]  # Get first fixture
        print(f"Running test: {test_case.industry}/{test_case.test_type}")
        
        # Run the test directly without error handling
        print("Loading spec...")
        with open(test_case.spec_path, 'r') as f:
            import json
            spec_data = json.load(f)
        
        from core.models import SpecV1
        spec = SpecV1(**spec_data)
        print(f"✅ Spec loaded: {spec.industry}")
        
        print("Loading and normalizing CSV...")
        from core.normalize import load_csv_with_metadata, normalize_temperature_data
        df, metadata = load_csv_with_metadata(test_case.csv_path)
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=spec.data_requirements.allowed_gaps_s
        )
        print(f"✅ Data normalized: {len(normalized_df)} rows")
        
        print("Making decision...")
        from core.decide import make_decision
        decision_result = make_decision(normalized_df, spec)
        print(f"✅ Decision made: {type(decision_result)}, status: {decision_result.status}")
        print(f"    Industry in decision: {decision_result.industry}")
        print(f"    Industry in spec: {spec.industry}")
        
        # Check if the decision has all expected fields
        print(f"    Decision fields: {list(decision_result.__dict__.keys())}")
        
        # This is where the error might occur - when converting to dict
        print("Converting to dict...")
        if hasattr(decision_result, 'model_dump'):
            decision_dict = decision_result.model_dump(by_alias=True)
            print(f"✅ Converted to dict: {type(decision_dict)}")
            
            # Test accessing industry
            print("Testing industry access...")
            industry_val = decision_dict.get('industry', 'not_found')
            print(f"✅ Industry via .get(): {industry_val}")
            
            # Try direct access (this might be where it fails)
            try:
                industry_direct = decision_dict['industry']
                print(f"✅ Industry via []: {industry_direct}")
            except KeyError:
                print("❌ No 'industry' key in dict")
                print(f"Available keys: {list(decision_dict.keys())}")
        
        result = None  # We bypassed the normal flow
        
        if result.success:
            print(f"✅ Test passed: {result.decision}")
        else:
            print(f"❌ Test failed: {result.error_message}")
            
    except Exception as e:
        print(f"🚨 Exception caught: {e}")
        print("Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    run_audit_with_debug()