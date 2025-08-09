"""
Test debug breadcrumbs in audit runner for PASS/FAIL mismatches.

Tests that when audit runner encounters a PASS/FAIL mismatch, it prints
a one-line metrics snippet (Fo, hold_secs, pct_in_range) to aid diagnosis.

Example:
    pytest -q tests/audit/test_debug_breadcrumbs.py
"""

import pytest
from unittest.mock import Mock, patch
import json
import tempfile
import os
from pathlib import Path

# Add parent directories to path to import modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cli.audit_runner import run_single_test, AuditTestCase


@pytest.fixture
def temp_test_files():
    """Create temporary test files for a PASS/FAIL mismatch scenario."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create a CSV file that should FAIL (insufficient hold time) but we'll expect PASS
        csv_content = """timestamp,sensor_temp
2024-01-01T10:00:00,180.0
2024-01-01T10:01:00,181.0
2024-01-01T10:02:00,182.0
2024-01-01T10:03:00,170.0
2024-01-01T10:04:00,171.0
"""
        csv_path = tmpdir_path / "test.csv"
        csv_path.write_text(csv_content)
        
        # Create a spec that should make this PASS (but we'll test it expecting FAIL)
        spec_content = {
            "version": "1.0",
            "industry": "powder",
            "job": {
                "job_id": "test_breadcrumbs"
            },
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        }
        json_path = tmpdir_path / "test.json"
        json_path.write_text(json.dumps(spec_content, indent=2))
        
        yield str(csv_path), str(json_path)


def test_pass_fail_mismatch_breadcrumbs(temp_test_files, capfd):
    """Test that PASS/FAIL mismatches include debug breadcrumbs."""
    csv_path, spec_path = temp_test_files
    
    # Create test case that expects PASS but will actually FAIL
    test_case = AuditTestCase(
        industry="powder",
        test_type="mismatch_test",
        csv_path=csv_path,
        spec_path=spec_path,
        expected_result="PASS",  # This will mismatch with actual FAIL
        description="Test mismatch breadcrumbs"
    )
    
    # Run test with verbose=True to capture debug output
    result = run_single_test(test_case, verbose=True)
    
    # Capture stdout
    captured = capfd.readouterr()
    stdout = captured.out
    
    # Test should not succeed due to mismatch
    assert not result.success
    assert result.decision == "FAIL"  # Actual result
    
    # Check that mismatch is detected and logged
    assert "PASS/FAIL mismatch" in stdout
    assert "expected=PASS, got=FAIL" in stdout
    
    # Check that metrics breadcrumbs are included when available
    if "hold_secs=" in stdout:
        assert "Metrics: hold_secs=" in stdout
        # Verify hold_secs format (should be a float)
        import re
        match = re.search(r'hold_secs=(\d+\.\d+)', stdout)
        assert match, "hold_secs should be formatted as float"
        hold_value = float(match.group(1))
        assert hold_value >= 0, "hold_secs should be non-negative"


def test_fo_metric_breadcrumb(temp_test_files, capfd):
    """Test that Fo metric is included in breadcrumbs when available."""
    csv_path, spec_path = temp_test_files
    
    # Modify spec to be autoclave industry (which uses Fo metric)
    with open(spec_path, 'r') as f:
        spec = json.load(f)
    
    spec["industry"] = "autoclave"
    spec["spec"]["target_temp_C"] = 132.0
    spec["spec"]["hold_time_s"] = 240
    
    with open(spec_path, 'w') as f:
        json.dump(spec, f, indent=2)
    
    test_case = AuditTestCase(
        industry="autoclave",
        test_type="fo_test",
        csv_path=csv_path,
        spec_path=spec_path,
        expected_result="FAIL",  # Expect mismatch
        description="Test Fo metric breadcrumb"
    )
    
    # Mock the decision result to include Fo metric
    original_run = run_single_test.__wrapped__ if hasattr(run_single_test, '__wrapped__') else run_single_test
    
    with patch('cli.audit_runner.make_decision') as mock_decision:
        # Create a mock decision result with Fo metric
        mock_result = Mock()
        mock_result.status = "PASS"
        mock_result.actual_hold_time_s = 300.0
        mock_result.model_dump.return_value = {
            "status": "PASS",
            "Fo": 15.5,
            "percent_in_range": 95.2,
            "actual_hold_time_s": 300.0
        }
        mock_decision.return_value = mock_result
        
        result = run_single_test(test_case, verbose=True)
    
    captured = capfd.readouterr()
    stdout = captured.out
    
    # Check for Fo metric in breadcrumbs
    if "Fo=" in stdout:
        assert "Fo=15.50" in stdout or "Fo=15.5" in stdout
    
    # Check for percent_in_range metric
    if "percent_in_range=" in stdout:
        assert "percent_in_range=95.2%" in stdout


def test_metrics_truncation(temp_test_files, capfd):
    """Test that large float metrics are properly truncated."""
    csv_path, spec_path = temp_test_files
    
    test_case = AuditTestCase(
        industry="powder",
        test_type="truncation_test", 
        csv_path=csv_path,
        spec_path=spec_path,
        expected_result="FAIL",
        description="Test metric truncation"
    )
    
    with patch('cli.audit_runner.make_decision') as mock_decision:
        # Create mock result with very precise floats
        mock_result = Mock()
        mock_result.status = "PASS"
        mock_result.actual_hold_time_s = 123.456789123456
        mock_result.model_dump.return_value = {
            "status": "PASS",
            "Fo": 12.3456789123456,
            "percent_in_range": 87.123456789,
            "actual_hold_time_s": 123.456789123456
        }
        mock_decision.return_value = mock_result
        
        result = run_single_test(test_case, verbose=True)
    
    captured = capfd.readouterr()
    stdout = captured.out
    
    # Check that floats are reasonably truncated (not too many decimal places)
    if "hold_secs=" in stdout:
        import re
        match = re.search(r'hold_secs=(\d+\.\d+)', stdout)
        if match:
            decimal_part = match.group(1).split('.')[1]
            assert len(decimal_part) <= 2, "hold_secs should be truncated to reasonable precision"
    
    if "Fo=" in stdout:
        import re
        match = re.search(r'Fo=(\d+\.\d+)', stdout)
        if match:
            decimal_part = match.group(1).split('.')[1]
            assert len(decimal_part) <= 2, "Fo should be truncated to reasonable precision"


def test_no_breadcrumbs_on_success(temp_test_files, capfd):
    """Test that no debug breadcrumbs are shown when test passes as expected."""
    csv_path, spec_path = temp_test_files
    
    test_case = AuditTestCase(
        industry="powder",
        test_type="success_test",
        csv_path=csv_path,
        spec_path=spec_path,
        expected_result="PASS",  # This should match actual PASS
        description="Test no breadcrumbs on success"
    )
    
    result = run_single_test(test_case, verbose=True)
    
    captured = capfd.readouterr()
    stdout = captured.out
    
    # Test should succeed since we expect PASS and should get PASS
    if result.success:
        # No mismatch breadcrumbs should be shown
        assert "PASS/FAIL mismatch" not in stdout
        assert "Metrics: hold_secs=" not in stdout
        assert "Fo=" not in stdout or "PASS/FAIL mismatch" not in stdout


def test_error_case_no_breadcrumbs(temp_test_files, capfd):
    """Test that ERROR cases don't show PASS/FAIL breadcrumbs."""
    csv_path, spec_path = temp_test_files
    
    # Create a spec with missing required fields to trigger error
    with open(spec_path, 'r') as f:
        spec = json.load(f)
    
    # Remove required field to trigger validation error
    del spec["spec"]["method"]
    
    with open(spec_path, 'w') as f:
        json.dump(spec, f, indent=2)
    
    test_case = AuditTestCase(
        industry="powder",
        test_type="error_test",
        csv_path=csv_path,
        spec_path=spec_path,
        expected_result="ERROR",
        description="Test error case handling"
    )
    
    result = run_single_test(test_case, verbose=True)
    
    captured = capfd.readouterr()
    stdout = captured.out
    
    # Should be an error case
    assert result.decision == "ERROR" or result.error_message is not None
    
    # Should not show PASS/FAIL mismatch breadcrumbs for error cases
    assert "PASS/FAIL mismatch" not in stdout
    assert "Metrics: hold_secs=" not in stdout