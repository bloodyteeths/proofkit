"""
Additional comprehensive tests for decide.py to reach ≥92% coverage.

Focus areas:
- Majority boundaries and edge cases
- Duplicate timestamp handling
- °F conversion edge cases
- Preconditions validation
- Industry-specific engine dispatch
- Error conditions and edge cases
- Cumulative hold time logic
- Ramp rate calculations
- Time to threshold calculations

Example usage:
    pytest tests/test_decide_additional.py -v --cov=core.decide
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

from core.decide import (
    make_decision,
    calculate_conservative_threshold,
    combine_sensor_readings,
    validate_preconditions,
    detect_temperature_columns,
    calculate_ramp_rate,
    find_threshold_crossing_time,
    calculate_continuous_hold_time,
    calculate_boolean_hold_time,
    calculate_cumulative_hold_time,
    DecisionError,
    INDUSTRY_METRICS
)
from core.models import SpecV1, DecisionResult, SensorMode


class TestValidatePreconditions:
    """Test validate_preconditions function edge cases."""
    
    def test_empty_dataframe(self, example_spec):
        """Test validation with empty DataFrame."""
        df = pd.DataFrame()
        valid, issues = validate_preconditions(df, example_spec)
        
        assert not valid
        assert "DataFrame is empty" in issues
    
    def test_insufficient_data_points(self, example_spec):
        """Test validation with insufficient data points."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-15T10:00:00Z")]
        })
        valid, issues = validate_preconditions(df, example_spec)
        
        assert not valid
        assert "Insufficient data points for analysis" in issues
    
    def test_no_timestamp_column(self, example_spec):
        """Test validation with no timestamp column."""
        df = pd.DataFrame({
            "temp_1": [180.0, 181.0],
            "temp_2": [179.0, 180.0]
        })
        valid, issues = validate_preconditions(df, example_spec)
        
        assert not valid
        assert "No timestamp column found" in issues
    
    def test_no_temperature_columns(self, example_spec):
        """Test validation with no temperature columns."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"),
            "pressure": [1013.25] * 5,
            "humidity": [50.0] * 5
        })
        valid, issues = validate_preconditions(df, example_spec)
        
        assert not valid
        assert "No temperature columns found" in issues
    
    def test_specified_sensors_not_found(self):
        """Test validation when specified sensors are not found."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"),
            "temp_A": [180.0] * 5,
            "temp_B": [181.0] * 5
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["missing_sensor_1", "missing_sensor_2"],
                "require_at_least": 2
            }
        }
        spec = SpecV1(**spec_data)
        
        valid, issues = validate_preconditions(df, spec)
        
        assert not valid
        assert "None of specified sensors found" in str(issues)
    
    def test_insufficient_sensors_available(self):
        """Test validation when insufficient sensors are available."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"),
            "pmt_sensor_1": [180.0] * 5
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
                "require_at_least": 2
            }
        }
        spec = SpecV1(**spec_data)
        
        valid, issues = validate_preconditions(df, spec)
        
        assert not valid
        assert "Insufficient sensors" in str(issues)
    
    def test_valid_conditions(self, simple_temp_data, example_spec):
        """Test validation with valid conditions."""
        valid, issues = validate_preconditions(simple_temp_data, example_spec)
        
        assert valid
        assert len(issues) == 0


class TestSensorCombinationEdgeCases:
    """Test sensor combination edge cases and error conditions."""
    
    def test_no_temperature_columns_provided(self, simple_temp_data):
        """Test combine_sensor_readings with no temperature columns."""
        with pytest.raises(DecisionError, match="No temperature columns provided"):
            combine_sensor_readings(simple_temp_data, [], SensorMode.MIN_OF_SET)
    
    def test_insufficient_valid_sensors_error(self):
        """Test combine_sensor_readings with insufficient valid sensors."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [180.0, np.nan, np.nan, np.nan, np.nan],  # Only 1 valid reading
            "sensor_2": [np.nan, 181.0, np.nan, np.nan, np.nan],  # Only 1 valid reading
            "sensor_3": [np.nan, np.nan, 182.0, np.nan, np.nan]   # Only 1 valid reading
        })
        
        temp_columns = ["sensor_1", "sensor_2", "sensor_3"]
        
        with pytest.raises(DecisionError, match="Insufficient valid sensors"):
            combine_sensor_readings(df, temp_columns, SensorMode.MIN_OF_SET, require_at_least=2)
    
    def test_majority_threshold_missing_threshold(self, simple_temp_data):
        """Test majority_over_threshold mode without threshold_C."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        
        with pytest.raises(DecisionError, match="threshold_C required"):
            combine_sensor_readings(
                simple_temp_data, temp_columns, SensorMode.MAJORITY_OVER_THRESHOLD
            )
    
    def test_unknown_sensor_mode(self, simple_temp_data):
        """Test combine_sensor_readings with unknown sensor mode."""
        temp_columns = ["pmt_sensor_1", "pmt_sensor_2"]
        
        # Create an invalid sensor mode by mocking
        with patch('core.decide.SensorMode') as mock_mode:
            mock_mode.MIN_OF_SET = SensorMode.MIN_OF_SET
            mock_mode.MEAN_OF_SET = SensorMode.MEAN_OF_SET
            mock_mode.MAJORITY_OVER_THRESHOLD = SensorMode.MAJORITY_OVER_THRESHOLD
            
            with pytest.raises(DecisionError, match="Unknown sensor combination mode"):
                combine_sensor_readings(simple_temp_data, temp_columns, "INVALID_MODE")
    
    def test_majority_without_require_at_least(self):
        """Test majority_over_threshold mode without require_at_least (uses majority)."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0, 183.0, 183.0, 183.0, 183.0],  # Above threshold
            "sensor_2": [182.5, 183.5, 183.5, 183.5, 183.5],  # Above threshold  
            "sensor_3": [180.0, 184.0, 184.0, 184.0, 184.0]   # Above threshold (except first)
        })
        
        temp_columns = ["sensor_1", "sensor_2", "sensor_3"]
        threshold_C = 182.0
        
        combined = combine_sensor_readings(
            df, temp_columns, SensorMode.MAJORITY_OVER_THRESHOLD,
            threshold_C=threshold_C
        )
        
        # First row: 2/3 sensors above threshold (majority) -> True
        # Rest: all 3 sensors above threshold -> True
        expected = pd.Series([True, True, True, True, True])
        pd.testing.assert_series_equal(combined, expected, check_names=False)


