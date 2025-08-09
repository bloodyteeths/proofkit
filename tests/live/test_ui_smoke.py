#!/usr/bin/env python3
"""Test UI smoke results."""

import os
import json
import pytest
from pathlib import Path

# Skip unless LIVE_QA env is set
pytestmark = pytest.mark.skipif(
    not os.getenv("LIVE_QA"),
    reason="Live QA tests only run when LIVE_QA=1"
)

def get_latest_ui_smoke():
    """Get the latest UI smoke results."""
    live_runs = Path("live_runs")
    if not live_runs.exists():
        return None
    
    for run_dir in sorted(live_runs.iterdir(), reverse=True):
        ui_smoke_file = run_dir / "ui_smoke.json"
        if ui_smoke_file.exists():
            with open(ui_smoke_file) as f:
                return json.load(f)
    
    return None

def test_homepage_loads():
    """Test that homepage loads with expected content."""
    results = get_latest_ui_smoke()
    if not results:
        pytest.skip("No UI smoke results found")
    
    homepage = results.get("homepage", {})
    
    assert homepage.get("status_code") == 200, f"Homepage returned {homepage.get('status_code')}"
    assert homepage.get("hero_found"), "Homepage hero not found"
    assert homepage.get("copy_found"), "Homepage copy not found"
    assert homepage.get("passed"), "Homepage checks failed"

def test_industry_pages_load():
    """Test that all industry pages load."""
    results = get_latest_ui_smoke()
    if not results:
        pytest.skip("No UI smoke results found")
    
    industries = results.get("industries", {})
    failures = []
    
    for industry, result in industries.items():
        if result.get("status_code") != 200:
            failures.append(f"{industry}: Status {result.get('status_code')}")
        elif not result.get("passed"):
            failures.append(f"{industry}: Content checks failed")
    
    assert not failures, f"Industry page failures:\n" + "\n".join(failures)

def test_examples_page_has_cards():
    """Test that examples page has industry cards."""
    results = get_latest_ui_smoke()
    if not results:
        pytest.skip("No UI smoke results found")
    
    examples = results.get("examples", {})
    
    assert examples.get("status_code") == 200, f"Examples page returned {examples.get('status_code')}"
    assert len(examples.get("industries_found", [])) >= 4, f"Only found {len(examples.get('industries_found', []))} industries"
    assert examples.get("passed"), "Examples page checks failed"

def test_verify_pages_work():
    """Test that verify pages load correctly."""
    results = get_latest_ui_smoke()
    if not results:
        pytest.skip("No UI smoke results found")
    
    verify_pages = results.get("verify_pages", {})
    if not verify_pages:
        pytest.skip("No verify pages tested")
    
    failures = []
    
    for page, result in verify_pages.items():
        if result.get("status_code") != 200:
            failures.append(f"{page}: Status {result.get('status_code')}")
        elif not result.get("status_chip_found"):
            failures.append(f"{page}: No PASS/FAIL chip found")
        elif not result.get("passed"):
            failures.append(f"{page}: Checks failed")
    
    assert not failures, f"Verify page failures:\n" + "\n".join(failures)

def test_overall_pass_rate():
    """Test that overall UI pass rate is acceptable."""
    results = get_latest_ui_smoke()
    if not results:
        pytest.skip("No UI smoke results found")
    
    summary = results.get("summary", {})
    pass_rate = summary.get("pass_rate", 0)
    
    assert pass_rate >= 80, f"UI pass rate too low: {pass_rate}% (minimum 80%)"
    
    # Warn if not perfect
    if pass_rate < 100:
        pytest.skip(f"UI pass rate is {pass_rate}% (some non-critical checks failed)")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])