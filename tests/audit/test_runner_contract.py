"""
Test contract validation for audit_runner.py

Tests that audit runner correctly handles expected ERROR cases by treating
DataQualityError and RequiredSignalMissingError exceptions as success
when expected_result=="ERROR".
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from cli.audit_runner import AuditTestCase, run_single_test
from core.errors import DataQualityError, RequiredSignalMissingError


def create_test_fixtures():
    """Create temporary test fixtures for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    
    # Create CSV file
    csv_content = """timestamp,sensor_temp1
2024-01-01T10:00:00Z,150.0
2024-01-01T10:01:00Z,160.0
2024-01-01T10:02:00Z,170.0
"""
    csv_path = temp_dir / "test.csv"
    csv_path.write_text(csv_content)
    
    # Create spec file
    spec_content = {
        "version": "1.0",
        "industry": "powder",
        "job": {"job_id": "test_001"},
        "spec": {
            "method": "PMT",
            "target_temp_C": 180.0,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 2.0
        },
        "data_requirements": {
            "max_sample_period_s": 30.0,
            "allowed_gaps_s": 60.0
        }
    }
    json_path = temp_dir / "test.json"
    json_path.write_text(json.dumps(spec_content, indent=2))
    
    return temp_dir, str(csv_path), str(json_path)


class TestAuditRunnerErrorContract:
    """Test that audit runner correctly handles expected ERROR cases."""

    def test_data_quality_error_success_when_expected(self):
        """Test DataQualityError is treated as success when expected_result='ERROR'."""
        temp_dir, csv_path, json_path = create_test_fixtures()
        
        try:
            test_case = AuditTestCase(
                industry="powder",
                test_type="gap",
                csv_path=csv_path,
                spec_path=json_path,
                expected_result="ERROR",
                description="Data gap test case"
            )
            
            # Mock load_csv_with_metadata to raise DataQualityError
            with patch('cli.audit_runner.load_csv_with_metadata') as mock_load:
                mock_load.side_effect = DataQualityError(
                    "Data gap exceeds allowed limit",
                    quality_issues=["Gap of 3600s detected"]
                )
                
                result = run_single_test(test_case, verbose=False)
                
                # Should be successful because we expected ERROR
                assert result.success is True
                assert result.decision == "ERROR"
                assert "DataQualityError" in result.error_message
                assert "Data gap exceeds allowed limit" in result.error_message
                
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)

    def test_required_signal_missing_error_success_when_expected(self):
        """Test RequiredSignalMissingError is treated as success when expected_result='ERROR'."""
        temp_dir, csv_path, json_path = create_test_fixtures()
        
        try:
            test_case = AuditTestCase(
                industry="powder",
                test_type="missing_required",
                csv_path=csv_path,
                spec_path=json_path,
                expected_result="ERROR",
                description="Missing required sensor test case"
            )
            
            # Mock make_decision to raise RequiredSignalMissingError
            with patch('cli.audit_runner.make_decision') as mock_decide:
                mock_decide.side_effect = RequiredSignalMissingError(
                    missing_signals=["temperature"],
                    available_signals=["pressure"]
                )
                
                # Need to also mock the data loading to get past that step
                with patch('cli.audit_runner.load_csv_with_metadata') as mock_load, \
                     patch('cli.audit_runner.normalize_temperature_data') as mock_normalize:
                    
                    mock_load.return_value = (MagicMock(), {})
                    mock_normalize.return_value = MagicMock()
                    
                    result = run_single_test(test_case, verbose=False)
                    
                    # Should be successful because we expected ERROR
                    assert result.success is True
                    assert result.decision == "ERROR"
                    assert "RequiredSignalMissingError" in result.error_message
                    assert "temperature" in result.error_message
                
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)

    def test_data_quality_error_failure_when_not_expected(self):
        """Test DataQualityError is treated as failure when expected_result != 'ERROR'."""
        temp_dir, csv_path, json_path = create_test_fixtures()
        
        try:
            test_case = AuditTestCase(
                industry="powder",
                test_type="pass",
                csv_path=csv_path,
                spec_path=json_path,
                expected_result="PASS",  # We expect PASS but get ERROR
                description="Pass test case"
            )
            
            # Mock load_csv_with_metadata to raise DataQualityError
            with patch('cli.audit_runner.load_csv_with_metadata') as mock_load:
                mock_load.side_effect = DataQualityError(
                    "Unexpected data quality issue",
                    quality_issues=["Unexpected gap"]
                )
                
                result = run_single_test(test_case, verbose=False)
                
                # Should be failure because we expected PASS but got ERROR
                assert result.success is False
                assert result.decision == "ERROR"
                assert "DataQualityError" in result.error_message
                
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)

    def test_required_signal_missing_error_failure_when_not_expected(self):
        """Test RequiredSignalMissingError is treated as failure when expected_result != 'ERROR'."""
        temp_dir, csv_path, json_path = create_test_fixtures()
        
        try:
            test_case = AuditTestCase(
                industry="powder",
                test_type="fail",
                csv_path=csv_path,
                spec_path=json_path,
                expected_result="FAIL",  # We expect FAIL but get ERROR
                description="Fail test case"
            )
            
            # Mock make_decision to raise RequiredSignalMissingError
            with patch('cli.audit_runner.make_decision') as mock_decide:
                mock_decide.side_effect = RequiredSignalMissingError(
                    missing_signals=["temperature"],
                    available_signals=["pressure"]
                )
                
                # Need to also mock the data loading to get past that step
                with patch('cli.audit_runner.load_csv_with_metadata') as mock_load, \
                     patch('cli.audit_runner.normalize_temperature_data') as mock_normalize:
                    
                    mock_load.return_value = (MagicMock(), {})
                    mock_normalize.return_value = MagicMock()
                    
                    result = run_single_test(test_case, verbose=False)
                    
                    # Should be failure because we expected FAIL but got ERROR
                    assert result.success is False
                    assert result.decision == "ERROR"
                    assert "RequiredSignalMissingError" in result.error_message or "Required sensors missing" in result.error_message
                
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)

    def test_no_expected_result_handles_errors_gracefully(self):
        """Test that when no expected_result is specified, errors are handled gracefully."""
        temp_dir, csv_path, json_path = create_test_fixtures()
        
        try:
            test_case = AuditTestCase(
                industry="powder",
                test_type="borderline",
                csv_path=csv_path,
                spec_path=json_path,
                expected_result=None,  # No expectation
                description="Borderline test case"
            )
            
            # Mock make_decision to raise DataQualityError
            with patch('cli.audit_runner.make_decision') as mock_decide:
                mock_decide.side_effect = DataQualityError(
                    "Some data issue",
                    quality_issues=["Data issue"]
                )
                
                # Need to also mock the data loading to get past that step
                with patch('cli.audit_runner.load_csv_with_metadata') as mock_load, \
                     patch('cli.audit_runner.normalize_temperature_data') as mock_normalize:
                    
                    mock_load.return_value = (MagicMock(), {})
                    mock_normalize.return_value = MagicMock()
                    
                    result = run_single_test(test_case, verbose=False)
                    
                    # Should be failure because no expectation means we didn't expect ERROR
                    assert result.success is False
                    assert result.decision == "ERROR"
                    assert "DataQualityError" in result.error_message
                
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)