class TestDetectTemperatureColumns:
    """Test temperature column detection edge cases."""
    
    def test_non_numeric_temperature_columns(self):
        """Test that non-numeric columns are excluded even if they match patterns."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temperature_string": ["hot", "warm", "cold"],  # String data
            "temp_numeric": [180.0, 181.0, 182.0],         # Numeric data
            "time_series": ["12:00", "12:01", "12:02"]     # Contains 'time' but not temperature
        })
        
        temp_columns = detect_temperature_columns(df)
        
        assert temp_columns == ["temp_numeric"]
    
    def test_various_temperature_patterns(self):
        """Test detection of various temperature column naming patterns."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "Temperature": [180.0, 181.0, 182.0],           # Capitalized
            "temp_C": [180.0, 181.0, 182.0],               # Celsius suffix
            "temp_F": [356.0, 357.8, 359.6],               # Fahrenheit suffix
            "PMT_1": [180.0, 181.0, 182.0],                # PMT pattern
            "sensor_A": [180.0, 181.0, 182.0],             # Sensor pattern
            "degC_probe": [180.0, 181.0, 182.0],           # degC pattern
            "°C_reading": [180.0, 181.0, 182.0],           # Degree symbol
            "pressure": [1013.25, 1013.30, 1013.35]        # Should be excluded
        })
        
        temp_columns = detect_temperature_columns(df)
        
        expected_columns = [
            "Temperature", "temp_C", "temp_F", "PMT_1", 
            "sensor_A", "degC_probe", "°C_reading"
        ]
        
        assert set(temp_columns) == set(expected_columns)
        assert "pressure" not in temp_columns
        assert "timestamp" not in temp_columns


