"""
ProofKit Decision Algorithm Tests

Comprehensive test suite for the decision algorithm functionality including:
- PASS/FAIL scenarios for various temperature profiles
- Sensor combination modes (min_of_set, mean_of_set, majority_over_threshold)
- Continuous vs cumulative hold time logic
- Conservative threshold calculation
- Edge cases and error handling

Example usage:
    pytest tests/test_decide.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from core.decide import (
    make_decision,
    calculate_conservative_threshold,
    combine_sensor_readings,
    calculate_hold_time,
    validate_preconditions,
    DecisionError
)
from core.models import SpecV1, DecisionResult, SensorMode


class TestConservativeThreshold:
    """Test conservative threshold calculation."""
    
    def test_basic_threshold_calculation(self):
        """Test basic conservative threshold calculation."""
        threshold = calculate_conservative_threshold(180.0, 2.0)
        assert threshold == 182.0
        
        threshold = calculate_conservative_threshold(150.0, 1.5)
        assert threshold == 151.5
        
        threshold = calculate_conservative_threshold(200.0, 0.0)
        assert threshold == 200.0
    
    def test_threshold_with_negative_uncertainty(self):
        """Test threshold calculation with edge cases."""
        # Negative uncertainty should still work (though unusual)
        threshold = calculate_conservative_threshold(180.0, -1.0)
        assert threshold == 179.0
        
        # Zero uncertainty
        threshold = calculate_conservative_threshold(180.0, 0.0)
        assert threshold == 180.0
    
    def test_threshold_precision(self):
        """Test threshold calculation precision."""
        threshold = calculate_conservative_threshold(180.123, 1.876)
        expected = 180.123 + 1.876
        assert abs(threshold - expected) < 1e-10


class TestSensorCombination:
    """Test sensor reading combination logic."""
    
    def test_min_of_set_mode(self, simple_temp_data):
        """Test min_of_set sensor combination mode."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        
        combined = combine_sensor_readings(
            simple_temp_data, temp_columns, SensorMode.MIN_OF_SET
        )
        
        # Result should be minimum of the two sensors at each timestamp
        expected_min = simple_temp_data[temp_columns].min(axis=1)
        pd.testing.assert_series_equal(combined, expected_min, check_names=False)
    
    def test_mean_of_set_mode(self, simple_temp_data):
        """Test mean_of_set sensor combination mode."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        
        combined = combine_sensor_readings(
            simple_temp_data, temp_columns, SensorMode.MEAN_OF_SET
        )
        
        # Result should be mean of the two sensors at each timestamp
        expected_mean = simple_temp_data[temp_columns].mean(axis=1)
        pd.testing.assert_series_equal(combined, expected_mean, check_names=False)
    
    def test_majority_over_threshold_mode(self):
        """Test majority_over_threshold sensor combination mode."""
        # Create test data with 3 sensors
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [179.0, 183.0, 183.0, 183.0, 183.0, 183.0, 183.0, 183.0, 183.0, 183.0],
            "sensor_2": [181.0, 183.5, 183.5, 183.5, 183.5, 183.5, 183.5, 183.5, 183.5, 183.5],
            "sensor_3": [180.0, 184.0, 184.0, 184.0, 184.0, 184.0, 184.0, 184.0, 184.0, 184.0]
        })
        
        temp_columns = ["sensor_1", "sensor_2", "sensor_3"]
        threshold_C = 182.0  # Conservative threshold
        
        combined = combine_sensor_readings(
            df, temp_columns, SensorMode.MAJORITY_OVER_THRESHOLD,
            require_at_least=2, threshold_C=threshold_C
        )
        
        # First row: only 2 sensors above threshold -> should be True (majority)
        # Rest: all 3 sensors above threshold -> should be True
        expected = pd.Series([True, True, True, True, True, True, True, True, True, True])
        pd.testing.assert_series_equal(combined, expected, check_names=False)
    
    def test_majority_insufficient_sensors(self):
        """Test majority mode when insufficient sensors meet threshold."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [179.0, 179.0, 179.0, 179.0, 179.0],  # Below threshold
            "sensor_2": [180.0, 180.0, 180.0, 180.0, 180.0],  # Below threshold  
            "sensor_3": [183.0, 183.0, 183.0, 183.0, 183.0]   # Above threshold
        })
        
        temp_columns = ["sensor_1", "sensor_2", "sensor_3"]
        threshold_C = 182.0
        
        combined = combine_sensor_readings(
            df, temp_columns, SensorMode.MAJORITY_OVER_THRESHOLD,
            require_at_least=2, threshold_C=threshold_C
        )
        
        # Only 1 sensor above threshold, need 2 -> all False
        expected = pd.Series([False, False, False, False, False])
        pd.testing.assert_series_equal(combined, expected, check_names=False)
    
    def test_missing_sensor_data(self):
        """Test sensor combination with missing data."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [180.0, 181.0, np.nan, 183.0, 184.0],
            "sensor_2": [179.0, np.nan, 182.0, 182.5, 183.5]
        })
        
        temp_columns = ["sensor_1", "sensor_2"]
        
        # Min of set should handle NaN appropriately
        combined = combine_sensor_readings(
            df, temp_columns, SensorMode.MIN_OF_SET
        )
        
        # Should have valid results where at least one sensor has data
        assert not combined.isna().all()
        assert combined.iloc[0] == 179.0  # min(180.0, 179.0)
        assert combined.iloc[1] == 181.0  # only sensor_1 available


class TestHoldTimeCalculation:
    """Test hold time calculation logic."""
    
    def test_continuous_hold_time_pass(self, simple_temp_data, example_spec):
        """Test continuous hold time calculation - passing scenario."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        threshold_C = 182.0
        
        # Combine sensors (min_of_set)
        combined_temps = combine_sensor_readings(
            simple_temp_data, temp_columns, SensorMode.MIN_OF_SET
        )
        
        hold_time = calculate_hold_time(
            simple_temp_data["timestamp"], 
            combined_temps, 
            threshold_C,
            continuous=True
        )
        
        # Should find significant hold time (data has 20 points at 182°C)
        assert hold_time >= 570.0  # 19 intervals * 30s = 570s
    
    def test_continuous_hold_time_fail(self, failing_temp_data, example_spec):
        """Test continuous hold time calculation - failing scenario."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        threshold_C = 182.0
        
        combined_temps = combine_sensor_readings(
            failing_temp_data, temp_columns, SensorMode.MIN_OF_SET
        )
        
        hold_time = calculate_hold_time(
            failing_temp_data["timestamp"],
            combined_temps,
            threshold_C,
            continuous=True
        )
        
        # Should have minimal hold time (temperatures don't reach threshold)
        assert hold_time < 60.0
    
    def test_cumulative_hold_time_pass(self, test_data_dir):
        """Test cumulative hold time calculation."""
        cumulative_csv_path = test_data_dir / "cumulative_hold_pass.csv"
        df, _ = load_csv_with_metadata(str(cumulative_csv_path))
        
        temp_columns = ["temp_1", "temp_2"]
        threshold_C = 182.0
        
        combined_temps = combine_sensor_readings(
            df, temp_columns, SensorMode.MIN_OF_SET
        )
        
        hold_time = calculate_hold_time(
            df["timestamp"],
            combined_temps,
            threshold_C,
            continuous=False  # Cumulative mode
        )
        
        # Should accumulate time above threshold across multiple periods
        assert hold_time >= 600.0  # Should pass 10-minute requirement
    
    def test_hold_time_with_gaps(self, gaps_temp_data):
        """Test hold time calculation with data gaps."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        threshold_C = 182.0
        
        combined_temps = combine_sensor_readings(
            gaps_temp_data, temp_columns, SensorMode.MIN_OF_SET
        )
        
        hold_time = calculate_hold_time(
            gaps_temp_data["timestamp"],
            combined_temps,
            threshold_C,
            continuous=True
        )
        
        # Hold time should account for gaps appropriately
        assert isinstance(hold_time, float)
        assert hold_time >= 0.0


