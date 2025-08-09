#!/usr/bin/env python3
"""
Test script to verify the 4 powder failure fixes.

Expected outcomes:
- dup_ts: should raise DataQualityError (ERROR)
- fail: should return FAIL status (not INDETERMINATE)
- missing_required: should raise RequiredSignalMissingError (ERROR)  
- pass: should return PASS status

Usage: python3 test_powder_fixes.py
"""

import sys
import json
import pandas as pd
from pathlib import Path
from core.models import SpecV1
from core.normalize import load_csv_with_metadata, normalize_temperature_data, DataQualityError
from core.metrics_powder import RequiredSignalMissingError, validate_powder_coating_cure
from core.decide import make_decision


def test_powder_fixes():
    """Test all 4 powder failure cases."""
    fixtures_dir = Path('audit/fixtures/powder')
    results = {}
    
    # Test 1: dup_ts should raise DataQualityError (ERROR)
    print("Testing dup_ts case...")
    try:
        csv_path = fixtures_dir / 'dup_ts.csv'
        spec_path = fixtures_dir / 'dup_ts.json'
        
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        df, metadata = load_csv_with_metadata(csv_path)
        data_reqs = spec_data.get('data_requirements', {})
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0),
            industry=spec_data.get('industry')
        )
        result = make_decision(normalized_df, spec)
        results['dup_ts'] = f'UNEXPECTED: {result.status} (expected ERROR)'
        print(f"  dup_ts: UNEXPECTED {result.status} (expected ERROR)")
        
    except DataQualityError as e:
        results['dup_ts'] = 'CORRECT: ERROR (DataQualityError)'
        print(f"  dup_ts: CORRECT ERROR - {e}")
    except Exception as e:
        results['dup_ts'] = f'WRONG ERROR TYPE: {type(e).__name__}: {e}'
        print(f"  dup_ts: WRONG ERROR TYPE - {type(e).__name__}: {e}")
    
    # Test 2: fail should return FAIL status (not INDETERMINATE)
    print("Testing fail case...")
    try:
        csv_path = fixtures_dir / 'fail.csv'
        spec_path = fixtures_dir / 'fail.json'
        
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        df, metadata = load_csv_with_metadata(csv_path)
        data_reqs = spec_data.get('data_requirements', {})
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0),
            industry=spec_data.get('industry')
        )
        result = make_decision(normalized_df, spec)
        
        if result.status == 'FAIL':
            results['fail'] = 'CORRECT: FAIL'
            print(f"  fail: CORRECT FAIL")
        else:
            results['fail'] = f'INCORRECT: {result.status} (expected FAIL)'
            print(f"  fail: INCORRECT {result.status} (expected FAIL)")
            print(f"  fail reasons: {result.reasons}")
            
    except Exception as e:
        results['fail'] = f'ERROR: {type(e).__name__}: {e}'
        print(f"  fail: ERROR - {type(e).__name__}: {e}")
    
    # Test 3: missing_required should raise RequiredSignalMissingError (ERROR)
    print("Testing missing_required case...")
    try:
        csv_path = fixtures_dir / 'missing_required.csv'
        spec_path = fixtures_dir / 'missing_required.json'
        
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        df, metadata = load_csv_with_metadata(csv_path)
        data_reqs = spec_data.get('data_requirements', {})
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0),
            industry=spec_data.get('industry')
        )
        result = make_decision(normalized_df, spec)
        results['missing_required'] = f'UNEXPECTED: {result.status} (expected ERROR)'
        print(f"  missing_required: UNEXPECTED {result.status} (expected ERROR)")
        
    except RequiredSignalMissingError as e:
        results['missing_required'] = 'CORRECT: ERROR (RequiredSignalMissingError)'
        print(f"  missing_required: CORRECT ERROR - {e}")
    except Exception as e:
        results['missing_required'] = f'WRONG ERROR TYPE: {type(e).__name__}: {e}'
        print(f"  missing_required: WRONG ERROR TYPE - {type(e).__name__}: {e}")
    
    # Test 4: pass should return PASS status
    print("Testing pass case...")
    try:
        csv_path = fixtures_dir / 'pass.csv'
        spec_path = fixtures_dir / 'pass.json'
        
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        df, metadata = load_csv_with_metadata(csv_path)
        data_reqs = spec_data.get('data_requirements', {})
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0),
            industry=spec_data.get('industry')
        )
        result = make_decision(normalized_df, spec)
        
        if result.status == 'PASS':
            results['pass'] = 'CORRECT: PASS'
            print(f"  pass: CORRECT PASS")
        else:
            results['pass'] = f'INCORRECT: {result.status} (expected PASS)'
            print(f"  pass: INCORRECT {result.status} (expected PASS)")
            print(f"  pass reasons: {result.reasons}")
            
    except Exception as e:
        results['pass'] = f'ERROR: {type(e).__name__}: {e}'
        print(f"  pass: ERROR - {type(e).__name__}: {e}")
    
    # Summary
    print("\n=== SUMMARY ===")
    for test, result in results.items():
        print(f"{test}: {result}")
    
    # Check if all tests are correct
    correct_count = sum(1 for result in results.values() if result.startswith('CORRECT'))
    print(f"\nPassed: {correct_count}/4 tests")
    
    return correct_count == 4


if __name__ == '__main__':
    success = test_powder_fixes()
    sys.exit(0 if success else 1)