class TestRampRateCalculation:
    """Test calculate_ramp_rate function."""
    
    def test_basic_ramp_rate_calculation(self):
        """Test basic ramp rate calculation."""
        # Create temperature data with known ramp rate
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="60s", tz="UTC")
        temperatures = pd.Series([20.0, 25.0, 30.0, 35.0, 40.0])  # 5°C per minute
        
        ramp_rates = calculate_ramp_rate(temperatures, timestamps)
        
        # First value will be NaN due to diff(), rest should be ~5.0 °C/min
        assert pd.isna(ramp_rates.iloc[0])
        # Allow some tolerance for floating point arithmetic
        for i in range(1, len(ramp_rates)):
            assert abs(ramp_rates.iloc[i] - 5.0) < 1.0
    
    def test_negative_ramp_rate(self):
        """Test ramp rate calculation with cooling (negative rates)."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=4, freq="60s", tz="UTC")
        temperatures = pd.Series([100.0, 90.0, 80.0, 70.0])  # -10°C per minute
        
        ramp_rates = calculate_ramp_rate(temperatures, timestamps)
        
        # First value will be NaN due to diff(), rest should be ~-10.0 °C/min
        assert pd.isna(ramp_rates.iloc[0])
        # Allow some tolerance for floating point arithmetic
        for i in range(1, len(ramp_rates)):
            assert abs(ramp_rates.iloc[i] - (-10.0)) < 1.0
    
    def test_variable_time_intervals(self):
        """Test ramp rate with variable time intervals."""
        timestamps = pd.Series([
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:01:00Z"),  # 1 minute
            pd.Timestamp("2024-01-15T10:03:00Z"),  # 2 minutes
            pd.Timestamp("2024-01-15T10:04:30Z"),  # 1.5 minutes
        ])
        temperatures = pd.Series([20.0, 25.0, 35.0, 42.0])
        
        ramp_rates = calculate_ramp_rate(temperatures, timestamps)
        
        assert pd.isna(ramp_rates.iloc[0])
        assert abs(ramp_rates.iloc[1] - 5.0) < 0.1    # 5°C / 1 min = 5°C/min
        assert abs(ramp_rates.iloc[2] - 5.0) < 0.1    # 10°C / 2 min = 5°C/min
        assert abs(ramp_rates.iloc[3] - 4.67) < 0.2   # 7°C / 1.5 min ≈ 4.67°C/min


class TestFindThresholdCrossingTime:
    """Test find_threshold_crossing_time function."""
    
    def test_threshold_reached(self):
        """Test finding threshold crossing time when threshold is reached."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=6, freq="30s", tz="UTC")
        temperatures = pd.Series([170.0, 175.0, 180.0, 185.0, 186.0, 187.0])
        threshold_C = 182.0
        
        crossing_time = find_threshold_crossing_time(temperatures, timestamps, threshold_C)
        
        # Should find crossing at index 3 (185.0 >= 182.0)  
        # Time = 3 * 30 seconds = 90 seconds
        assert crossing_time == 90.0
    
    def test_threshold_never_reached(self):
        """Test finding threshold crossing time when threshold is never reached."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        temperatures = pd.Series([170.0, 175.0, 180.0, 181.0, 181.5])
        threshold_C = 182.0
        
        crossing_time = find_threshold_crossing_time(temperatures, timestamps, threshold_C)
        
        assert crossing_time is None
    
    def test_threshold_reached_immediately(self):
        """Test finding threshold crossing time when threshold is reached immediately."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        temperatures = pd.Series([185.0, 186.0, 187.0, 188.0, 189.0])
        threshold_C = 182.0
        
        crossing_time = find_threshold_crossing_time(temperatures, timestamps, threshold_C)
        
        # Should find crossing at index 0
        assert crossing_time == 0.0


