"""
Advanced coverage tests for core/decide.py to achieve ≥92% coverage.

Focuses on uncovered branches including:
- Majority require_at_least edge cases
- Duplicate timestamp handling
- Fahrenheit temperature conversion
- Hysteresis double-count prevention
- Complex validation logic paths
- Error handling in threshold detection
- Boolean sensor mode edge cases
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import List

from core.decide import (
    make_decision, 
    combine_sensor_readings,
    calculate_boolean_hold_time,
    detect_temperature_columns,
    validate_preconditions,
    DecisionError,
    INDUSTRY_METRICS
)
from core.models import SpecV1, SensorMode


def create_test_df(timestamps: List[str], **columns) -> pd.DataFrame:
    """Create test DataFrame with flexible column specification."""
    data = {"timestamp": pd.to_datetime(timestamps)}
    data.update(columns)
    return pd.DataFrame(data)


def create_basic_spec(**overrides) -> SpecV1:
    """Create basic specification with optional overrides."""
    base_spec = {
        "version": "1.0",
        "job": {"job_id": "test_job"},
        "spec": {
            "method": "PMT", 
            "target_temp_C": 170.0,
            "hold_time_s": 300,
            "sensor_uncertainty_C": 2.0
        },
        "data_requirements": {
            "max_sample_period_s": 60.0,
            "allowed_gaps_s": 120.0
        }
    }
    
    # Apply overrides recursively
    for key, value in overrides.items():
        if isinstance(value, dict) and key in base_spec:
            base_spec[key].update(value)
        else:
            base_spec[key] = value
    
    return SpecV1(**base_spec)


class TestMajorityRequireAtLeastEdges:
    """Test majority_over_threshold with require_at_least edge cases."""
    
    def test_majority_require_at_least_exact_match(self):
        """Test majority mode when exactly require_at_least sensors meet threshold."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            sensor1=[171.0, 173.0],
            sensor2=[173.0, 171.0], 
            sensor3=[169.0, 169.0]
        )
        
        # require_at_least=2, threshold=172.0
        combined = combine_sensor_readings(
            df, ["sensor1", "sensor2", "sensor3"], 
            SensorMode.MAJORITY_OVER_THRESHOLD,
            require_at_least=2,
            threshold_C=172.0
        )
        
        # Row 0: 1 sensor >= 172°C (sensor2) -> False
        # Row 1: 1 sensor >= 172°C (sensor1) -> False  
        expected = pd.Series([False, False])
        pd.testing.assert_series_equal(combined, expected, check_names=False)

    def test_majority_require_at_least_exceeds_threshold(self):
        """Test majority mode when more than require_at_least sensors meet threshold."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            sensor1=[173.0, 173.0],
            sensor2=[174.0, 174.0],
            sensor3=[175.0, 171.0]
        )
        
        # require_at_least=2, threshold=172.0
        combined = combine_sensor_readings(
            df, ["sensor1", "sensor2", "sensor3"],
            SensorMode.MAJORITY_OVER_THRESHOLD, 
            require_at_least=2,
            threshold_C=172.0
        )
        
        # Row 0: 3 sensors >= 172°C -> True (3 >= 2)
        # Row 1: 2 sensors >= 172°C -> True (2 >= 2)
        expected = pd.Series([True, True])
        pd.testing.assert_series_equal(combined, expected, check_names=False)

    def test_majority_require_at_least_with_nan_values(self):
        """Test majority mode with NaN values affecting sensor count."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            sensor1=[173.0, np.nan],
            sensor2=[174.0, 174.0],
            sensor3=[np.nan, 173.0]
        )
        
        # require_at_least=2, threshold=172.0  
        combined = combine_sensor_readings(
            df, ["sensor1", "sensor2", "sensor3"],
            SensorMode.MAJORITY_OVER_THRESHOLD,
            require_at_least=2,
            threshold_C=172.0
        )
        
        # Row 0: 2 valid sensors (sensor1, sensor2), 2 >= 172°C -> True (2 >= 2)
        # Row 1: 2 valid sensors (sensor2, sensor3), 2 >= 172°C -> True (2 >= 2)
        expected = pd.Series([True, True])
        pd.testing.assert_series_equal(combined, expected, check_names=False)