class TestDecisionMaking:
    """Test complete decision making process."""
    
    def test_decision_pass_scenario(self, simple_temp_data, example_spec):
        """Test decision algorithm with passing temperature data."""
        result = make_decision(simple_temp_data, example_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == example_spec.job.job_id
        assert result.target_temp_C == example_spec.spec.target_temp_C
        assert result.conservative_threshold_C == 182.0  # 180 + 2
        assert result.actual_hold_time_s >= example_spec.spec.hold_time_s
        assert result.required_hold_time_s == example_spec.spec.hold_time_s
        assert len(result.reasons) > 0
        assert isinstance(result.warnings, list)
    
    def test_decision_fail_scenario(self, failing_temp_data, example_spec):
        """Test decision algorithm with failing temperature data."""
        result = make_decision(failing_temp_data, example_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert result.job_id == example_spec.job.job_id
        assert result.actual_hold_time_s < example_spec.spec.hold_time_s
        assert len(result.reasons) > 0
        assert any("hold time" in reason.lower() for reason in result.reasons)
    
    def test_decision_with_fahrenheit_data(self, fahrenheit_temp_data, example_spec):
        """Test decision with Fahrenheit temperature data."""
        result = make_decision(fahrenheit_temp_data, example_spec)
        
        assert isinstance(result, DecisionResult)
        # Should handle Fahrenheit conversion and make appropriate decision
        assert result.target_temp_C == example_spec.spec.target_temp_C
        assert result.conservative_threshold_C == 182.0
    
    def test_decision_different_sensor_modes(self, simple_temp_data):
        """Test decision algorithm with different sensor modes."""
        base_spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_mode_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        
        # Test min_of_set mode
        spec_min = SpecV1(**{
            **base_spec_data,
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
                "require_at_least": 1
            }
        })
        
        result_min = make_decision(simple_temp_data, spec_min)
        assert isinstance(result_min, DecisionResult)
        
        # Test mean_of_set mode
        spec_mean = SpecV1(**{
            **base_spec_data,
            "sensor_selection": {
                "mode": "mean_of_set",
                "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
                "require_at_least": 1
            }
        })
        
        result_mean = make_decision(simple_temp_data, spec_mean)
        assert isinstance(result_mean, DecisionResult)
        
        # Mean mode should typically have higher effective temperature
        # (but both should pass in this case)
        assert result_min.pass_ is True
        assert result_mean.pass_ is True
    
    def test_decision_with_majority_threshold(self, test_data_dir):
        """Test decision with majority_over_threshold sensor mode."""
        # Create data with 3 sensors
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=25, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 20,
            "sensor_2": [164.0, 169.0, 174.0, 178.0, 180.0] + [182.5] * 20,
            "sensor_3": [166.0, 171.0, 176.0, 180.0, 182.0] + [184.0] * 20
        })
        
        majority_spec_path = test_data_dir / "majority_threshold_spec.json"
        with open(majority_spec_path) as f:
            import json
            spec_data = json.load(f)
        
        spec = SpecV1(**spec_data)
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
        # Should pass - majority of sensors above threshold for required time
        assert result.pass_ is True
    
    def test_decision_continuous_vs_cumulative(self, test_data_dir):
        """Test difference between continuous and cumulative hold time modes."""
        cumulative_csv_path = test_data_dir / "cumulative_hold_pass.csv"
        df, _ = load_csv_with_metadata(str(cumulative_csv_path))
        
        base_spec_data = {
            "version": "1.0",
            "job": {"job_id": "hold_time_mode_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 600, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {"mode": "min_of_set", "sensors": ["temp_1", "temp_2"], "require_at_least": 1}
        }
        
        # Test continuous mode
        spec_continuous = SpecV1(**{
            **base_spec_data,
            "logic": {"continuous": True, "max_total_dips_s": 0}
        })
        
        result_continuous = make_decision(df, spec_continuous)
        
        # Test cumulative mode
        spec_cumulative = SpecV1(**{
            **base_spec_data,
            "logic": {"continuous": False, "max_total_dips_s": 120}
        })
        
        result_cumulative = make_decision(df, spec_cumulative)
        
        # Both should be valid results
        assert isinstance(result_continuous, DecisionResult)
        assert isinstance(result_cumulative, DecisionResult)
        
        # Cumulative mode should be more lenient
        if not result_continuous.pass_:
            # If continuous fails, cumulative might still pass
            assert result_cumulative.actual_hold_time_s >= result_continuous.actual_hold_time_s


class TestDecisionEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_dataframe_error(self, example_spec):
        """Test decision with empty DataFrame."""
        df = pd.DataFrame()
        
        with pytest.raises(DecisionError):
            make_decision(df, example_spec)
    
    def test_missing_temperature_columns(self, example_spec):
        """Test decision with missing temperature columns."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"),
            "wrong_column": [180.0] * 5
        })
        
        with pytest.raises(DecisionError):
            make_decision(df, example_spec)
    
    def test_insufficient_data_points(self, example_spec):
        """Test decision with insufficient data points."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=2, freq="30s", tz="UTC"),
            "pmt_sensor_1": [180.0, 181.0],
            "pmt_sensor_2": [179.5, 180.5]
        })
        
        result = make_decision(df, example_spec)
        
        # Should fail due to insufficient data
        assert result.pass_ is False
        assert any("insufficient" in reason.lower() or "short" in reason.lower() 
                  for reason in result.reasons)
    
    def test_all_temperatures_below_threshold(self, example_spec):
        """Test decision when all temperatures are below threshold."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=25, freq="30s", tz="UTC"),
            "pmt_sensor_1": [175.0] * 25,  # Below 182°C threshold
            "pmt_sensor_2": [174.0] * 25
        })
        
        result = make_decision(df, example_spec)
        
        assert result.pass_ is False
        assert result.actual_hold_time_s < 60.0  # Minimal hold time
        assert any("threshold" in reason.lower() for reason in result.reasons)
    
    def test_sensor_failure_scenario(self):
        """Test decision with sensor failure (all NaN values)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC"),
            "pmt_sensor_1": [np.nan] * 10,
            "pmt_sensor_2": [np.nan] * 10
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_failure_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {"mode": "min_of_set", "sensors": ["pmt_sensor_1", "pmt_sensor_2"], "require_at_least": 1}
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError):
            make_decision(df, spec)