class TestContinuousHoldTime:
    """Test calculate_continuous_hold_time function edge cases."""
    
    def test_insufficient_data_points(self):
        """Test continuous hold time with insufficient data points."""
        timestamps = pd.Series([pd.Timestamp("2024-01-15T10:00:00Z")])
        temperatures = pd.Series([185.0])
        
        hold_time, start_idx, end_idx = calculate_continuous_hold_time(
            temperatures, timestamps, 182.0
        )
        
        assert hold_time == 0.0
        assert start_idx == -1
        assert end_idx == -1
    
    def test_no_intervals_above_threshold(self):
        """Test continuous hold time when no intervals are above threshold."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        temperatures = pd.Series([170.0, 175.0, 180.0, 181.0, 181.5])
        
        hold_time, start_idx, end_idx = calculate_continuous_hold_time(
            temperatures, timestamps, 182.0
        )
        
        assert hold_time == 0.0
        assert start_idx == -1
        assert end_idx == -1


class TestBooleanHoldTime:
    """Test calculate_boolean_hold_time function."""
    
    def test_insufficient_data_boolean(self):
        """Test boolean hold time with insufficient data."""
        timestamps = pd.Series([pd.Timestamp("2024-01-15T10:00:00Z")])
        boolean_series = pd.Series([True])
        
        hold_time = calculate_boolean_hold_time(boolean_series, timestamps, continuous=True)
        
        assert hold_time == 0.0
    
    def test_continuous_boolean_no_intervals(self):
        """Test continuous boolean hold time with no True intervals."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        boolean_series = pd.Series([False, False, False, False, False])
        
        hold_time = calculate_boolean_hold_time(boolean_series, timestamps, continuous=True)
        
        assert hold_time == 0.0
    
    def test_cumulative_boolean_exceeds_dips(self):
        """Test cumulative boolean hold time when dips exceed limit."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC")
        # Pattern: True, True, False, False, False, True, True, False, False, False
        # Total False periods: 5 intervals * 30s = 150s > 60s max_dips
        boolean_series = pd.Series([True, True, False, False, False, True, True, False, False, False])
        
        hold_time = calculate_boolean_hold_time(
            boolean_series, timestamps, continuous=False, max_dips_s=60
        )
        
        assert hold_time == 0.0
    
    def test_cumulative_boolean_within_dips(self):
        """Test cumulative boolean hold time when dips are within limit."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=8, freq="30s", tz="UTC")
        # Pattern: True, True, False, True, True, True, True, True
        # False periods: 1 interval * 30s = 30s < 60s max_dips
        boolean_series = pd.Series([True, True, False, True, True, True, True, True])
        
        hold_time = calculate_boolean_hold_time(
            boolean_series, timestamps, continuous=False, max_dips_s=60
        )
        
        # Should count all True periods: 7 intervals * 30s = 210s
        assert hold_time == 210.0