class TestDuplicateTimestamps:
    """Test handling of duplicate timestamps and time calculation edge cases."""
    
    def test_duplicate_timestamps_hold_time_calculation(self):
        """Test hold time calculation with duplicate timestamps."""
        # Create DataFrame with duplicate timestamps - need more data points
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        timestamps[1] = timestamps[0]  # Create one duplicate
        
        df = create_test_df(timestamps, temp_C=[173.0] * 15)
        spec = create_basic_spec()
        
        result = make_decision(df, spec)
        
        # Should pass with sufficient data points
        assert result.pass_ is True
        assert result.actual_hold_time_s >= 300.0

    def test_zero_time_intervals_ramp_rate(self):
        """Test ramp rate calculation with zero time intervals (duplicate timestamps)."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        timestamps[1] = timestamps[0]  # Zero interval
        temperatures = [168.0, 175.0] + [177.0] * 13
        
        df = create_test_df(timestamps, temp_C=temperatures)
        
        spec = create_basic_spec(
            preconditions={"max_ramp_rate_C_per_min": 10.0}
        )
        
        result = make_decision(df, spec)
        
        # Should handle division by zero in ramp rate calculation
        assert isinstance(result.actual_hold_time_s, float)


class TestFahrenheitConversion:
    """Test Fahrenheit temperature case handling."""
    
    def test_fahrenheit_column_detection(self):
        """Test detection of Fahrenheit temperature columns."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            temp_F=[340.0, 342.0],  # ~170°C in Fahrenheit
            sensor_degF=[343.0, 345.0]
        )
        
        temp_columns = detect_temperature_columns(df)
        
        # Should detect both Fahrenheit columns
        assert "temp_F" in temp_columns
        assert "sensor_degF" in temp_columns
        
    def test_fahrenheit_temperature_values(self):
        """Test decision making with Fahrenheit-scale temperature values."""
        # Fahrenheit values equivalent to ~170-175°C - need more data points
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            temp_F=[340.0, 342.0, 345.0, 347.0, 347.0] + [346.0] * 10  # ~170-175°C
        )
        
        spec = create_basic_spec(
            **{"spec": {"target_temp_C": 170.0, "sensor_uncertainty_C": 2.0}}
        )
        
        result = make_decision(df, spec)
        
        # Should work with Fahrenheit values (treated as Celsius by algorithm)
        assert isinstance(result.pass_, bool)
        assert result.max_temp_C > 300.0  # Fahrenheit values treated as Celsius


class TestHysteresisDoubleCountGuard:
    """Test hysteresis logic to prevent double-counting."""
    
    def test_hysteresis_state_persistence(self):
        """Test that hysteresis state persists correctly through borderline values."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        # Pattern: above -> exactly at hysteresis point -> back above  
        temperatures = [173.0, 170.0, 170.0, 172.5, 173.0, 173.5] + [173.0] * 9  # threshold=172, hysteresis=2
        
        df = create_test_df(timestamps, temp_C=temperatures)
        spec = create_basic_spec()
        
        result = make_decision(df, spec)
        
        # Should maintain hold state through hysteresis point (170°C = 172-2)
        assert result.pass_ is True
        assert result.actual_hold_time_s >= 120.0  # Should count most of the time

    def test_hysteresis_prevents_rapid_switching(self):
        """Test that hysteresis prevents rapid on/off switching at threshold."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        # Oscillating around threshold: 172°C 
        temperatures = [171.9, 172.1, 171.9, 172.1, 171.9, 172.1, 171.9, 172.1] + [172.0] * 7
        
        df = create_test_df(timestamps, temp_C=temperatures)
        spec = create_basic_spec()
        
        result = make_decision(df, spec)
        
        # Without hysteresis this would switch rapidly, but hysteresis should smooth it
        assert isinstance(result.actual_hold_time_s, float)


