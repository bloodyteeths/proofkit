"""
Test Shared Error Handling

Tests for ProofKit shared error classes and error handling consistency
across modules. Validates that error classes provide proper structured
information and that different modules handle errors consistently.

This module tests:
1. Error class construction and attributes
2. Error message formatting and details
3. Error handling in audit runner
4. Integration with decision algorithm

Example usage:
    pytest tests/test_shared_errors.py -v
    pytest tests/test_shared_errors.py::TestRequiredSignalMissingError -s
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.errors import (
    ProofKitError, RequiredSignalMissingError, DataQualityError,
    SensorFailureError, DecisionError, ValidationError,
    InsufficientDataError, ThresholdNotReachedError
)
from cli.audit_runner import AuditTestCase, run_single_test


class TestProofKitError:
    """Test base ProofKit error class."""
    
    def test_basic_error_creation(self):
        """Test basic error construction with message only."""
        error = ProofKitError("Test error message")
        
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.error_code == "ProofKitError"
        assert error.details == {}
    
    def test_error_with_code_and_details(self):
        """Test error construction with error code and details."""
        details = {"field": "value", "count": 42}
        error = ProofKitError("Test message", "CUSTOM_ERROR", details)
        
        assert error.message == "Test message"
        assert error.error_code == "CUSTOM_ERROR"
        assert error.details == details


class TestRequiredSignalMissingError:
    """Test RequiredSignalMissingError class."""
    
    def test_missing_specific_signals(self):
        """Test error for missing specific required signals."""
        missing = ["sensor_temp_01", "sensor_temp_02"]
        available = ["sensor_temp_03", "sensor_pressure_01"]
        
        error = RequiredSignalMissingError(missing, available)
        
        assert error.missing_signals == missing
        assert error.available_signals == available
        assert error.required_count is None
        assert error.error_code == "REQUIRED_SIGNAL_MISSING"
        
        # Check message content
        message = str(error)
        assert "Required sensors missing" in message
        assert "sensor_temp_01" in message
        assert "sensor_temp_02" in message
        assert "sensor_temp_03" in message
    
    def test_insufficient_sensor_count(self):
        """Test error for insufficient number of sensors."""
        missing = []
        available = ["sensor_temp_01", "sensor_temp_02"] 
        required_count = 3
        
        error = RequiredSignalMissingError(missing, available, required_count)
        
        assert error.missing_signals == missing
        assert error.available_signals == available
        assert error.required_count == required_count
        
        # Check message content for count-based error
        message = str(error)
        assert "Insufficient sensors" in message
        assert "found 2 sensors" in message
        assert "require at least 3" in message
    
    def test_error_details_structure(self):
        """Test that error details contain expected structure."""
        missing = ["sensor_01"]
        available = ["sensor_02", "sensor_03"]
        required_count = 2
        
        error = RequiredSignalMissingError(missing, available, required_count)
        
        expected_details = {
            "missing_signals": missing,
            "available_signals": available,
            "required_count": required_count
        }
        
        assert error.details == expected_details


class TestDataQualityError:
    """Test DataQualityError class."""
    
    def test_data_quality_error_creation(self):
        """Test data quality error with quality issues list."""
        issues = ["Large data gaps detected", "Duplicate timestamps found", "Out of range values"]
        error = DataQualityError("Data quality validation failed", issues)
        
        assert error.quality_issues == issues
        assert error.error_code == "DATA_QUALITY_ERROR"
        assert error.details["quality_issues"] == issues
        
        message = str(error)
        assert "Data quality validation failed" in message


class TestSensorFailureError:
    """Test SensorFailureError class."""
    
    def test_sensor_failure_all_nan(self):
        """Test sensor failure for all NaN values."""
        failed_sensors = ["sensor_temp_01", "sensor_temp_03"]
        error = SensorFailureError(failed_sensors, "all_nan")
        
        assert error.failed_sensors == failed_sensors
        assert error.failure_type == "all_nan"
        assert error.error_code == "SENSOR_FAILURE"
        
        message = str(error)
        assert "Sensor failure detected (all_nan)" in message
        assert "sensor_temp_01" in message
    
    def test_sensor_failure_default_type(self):
        """Test sensor failure with default failure type."""
        failed_sensors = ["sensor_01"]
        error = SensorFailureError(failed_sensors)
        
        assert error.failure_type == "all_nan"


class TestDecisionError:
    """Test DecisionError class."""
    
    def test_decision_error_with_stage(self):
        """Test decision error with algorithm stage information."""
        error = DecisionError("Threshold calculation failed", "threshold_analysis")
        
        assert error.algorithm_stage == "threshold_analysis"
        assert error.error_code == "DECISION_ERROR"
        assert error.details["algorithm_stage"] == "threshold_analysis"
    
    def test_decision_error_without_stage(self):
        """Test decision error without stage information."""
        error = DecisionError("Generic decision failure")
        
        assert error.algorithm_stage is None
        assert error.details == {}


class TestValidationError:
    """Test ValidationError class."""
    
    def test_validation_error_with_fields(self):
        """Test validation error with invalid field information."""
        invalid_fields = ["target_temp_C", "hold_time_s"]
        error = ValidationError("Spec validation failed", "spec_validation", invalid_fields)
        
        assert error.validation_type == "spec_validation"
        assert error.invalid_fields == invalid_fields
        assert error.error_code == "VALIDATION_ERROR"
        
        expected_details = {
            "validation_type": "spec_validation",
            "invalid_fields": invalid_fields
        }
        assert error.details == expected_details
    
    def test_validation_error_without_fields(self):
        """Test validation error without field information."""
        error = ValidationError("Generic validation failed", "csv_validation")
        
        assert error.validation_type == "csv_validation" 
        assert error.invalid_fields == []


class TestInsufficientDataError:
    """Test InsufficientDataError class."""
    
    def test_insufficient_data_error(self):
        """Test insufficient data error construction."""
        error = InsufficientDataError(50, 100, "hold_time_analysis")
        
        assert error.available_points == 50
        assert error.required_points == 100
        assert error.analysis_type == "hold_time_analysis"
        assert error.error_code == "INSUFFICIENT_DATA"
        
        message = str(error)
        assert "50 points available" in message
        assert "100 required" in message
        assert "hold_time_analysis" in message
    
    def test_insufficient_data_default_analysis(self):
        """Test insufficient data error with default analysis type."""
        error = InsufficientDataError(10, 20)
        
        assert error.analysis_type == "decision"


class TestThresholdNotReachedError:
    """Test ThresholdNotReachedError class."""
    
    def test_threshold_not_reached_error(self):
        """Test threshold not reached error construction."""
        error = ThresholdNotReachedError(178.5, 182.0, 180.0)
        
        assert error.max_temp_C == 178.5
        assert error.threshold_C == 182.0
        assert error.target_temp_C == 180.0
        assert error.error_code == "THRESHOLD_NOT_REACHED"
        
        message = str(error)
        assert "178.5°C" in message
        assert "182.0°C" in message
        assert "180.0°C" in message


class TestAuditRunnerErrorHandling:
    """Test error handling integration with audit runner."""
    
    def test_audit_handles_required_signal_missing_error(self, tmp_path):
        """Test that audit runner properly handles RequiredSignalMissingError."""
        # Create CSV with insufficient sensors
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='10S')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_temp_01': np.full(50, 185.0)  # Only one sensor
        })
        
        csv_path = tmp_path / "insufficient_sensors.csv"
        df.to_csv(csv_path, index=False)
        
        # Create spec that requires 3 sensors
        spec_content = """{
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "error_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 3
            }
        }"""
        
        spec_path = tmp_path / "insufficient_sensors.json"
        spec_path.write_text(spec_content)
        
        # Create test case that expects ERROR
        test_case = AuditTestCase(
            industry="powder",
            test_type="missing_required",
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            expected_result="ERROR",
            description="Test insufficient sensors"
        )
        
        # Run audit test
        result = run_single_test(test_case, verbose=True)
        
        # Should succeed because we expected ERROR
        assert result.success == True
        assert result.decision == "ERROR"
        assert "sensor" in result.error_message.lower()
    
    def test_audit_handles_unexpected_error_gracefully(self, tmp_path):
        """Test that audit runner handles unexpected errors gracefully."""
        # Create invalid CSV file (empty)
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("timestamp\n")  # Only header, no data
        
        # Create valid spec
        spec_content = """{
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "empty_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            }
        }"""
        
        spec_path = tmp_path / "empty.json"
        spec_path.write_text(spec_content)
        
        # Create test case that does NOT expect ERROR
        test_case = AuditTestCase(
            industry="powder",
            test_type="pass",
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            expected_result="PASS",
            description="Test empty data handling"
        )
        
        # Run audit test
        result = run_single_test(test_case, verbose=True)
        
        # Should fail because we expected PASS but got error
        assert result.success == False
        assert result.error_message is not None
    
    def test_error_expected_result_matching(self, tmp_path):
        """Test that ERROR expected results are matched correctly."""
        # This test verifies the logic in audit_runner.py that determines
        # success based on expected vs actual results for ERROR cases
        
        # Create a scenario that should raise RequiredSignalMissingError
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=10, freq='10S')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'other_column': np.full(10, 25.0)  # No temperature sensors
        })
        
        csv_path = tmp_path / "no_sensors.csv"
        df.to_csv(csv_path, index=False)
        
        spec_content = """{
            "version": "1.0",
            "industry": "powder", 
            "job": {"job_id": "no_sensors_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            }
        }"""
        
        spec_path = tmp_path / "no_sensors.json"
        spec_path.write_text(spec_content)
        
        # Test case 1: Expect ERROR (should succeed)
        test_case_expect_error = AuditTestCase(
            industry="powder",
            test_type="missing_required",
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            expected_result="ERROR",
            description="Test missing sensors with ERROR expected"
        )
        
        result = run_single_test(test_case_expect_error)
        assert result.success == True  # Success because we expected ERROR and got it
        assert result.decision == "ERROR"
        
        # Test case 2: Expect PASS (should fail)
        test_case_expect_pass = AuditTestCase(
            industry="powder",
            test_type="pass",
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            expected_result="PASS",
            description="Test missing sensors with PASS expected"
        )
        
        result = run_single_test(test_case_expect_pass)
        assert result.success == False  # Failure because we expected PASS but got ERROR
        assert result.decision == "ERROR"


if __name__ == "__main__":
    # Run all tests when executed directly
    pytest.main([__file__, "-v"])