class TestCumulativeHoldTime:
    """Test calculate_cumulative_hold_time function edge cases."""
    
    def test_insufficient_data_cumulative(self):
        """Test cumulative hold time with insufficient data."""
        timestamps = pd.Series([pd.Timestamp("2024-01-15T10:00:00Z")])
        temperatures = pd.Series([185.0])
        
        hold_time, intervals = calculate_cumulative_hold_time(
            temperatures, timestamps, 182.0, 60
        )
        
        assert hold_time == 0.0
        assert intervals == []
    
    def test_total_dips_within_allowance(self):
        """Test cumulative hold time when total dips are within allowance."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=8, freq="30s", tz="UTC")
        # Pattern: above 60s, below 30s, above 60s, below 30s (60s total dips < 120s allowance)
        temperatures = pd.Series([185.0, 185.0, 180.0, 185.0, 185.0, 180.0, 185.0, 185.0])
        
        hold_time, intervals = calculate_cumulative_hold_time(
            temperatures, timestamps, 182.0, 120
        )
        
        # Should count all above intervals: 6 intervals * 30s = 180s
        assert hold_time == 180.0
        assert len(intervals) == 3  # Three intervals above threshold


class TestIndustrySpecificDispatch:
    """Test industry-specific validation engine dispatch."""
    
    def test_industry_specific_engine_available(self, simple_temp_data):
        """Test dispatch to industry-specific engine when available."""
        spec_data = {
            "version": "1.0",
            "industry": "haccp",  # Specify HACCP industry
            "job": {"job_id": "haccp_test"},
            "spec": {"method": "PMT", "target_temp_C": 5.0, "hold_time_s": 300, "sensor_uncertainty_C": 1.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        # Mock the HACCP validation function
        mock_result = DecisionResult(
            pass_=True,
            job_id="haccp_test",
            target_temp_C=5.0,
            conservative_threshold_C=6.0,
            actual_hold_time_s=300.0,
            required_hold_time_s=300,
            max_temp_C=4.5,
            min_temp_C=4.0,
            reasons=["HACCP validation passed"],
            warnings=[]
        )
        
        # Patch INDUSTRY_METRICS to have a mock function
        with patch.dict('core.decide.INDUSTRY_METRICS', {'haccp': MagicMock(return_value=mock_result)}):
            result = make_decision(simple_temp_data, spec)
            assert result.reasons == ["HACCP validation passed"]
    
    def test_industry_specific_engine_failure_fallback(self, simple_temp_data):
        """Test fallback to default validation when industry-specific engine fails."""
        spec_data = {
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "sterile_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        # Mock the sterile validation function to raise an exception
        mock_engine = MagicMock(side_effect=Exception("Engine failed"))
        with patch.dict('core.decide.INDUSTRY_METRICS', {'sterile': mock_engine}):
            result = make_decision(simple_temp_data, spec)
            
            # Should fall back to default powder coat validation
            assert isinstance(result, DecisionResult)
            assert result.job_id == "sterile_test"
    
    def test_unknown_industry_default_validation(self, simple_temp_data):
        """Test default validation for unknown industry."""
        spec_data = {
            "version": "1.0",
            "industry": "unknown_industry",
            "job": {"job_id": "unknown_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(simple_temp_data, spec)
        
        # Should use default powder coat validation
        assert isinstance(result, DecisionResult)
        assert result.job_id == "unknown_test"


class TestDecisionErrorConditions:
    """Test various error conditions in make_decision."""
    
    def test_empty_dataframe_decision_error(self, example_spec):
        """Test decision with empty DataFrame."""
        df = pd.DataFrame()
        
        with pytest.raises(DecisionError, match="Normalized DataFrame is empty"):
            make_decision(df, example_spec)
    
    def test_insufficient_data_points_decision_error(self, example_spec):
        """Test decision with insufficient data points."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-15T10:00:00Z")]
        })
        
        with pytest.raises(DecisionError, match="Insufficient data points"):
            make_decision(df, example_spec)
    
    def test_no_timestamp_column_error(self, example_spec):
        """Test decision with no timestamp column."""
        df = pd.DataFrame({
            "pmt_sensor_1": [180.0, 181.0, 182.0],
            "pmt_sensor_2": [179.0, 180.0, 181.0]
        })
        
        with pytest.raises(DecisionError, match="No timestamp column found"):
            make_decision(df, example_spec)
    
    def test_no_temperature_columns_error(self, example_spec):
        """Test decision with no temperature columns."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC"),
            "pressure": [1013.25] * 10,
            "humidity": [50.0] * 10
        })
        
        with pytest.raises(DecisionError, match="No temperature columns found"):
            make_decision(df, example_spec)
    
    def test_all_sensors_failed_error(self, example_spec):
        """Test decision when all sensors have failed (all NaN)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC"),
            "pmt_sensor_1": [np.nan] * 10,
            "pmt_sensor_2": [np.nan] * 10
        })
        
        with pytest.raises(DecisionError, match="All temperature sensors have failed"):
            make_decision(df, example_spec)
    
    def test_specified_sensors_not_found_error(self):
        """Test decision when specified sensors are not found."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC"),
            "temp_A": [180.0] * 10,
            "temp_B": [181.0] * 10
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_error_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["missing_sensor_1", "missing_sensor_2"],
                "require_at_least": 1
            }
        }
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="None of specified sensors found"):
            make_decision(df, spec)


class TestPreconditionsValidation:
    """Test preconditions validation in decision making."""
    
    def test_ramp_rate_validation(self):
        """Test ramp rate precondition validation."""
        # Create data with high ramp rate (>10°C/min)
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=8, freq="30s", tz="UTC")
        # Very fast heating: 20°C in 30s = 40°C/min
        temperatures = [160.0, 180.0, 185.0, 185.0, 185.0, 185.0, 185.0, 185.0]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temperatures,
            "pmt_sensor_2": [t - 1.0 for t in temperatures]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "ramp_rate_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0  # Should be exceeded
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert any("Ramp rate too high" in reason for reason in result.reasons)
    
    def test_time_to_threshold_validation(self):
        """Test time to threshold precondition validation."""
        # Create data that takes too long to reach threshold
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        # Slow heating: doesn't reach threshold until 7 minutes (420s)
        temperatures = [160.0] * 10 + [182.0] * 5  # Reaches threshold at index 10 = 300s
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temperatures,
            "pmt_sensor_2": [t - 1.0 for t in temperatures]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "time_to_threshold_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 60, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "preconditions": {
                "max_time_to_threshold_s": 120  # Should be exceeded (300s > 120s)
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert any("Time to threshold too long" in reason for reason in result.reasons)


class TestCumulativeHoldTimeLogic:
    """Test cumulative hold time logic in decision making."""
    
    def test_cumulative_mode_pass(self):
        """Test cumulative hold time mode that passes."""
        # Create data with brief dips but sufficient cumulative time
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        # Pattern: above threshold with brief dips
        temperatures = [185.0] * 5 + [180.0] * 2 + [185.0] * 8  # 13 * 30s = 390s above
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temperatures,
            "pmt_sensor_2": [t - 1.0 for t in temperatures]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "cumulative_pass_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "logic": {
                "continuous": False,
                "max_total_dips_s": 120  # Allow up to 2 minutes of dips
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert result.pass_ is True
        assert any("Cumulative hold time requirement met" in reason for reason in result.reasons)
    
    def test_cumulative_mode_fail(self):
        """Test cumulative hold time mode that fails."""
        # Create data with too many dips
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        # Pattern: above threshold with too many dips
        temperatures = [185.0] * 3 + [180.0] * 9 + [185.0] * 3  # Only 6 * 30s = 180s above
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temperatures,
            "pmt_sensor_2": [t - 1.0 for t in temperatures]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "cumulative_fail_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "logic": {
                "continuous": False,
                "max_total_dips_s": 60  # Allow only 1 minute of dips (but we have 4.5 minutes)
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert any("Insufficient cumulative hold time" in reason for reason in result.reasons)


class TestDuplicateTimestamps:
    """Test handling of duplicate timestamps and edge cases."""
    
    def test_duplicate_timestamps_handling(self, example_spec):
        """Test decision making with duplicate timestamps."""
        # Create data with duplicate timestamps
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),  # Duplicate
            pd.Timestamp("2024-01-15T10:01:00Z"),
            pd.Timestamp("2024-01-15T10:01:30Z")
        ] + [pd.Timestamp("2024-01-15T10:00:00Z") + timedelta(seconds=120 + i*30) for i in range(20)]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": [185.0] * len(timestamps),
            "pmt_sensor_2": [184.0] * len(timestamps)
        })
        
        result = make_decision(df, example_spec)
        
        # Should handle duplicates gracefully and still make a decision
        assert isinstance(result, DecisionResult)
    
    def test_fahrenheit_conversion_edge_cases(self):
        """Test Fahrenheit conversion with edge temperature values."""
        # Test with extreme temperature values in Fahrenheit
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC")
        
        # Fahrenheit temperatures that convert to reasonable Celsius values
        # 356°F = 180°C, 365°F ≈ 185°C  
        fahrenheit_temps = [356.0] * 3 + [365.0] * 7
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_f_1": fahrenheit_temps,
            "temp_f_2": [t + 2.0 for t in fahrenheit_temps]  # Slightly higher
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "fahrenheit_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 180, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        # Need to normalize the data first to convert Fahrenheit to Celsius
        from core.normalize import normalize_temperature_data
        normalized_df = normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        
        result = make_decision(normalized_df, spec)
        
        assert isinstance(result, DecisionResult)
        # Should successfully process Fahrenheit data
        assert result.target_temp_C == 180.0


class TestMajorityBoundaries:
    """Test majority sensor mode boundary conditions."""
    
    def test_exactly_half_sensors_above_threshold(self):
        """Test majority mode when exactly half the sensors are above threshold."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0] * 5,  # Above threshold
            "sensor_2": [183.0] * 5,  # Above threshold
            "sensor_3": [180.0] * 5,  # Below threshold  
            "sensor_4": [180.0] * 5   # Below threshold
        })
        
        temp_columns = ["sensor_1", "sensor_2", "sensor_3", "sensor_4"]
        threshold_C = 182.0
        
        combined = combine_sensor_readings(
            df, temp_columns, SensorMode.MAJORITY_OVER_THRESHOLD,
            threshold_C=threshold_C
        )
        
        # Exactly 2/4 = 50% above threshold -> should be False (need >50%)
        expected = pd.Series([False] * 5)
        pd.testing.assert_series_equal(combined, expected, check_names=False)
    
    def test_one_more_than_half_above_threshold(self):
        """Test majority mode when just over half are above threshold."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0] * 5,  # Above threshold
            "sensor_2": [183.0] * 5,  # Above threshold
            "sensor_3": [183.0] * 5,  # Above threshold
            "sensor_4": [180.0] * 5,  # Below threshold
            "sensor_5": [180.0] * 5   # Below threshold
        })
        
        temp_columns = ["sensor_1", "sensor_2", "sensor_3", "sensor_4", "sensor_5"]
        threshold_C = 182.0
        
        combined = combine_sensor_readings(
            df, temp_columns, SensorMode.MAJORITY_OVER_THRESHOLD,
            threshold_C=threshold_C
        )
        
        # 3/5 = 60% above threshold -> should be True (>50%)
        expected = pd.Series([True] * 5)
        pd.testing.assert_series_equal(combined, expected, check_names=False)


class TestBooleanModeDecisionMaking:
    """Test decision making with boolean sensor combination results."""
    
    def test_boolean_mode_continuous_pass(self):
        """Test decision making with boolean mode and continuous logic."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0] * 15,  # Always above threshold
            "sensor_2": [183.0] * 15,  # Always above threshold
            "sensor_3": [180.0] * 5 + [183.0] * 10  # Above threshold for last 10 intervals
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "boolean_continuous_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 240, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "sensors": ["sensor_1", "sensor_2", "sensor_3"],
                "require_at_least": 2
            },
            "logic": {"continuous": True, "max_total_dips_s": 0}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
        # Should handle boolean mode correctly
        assert result.actual_hold_time_s >= 240.0
    
    def test_boolean_mode_cumulative_pass(self):
        """Test decision making with boolean mode and cumulative logic."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0] * 15,  # Always above threshold
            "sensor_2": [183.0] * 15,  # Always above threshold  
            "sensor_3": [180.0] * 3 + [183.0] * 5 + [180.0] * 2 + [183.0] * 5
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "boolean_cumulative_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "sensors": ["sensor_1", "sensor_2", "sensor_3"],
                "require_at_least": 2
            },
            "logic": {"continuous": False, "max_total_dips_s": 120}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
        # Should handle boolean cumulative mode correctly
        assert result.actual_hold_time_s >= 300.0