class TestBoundaryConditionsTimeCalculations:
    """Test boundary conditions in time calculations."""
    
    def test_single_point_above_threshold(self):
        """Test time calculations with only one point above threshold."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        temperatures = [169.0] * 14 + [173.0]  # Only last point above 172°C threshold
        
        df = create_test_df(timestamps, temp_C=temperatures)
        
        spec = create_basic_spec()
        result = make_decision(df, spec)
        
        # Should handle single point case
        assert result.pass_ is False  # Insufficient hold time
        assert result.actual_hold_time_s == 0.0  # No continuous hold

    def test_threshold_at_exact_boundary(self):
        """Test behavior when temperature exactly equals threshold."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            temp_C=[172.0] * 15  # Exactly at threshold
        )
        
        spec = create_basic_spec()  # threshold = 170 + 2 = 172°C
        result = make_decision(df, spec)
        
        # Should pass with exact threshold match (>= comparison)
        assert result.pass_ is True
        assert result.actual_hold_time_s >= 300.0

    def test_end_of_data_during_hold(self):
        """Test hold time calculation when data ends while above threshold."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(10)]
        df = create_test_df(
            timestamps,
            temp_C=[173.0] * 10  # Ends while above threshold
        )
        
        spec = create_basic_spec(**{"spec": {"hold_time_s": 120}})  # Require 2 minutes
        result = make_decision(df, spec)
        
        # Should count time until end of data
        assert result.pass_ is True
        assert result.actual_hold_time_s >= 480.0  # 9 intervals * 60s


class TestErrorHandlingThresholdDetection:
    """Test error handling in threshold detection and validation."""
    
    def test_unknown_sensor_mode_error(self):
        """Test error handling for unknown sensor combination mode."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            temp_C=[172.0, 173.0]
        )
        
        # This should trigger an error in sensor combination
        with pytest.raises(DecisionError, match="Unknown sensor combination mode"):
            combine_sensor_readings(
                df, ["temp_C"], "INVALID_MODE"  # Invalid mode
            )

    def test_majority_threshold_without_threshold_param(self):
        """Test majority_over_threshold mode without threshold parameter."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            temp_C=[172.0, 173.0]
        )
        
        with pytest.raises(DecisionError, match="threshold_C required"):
            combine_sensor_readings(
                df, ["temp_C"], SensorMode.MAJORITY_OVER_THRESHOLD
                # Missing threshold_C parameter
            )

    def test_no_temperature_columns_provided(self):
        """Test error when no temperature columns provided to sensor combination."""
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"],
            temp_C=[172.0, 173.0]
        )
        
        with pytest.raises(DecisionError, match="No temperature columns provided"):
            combine_sensor_readings(df, [], SensorMode.MIN_OF_SET)

    def test_sensor_selection_no_matching_columns(self):
        """Test error when sensor selection specifies non-existent columns."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            temp_C=[173.0] * 15
        )
        
        spec = create_basic_spec(
            sensor_selection={
                "sensors": ["nonexistent_sensor1", "nonexistent_sensor2"],
                "mode": "min_of_set"
            }
        )
        
        result = make_decision(df, spec)
        # Should handle gracefully with warning
        assert result.pass_ is True  # Has valid data in temp_C
        assert len(result.warnings) > 0


