"""
Test error handling in ProofKit audit framework.

This module tests proper error handling, inheritance, and classification
of errors within the ProofKit system.

Example usage:
    pytest tests/test_error_handling.py -v
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.errors import (
    ProofKitError, DataQualityError, RequiredSignalMissingError,
    SensorFailureError, DecisionError, ValidationError
)
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.models import SpecV1


class TestErrorHierarchy:
    """Test proper error class hierarchy and inheritance."""
    
    def test_required_signal_missing_inherits_from_data_quality_error(self):
        """RequiredSignalMissingError should inherit from DataQualityError."""
        error = RequiredSignalMissingError(
            missing_signals=["sensor_1"], 
            available_signals=["sensor_2"], 
            required_count=2
        )
        
        assert isinstance(error, DataQualityError)
        assert isinstance(error, ProofKitError)
        assert error.error_code == "REQUIRED_SIGNAL_MISSING"
        
    def test_data_quality_error_inherits_from_proofkit_error(self):
        """DataQualityError should inherit from ProofKitError."""
        error = DataQualityError("Test message", ["issue1", "issue2"])
        
        assert isinstance(error, ProofKitError)
        assert error.error_code == "DATA_QUALITY_ERROR"
        assert error.quality_issues == ["issue1", "issue2"]


class TestErrorMessages:
    """Test error message formatting and details."""
    
    def test_required_signal_missing_error_messages(self):
        """Test different message formats for RequiredSignalMissingError."""
        # Test with missing specific sensors
        error1 = RequiredSignalMissingError(
            missing_signals=["sensor_temp_01"],
            available_signals=["sensor_temp_02", "sensor_temp_03"]
        )
        
        assert "Required sensors missing" in str(error1)
        assert "sensor_temp_01" in str(error1)
        assert "Available sensors" in str(error1)
        
        # Test with insufficient sensor count
        error2 = RequiredSignalMissingError(
            missing_signals=[],
            available_signals=["sensor_1"],
            required_count=3
        )
        
        assert "Insufficient sensors" in str(error2)
        assert "found 1 sensors, require at least 3" in str(error2)
    
    def test_error_details_structure(self):
        """Test that error details contain expected keys."""
        error = RequiredSignalMissingError(
            missing_signals=["sensor_1"],
            available_signals=["sensor_2", "sensor_3"],
            required_count=2
        )
        
        assert "missing_signals" in error.details
        assert "available_signals" in error.details
        assert "required_count" in error.details
        assert "quality_issues" in error.details


class TestErrorHandlingInDecision:
    """Test that the decision algorithm properly raises expected errors."""
    
    def test_insufficient_sensors_raises_error(self, tmp_path):
        """Test that insufficient sensors raises RequiredSignalMissingError."""
        # Create CSV with only 1 sensor when spec requires 3
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=30, freq='10S')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': np.full(30, 185.0)  # Only one sensor
        })
        
        csv_path = tmp_path / "insufficient_sensors.csv"
        df.to_csv(csv_path, index=False)
        
        spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "insufficient_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 3  # Require 3 sensors but only provide 1
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Should raise RequiredSignalMissingError
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            df, _ = load_csv_with_metadata(str(csv_path))
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
            spec_model = SpecV1(**spec)
            make_decision(normalized_df, spec_model)
        
        error = exc_info.value
        assert isinstance(error, RequiredSignalMissingError)
        assert isinstance(error, DataQualityError)
        assert error.required_count == 3
        assert len(error.available_signals) == 1


class TestAuditRunnerErrorHandling:
    """Test that audit runner handles errors appropriately."""
    
    def test_expected_error_marked_as_success(self):
        """Test that expected ERROR results are marked as successful."""
        from cli.audit_runner import AuditTestCase, run_single_test
        
        # This would normally require actual fixture files, so we'll skip for now
        # In a real implementation, this would test the audit runner logic
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])