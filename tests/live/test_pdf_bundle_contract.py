#!/usr/bin/env python3
"""Test PDF and bundle contract consistency from live runs."""

import os
import json
import pytest
from pathlib import Path

# Skip unless LIVE_QA env is set
pytestmark = pytest.mark.skipif(
    not os.getenv("LIVE_QA"),
    reason="Live QA tests only run when LIVE_QA=1"
)

def get_latest_run():
    """Get the latest live run directory."""
    live_runs = Path("live_runs")
    if not live_runs.exists():
        return None
    
    runs = sorted([d for d in live_runs.iterdir() if d.is_dir()])
    return runs[-1] if runs else None

def test_latest_matrix_consistency():
    """Test that latest matrix run has consistent results."""
    latest_run = get_latest_run()
    if not latest_run:
        pytest.skip("No live runs found")
    
    matrix_file = latest_run / "matrix.json"
    if not matrix_file.exists():
        pytest.skip("No matrix.json in latest run")
    
    with open(matrix_file) as f:
        matrix = json.load(f)
    
    failures = []
    
    for industry, variants in matrix.items():
        for variant, result in variants.items():
            if "error" in result:
                failures.append(f"{industry}/{variant}: {result['error']}")
                continue
            
            # Check artifacts exist
            if not result.get('artifacts', {}).get('pdf'):
                failures.append(f"{industry}/{variant}: Missing PDF")
            
            if not result.get('artifacts', {}).get('bundle'):
                failures.append(f"{industry}/{variant}: Missing bundle")
            
            # Check API status is valid
            api_status = result.get('api_status')
            if api_status not in ['PASS', 'FAIL', 'INDETERMINATE', 'ERROR']:
                failures.append(f"{industry}/{variant}: Invalid API status: {api_status}")
    
    assert not failures, f"Matrix inconsistencies:\n" + "\n".join(failures)

def test_pdf_assertions():
    """Test PDF inspection assertions for all generated PDFs."""
    latest_run = get_latest_run()
    if not latest_run:
        pytest.skip("No live runs found")
    
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from scripts.inspect_pdf import inspect_pdf_text
    
    failures = []
    
    for pdf_path in latest_run.glob("**/proof.pdf"):
        rel_path = pdf_path.relative_to(latest_run)
        result = inspect_pdf_text(str(pdf_path))
        
        if not result['exists']:
            failures.append(f"{rel_path}: PDF doesn't exist")
            continue
        
        if not result['assertions_passed']:
            for assertion in result.get('assertions', []):
                failures.append(f"{rel_path}: {assertion}")
    
    assert not failures, f"PDF assertion failures:\n" + "\n".join(failures)

def test_bundle_assertions():
    """Test bundle verification assertions for all generated bundles."""
    latest_run = get_latest_run()
    if not latest_run:
        pytest.skip("No live runs found")
    
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from scripts.verify_bundle import verify_bundle
    
    failures = []
    
    for bundle_path in latest_run.glob("**/evidence.zip"):
        rel_path = bundle_path.relative_to(latest_run)
        result = verify_bundle(str(bundle_path))
        
        if not result['exists']:
            failures.append(f"{rel_path}: Bundle doesn't exist")
            continue
        
        if not result['assertions_passed']:
            for assertion in result.get('assertions', []):
                failures.append(f"{rel_path}: {assertion}")
    
    assert not failures, f"Bundle assertion failures:\n" + "\n".join(failures)

def test_pass_fail_matrix_coverage():
    """Test that each industry has both PASS and FAIL examples."""
    latest_run = get_latest_run()
    if not latest_run:
        pytest.skip("No live runs found")
    
    matrix_file = latest_run / "matrix.json"
    if not matrix_file.exists():
        pytest.skip("No matrix.json in latest run")
    
    with open(matrix_file) as f:
        matrix = json.load(f)
    
    failures = []
    
    for industry in matrix:
        has_pass = False
        has_fail = False
        
        for variant, result in matrix[industry].items():
            if "error" not in result:
                status = result.get('api_status')
                if status == 'PASS':
                    has_pass = True
                elif status == 'FAIL':
                    has_fail = True
        
        if not has_pass:
            failures.append(f"{industry}: Missing PASS example")
        if not has_fail:
            failures.append(f"{industry}: Missing FAIL example")
    
    assert not failures, f"Matrix coverage issues:\n" + "\n".join(failures)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--maxfail=1"])