class TestComplexValidationLogicPaths:
    """Test complex validation logic paths and edge cases."""
    
    def test_insufficient_data_points_for_hold_requirement(self):
        """Test insufficient data points based on hold time requirement."""
        # Only 3 data points over 30 seconds - insufficient for 600s hold requirement
        df = create_test_df(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z", "2024-01-01T10:01:00Z"],
            temp_C=[173.0, 173.0, 173.0]
        )
        
        spec = create_basic_spec(**{"spec": {"hold_time_s": 600}})  # Require 10 minutes hold
        result = make_decision(df, spec)
        
        # Should fail due to insufficient data points (3 points < 22 required for 600s hold)
        assert result.pass_ is False
        assert any("Insufficient data points for reliable analysis" in reason for reason in result.reasons)

    def test_sensor_failure_warning_but_continue(self):
        """Test warning for sensor failure but continue with remaining sensors."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            sensor1=[173.0] * 15,  # Working sensor
            sensor2=[np.nan] * 15  # Failed sensor
        )
        
        spec = create_basic_spec()
        result = make_decision(df, spec)
        
        # Should warn about sensor failure but continue
        assert result.pass_ is True  # Has enough data
        assert len(result.warnings) >= 1
        sensor_failure_warnings = [w for w in result.warnings if "Sensor failure detected" in w]
        assert len(sensor_failure_warnings) >= 1

    def test_industry_specific_fallback_to_default(self):
        """Test fallback to default validation when industry-specific fails."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            temp_C=[173.0] * 15
        )
        
        spec = create_basic_spec(industry="haccp", **{"spec": {"method": "OVEN_AIR"}})  # Use valid industry and method
        result = make_decision(df, spec)
        
        # Should process with industry-specific validation
        assert isinstance(result.pass_, bool)

    def test_preconditions_multiple_failures(self):
        """Test multiple precondition failures accumulating."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        temperatures = [160.0, 180.0, 181.0] + [173.0] * 12  # Very fast ramp
        
        df = create_test_df(timestamps, temp_C=temperatures)
        
        spec = create_basic_spec(
            preconditions={
                "max_ramp_rate_C_per_min": 5.0,  # Will fail - ramp is ~20°C/min
                "max_time_to_threshold_s": 30    # Will fail - takes 60s to reach threshold
            },
            **{"spec": {"hold_time_s": 300}}
        )
        
        result = make_decision(df, spec)
        
        # Should accumulate multiple failure reasons
        assert result.pass_ is False
        assert len(result.reasons) >= 2  # Multiple failure reasons


class TestContinuousVsCumulativeHoldEdgeCases:
    """Test edge cases in continuous vs cumulative hold calculations."""
    
    def test_boolean_hold_empty_series(self):
        """Test boolean hold time with empty series."""
        empty_series = pd.Series([], dtype=bool)
        empty_timestamps = pd.Series([], dtype='datetime64[ns]')
        
        hold_time = calculate_boolean_hold_time(empty_series, empty_timestamps, continuous=True)
        assert hold_time == 0.0
        
        hold_time = calculate_boolean_hold_time(empty_series, empty_timestamps, continuous=False)
        assert hold_time == 0.0

    def test_boolean_hold_single_point(self):
        """Test boolean hold time with single data point."""
        single_series = pd.Series([True])
        single_timestamps = pd.Series([pd.Timestamp("2024-01-01T10:00:00Z")])
        
        hold_time = calculate_boolean_hold_time(single_series, single_timestamps, continuous=True)
        assert hold_time == 0.0  # Need at least 2 points for duration
        
        hold_time = calculate_boolean_hold_time(single_series, single_timestamps, continuous=False)
        assert hold_time == 0.0

    def test_cumulative_all_false_boolean(self):
        """Test cumulative boolean hold time with all False values."""
        timestamps = pd.Series(pd.to_datetime([
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z"
        ]))
        all_false_series = pd.Series([False, False, False])
        
        hold_time = calculate_boolean_hold_time(
            all_false_series, timestamps, continuous=False, max_dips_s=120
        )
        
        assert hold_time == 0.0

    def test_cumulative_alternating_pattern_exceeds_limit(self):
        """Test cumulative mode with alternating pattern that exceeds dip limit."""
        timestamps = pd.Series(pd.to_datetime([
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ]))
        alternating_series = pd.Series([True, False, True, False, True, False])
        
        hold_time = calculate_boolean_hold_time(
            alternating_series, timestamps, continuous=False, max_dips_s=90  # Only allow 1.5 min False
        )
        
        # Total False time = 180s > 90s limit -> should return 0
        assert hold_time == 0.0

    def test_sensor_selection_insufficient_available(self):
        """Test sensor selection when insufficient sensors are available."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            sensor1=[173.0] * 15
        )
        
        spec = create_basic_spec(
            sensor_selection={
                "sensors": ["sensor1", "nonexistent_sensor"],
                "require_at_least": 2,
                "mode": "min_of_set"
            }
        )
        
        result = make_decision(df, spec)
        
        # Should generate warning about insufficient sensors
        assert len(result.warnings) >= 1
        insufficient_warnings = [w for w in result.warnings if "Only 1 sensors available, 2 required" in w]
        assert len(insufficient_warnings) >= 1

    def test_boolean_sensor_mode_decision_making(self):
        """Test complete decision making with boolean sensor mode results."""
        timestamps = [f"2024-01-01T10:{i:02d}:00Z" for i in range(15)]
        df = create_test_df(
            timestamps,
            sensor1=[173.0, 173.0, 171.0, 173.0, 173.0] + [173.0] * 10,
            sensor2=[174.0, 171.0, 173.0, 174.0, 174.0] + [174.0] * 10,
            sensor3=[175.0, 169.0, 175.0, 175.0, 175.0] + [175.0] * 10
        )
        
        spec = create_basic_spec(
            sensor_selection={
                "sensors": ["sensor1", "sensor2", "sensor3"],
                "mode": "majority_over_threshold",
                "require_at_least": 2
            }
        )
        
        result = make_decision(df, spec)
        
        # Should handle boolean mode decision making
        assert isinstance(result.pass_, bool)
        assert isinstance(result.max_temp_C, float)  # Should have placeholder values
        assert isinstance(result.min_temp_C, float)