class TestDecisionResultValidation:
    """Test DecisionResult model validation and serialization."""
    
    def test_decision_result_structure(self, simple_temp_data, example_spec):
        """Test DecisionResult structure and field validation."""
        result = make_decision(simple_temp_data, example_spec)
        
        # Check all required fields are present
        assert hasattr(result, 'pass_')
        assert hasattr(result, 'job_id')
        assert hasattr(result, 'target_temp_C')
        assert hasattr(result, 'conservative_threshold_C')
        assert hasattr(result, 'actual_hold_time_s')
        assert hasattr(result, 'required_hold_time_s')
        assert hasattr(result, 'max_temp_C')
        assert hasattr(result, 'min_temp_C')
        assert hasattr(result, 'reasons')
        assert hasattr(result, 'warnings')
        
        # Check field types
        assert isinstance(result.pass_, bool)
        assert isinstance(result.job_id, str)
        assert isinstance(result.target_temp_C, float)
        assert isinstance(result.conservative_threshold_C, float)
        assert isinstance(result.actual_hold_time_s, float)
        assert isinstance(result.required_hold_time_s, int)
        assert isinstance(result.max_temp_C, float)
        assert isinstance(result.min_temp_C, float)
        assert isinstance(result.reasons, list)
        assert isinstance(result.warnings, list)
    
    def test_decision_result_serialization(self, simple_temp_data, example_spec):
        """Test DecisionResult JSON serialization."""
        result = make_decision(simple_temp_data, example_spec)
        
        # Should be serializable to JSON
        json_dict = result.model_dump()
        assert isinstance(json_dict, dict)
        assert 'pass' in json_dict  # Uses alias
        assert json_dict['pass'] == result.pass_
        
        # Should be deserializable from JSON
        reconstructed = DecisionResult(**json_dict)
        assert reconstructed.pass_ == result.pass_
        assert reconstructed.job_id == result.job_id
    
    def test_decision_metrics_ranges(self, simple_temp_data, example_spec):
        """Test decision result metrics are within expected ranges."""
        result = make_decision(simple_temp_data, example_spec)
        
        # Temperature metrics should be reasonable
        assert 0.0 <= result.min_temp_C <= 500.0
        assert 0.0 <= result.max_temp_C <= 500.0
        assert result.min_temp_C <= result.max_temp_C
        
        # Hold time should be non-negative
        assert result.actual_hold_time_s >= 0.0
        assert result.required_hold_time_s > 0
        
        # Threshold should be reasonable
        assert result.conservative_threshold_C > result.target_temp_C
        assert result.conservative_threshold_C <= result.target_temp_C + 20.0  # Reasonable uncertainty range


from core.normalize import load_csv_with_metadata