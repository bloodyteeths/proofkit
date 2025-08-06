"""
Parametrized test matrix for decide.py coverage ≥90%.

Tests core decision algorithm functionality with focus on:
- Hysteresis behavior in threshold crossings
- Temperature dips and recovery patterns  
- Time-to-threshold calculations
- Ramp rate validation

Uses small test series (≤25 rows) with helpers from tests/helpers.py.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any

from core.decide import (
    make_decision, 
    calculate_conservative_threshold,
    combine_sensor_readings,
    calculate_ramp_rate,
    find_threshold_crossing_time,
    calculate_continuous_hold_time,
    calculate_cumulative_hold_time,
    calculate_boolean_hold_time,
    detect_temperature_columns,
    validate_preconditions,
    DecisionError
)
from core.models import SpecV1, SensorMode, DecisionResult
from tests.helpers import load_spec_fixture_validated


def create_test_series(
    timestamps: List[str], 
    temperatures: List[float], 
    column_name: str = "temp_C"
) -> pd.DataFrame:
    """Create minimal test DataFrame with timestamp and temperature data."""
    return pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps),
        column_name: temperatures
    })


def create_basic_spec(
    target_temp_C: float = 170.0,
    hold_time_s: int = 300,
    sensor_uncertainty_C: float = 2.0,
    continuous: bool = True,
    max_dips_s: int = 0,
    max_ramp_rate: float = None,
    max_time_to_threshold: int = None
) -> SpecV1:
    """Create basic test specification with configurable parameters."""
    spec_data = {
        "version": "1.0",
        "job": {"job_id": "test_job"},
        "spec": {
            "method": "PMT",
            "target_temp_C": target_temp_C,
            "hold_time_s": hold_time_s,
            "sensor_uncertainty_C": sensor_uncertainty_C
        },
        "data_requirements": {
            "max_sample_period_s": 60.0,
            "allowed_gaps_s": 120.0
        },
        "logic": {
            "continuous": continuous,
            "max_total_dips_s": max_dips_s
        }
    }
    
    if max_ramp_rate is not None or max_time_to_threshold is not None:
        spec_data["preconditions"] = {}
        if max_ramp_rate is not None:
            spec_data["preconditions"]["max_ramp_rate_C_per_min"] = max_ramp_rate
        if max_time_to_threshold is not None:
            spec_data["preconditions"]["max_time_to_threshold_s"] = max_time_to_threshold
    
    return SpecV1(**spec_data)


class TestHysteresisBehavior:
    """Test hysteresis behavior in threshold crossings."""
    
    @pytest.mark.parametrize("hysteresis_C,expected_hold_time", [
        (1.0, 330.0),  # Small hysteresis - longer hold
        (2.0, 240.0),  # Default hysteresis - medium hold  
        (3.0, 150.0),  # Large hysteresis - shorter hold
    ])
    def test_hysteresis_different_values(self, hysteresis_C: float, expected_hold_time: float):
        """Test continuous hold time calculation with different hysteresis values."""
        # Create temperature series that dips below threshold but above hysteresis point
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z", "2024-01-01T10:01:00Z",
            "2024-01-01T10:01:30Z", "2024-01-01T10:02:00Z", "2024-01-01T10:02:30Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:03:30Z", "2024-01-01T10:04:00Z",
            "2024-01-01T10:04:30Z", "2024-01-01T10:05:00Z", "2024-01-01T10:05:30Z",
            "2024-01-01T10:06:00Z", "2024-01-01T10:06:30Z", "2024-01-01T10:07:00Z"
        ]
        temperatures = [
            169.0, 172.5, 173.0, 171.8, 171.5,  # Ramp up, small dip
            172.2, 172.8, 171.2, 171.8, 172.5,  # More dips
            172.0, 171.0, 170.5, 172.2, 172.5   # Final section
        ]
        
        df = create_test_series(timestamps, temperatures)
        threshold_C = 172.0
        time_series = df["timestamp"]
        temp_series = df["temp_C"]
        
        hold_time, start_idx, end_idx = calculate_continuous_hold_time(
            temp_series, time_series, threshold_C, hysteresis_C
        )
        
        # With different hysteresis, we get different hold times
        assert abs(hold_time - expected_hold_time) < 30.0, f"Expected ~{expected_hold_time}s, got {hold_time}s"
        assert start_idx >= 0
        assert end_idx >= start_idx

    def test_hysteresis_prevents_false_drops(self):
        """Test that hysteresis prevents brief dips from ending hold period."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z", "2024-01-01T10:01:00Z",
            "2024-01-01T10:01:30Z", "2024-01-01T10:02:00Z", "2024-01-01T10:02:30Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:03:30Z", "2024-01-01T10:04:00Z",
            "2024-01-01T10:04:30Z"
        ]
        # Threshold: 172°C, Hysteresis: 2°C -> Must drop below 170°C to end hold
        temperatures = [172.5, 173.0, 171.5, 171.8, 172.2, 171.0, 172.5, 172.8, 173.0, 172.5]
        
        df = create_test_series(timestamps, temperatures)
        threshold_C = 172.0
        hysteresis_C = 2.0
        
        hold_time, start_idx, end_idx = calculate_continuous_hold_time(
            df["temp_C"], df["timestamp"], threshold_C, hysteresis_C
        )
        
        # Should maintain hold despite dip to 171.0°C (above 170°C hysteresis point)
        expected_duration = 270.0  # 9 intervals of 30s each
        assert abs(hold_time - expected_duration) < 30.0
        assert start_idx == 0
        assert end_idx == 9

    def test_hysteresis_triggers_drop(self):
        """Test that dropping below hysteresis point ends hold period."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z", "2024-01-01T10:01:00Z",
            "2024-01-01T10:01:30Z", "2024-01-01T10:02:00Z", "2024-01-01T10:02:30Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:03:30Z"
        ]
        # Threshold: 172°C, Hysteresis: 2°C -> Drop below 170°C ends hold
        temperatures = [172.5, 173.0, 172.8, 169.5, 172.0, 172.5, 173.0, 172.2]
        
        df = create_test_series(timestamps, temperatures)
        threshold_C = 172.0
        hysteresis_C = 2.0
        
        hold_time, start_idx, end_idx = calculate_continuous_hold_time(
            df["temp_C"], df["timestamp"], threshold_C, hysteresis_C
        )
        
        # Should end hold after 169.5°C dip at index 3
        expected_duration = 90.0  # 3 intervals of 30s each
        assert abs(hold_time - expected_duration) < 30.0
        assert start_idx == 0
        assert end_idx == 2


class TestTemperatureDips:
    """Test handling of temperature dips and recovery patterns."""
    
    @pytest.mark.parametrize("dip_pattern,continuous_hold,cumulative_hold", [
        # Brief single dip - both modes should handle differently
        ([172.0, 173.0, 169.0, 173.0, 172.5], 60.0, 120.0),
        # Multiple brief dips
        ([172.0, 173.0, 169.0, 172.5, 169.5, 173.0], 30.0, 120.0),
        # No dips - both modes same
        ([172.0, 173.0, 173.5, 173.2, 172.8], 120.0, 120.0),
    ])
    def test_dip_patterns_continuous_vs_cumulative(
        self, dip_pattern: List[float], continuous_hold: float, cumulative_hold: float
    ):
        """Test how different dip patterns affect continuous vs cumulative hold time."""
        timestamps = [f"2024-01-01T10:0{i}:00Z" for i in range(len(dip_pattern))]
        df = create_test_series(timestamps, dip_pattern)
        threshold_C = 172.0
        
        # Test continuous hold
        cont_hold, _, _ = calculate_continuous_hold_time(
            df["temp_C"], df["timestamp"], threshold_C, hysteresis_C=2.0
        )
        
        # Test cumulative hold (allowing 120s of dips)
        cum_hold, _ = calculate_cumulative_hold_time(
            df["temp_C"], df["timestamp"], threshold_C, max_total_dips_s=120
        )
        
        assert abs(cont_hold - continuous_hold) < 30.0, f"Continuous: expected {continuous_hold}, got {cont_hold}"
        assert abs(cum_hold - cumulative_hold) < 30.0, f"Cumulative: expected {cumulative_hold}, got {cum_hold}"

    def test_excessive_dips_fail_cumulative(self):
        """Test that excessive dips cause cumulative mode to fail."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z",
            "2024-01-01T10:06:00Z", "2024-01-01T10:07:00Z"
        ]
        # Pattern: above, below (60s), above, below (60s), above, below (60s), above, above
        # Total dip time: 180s, max allowed: 120s
        temperatures = [173.0, 169.0, 173.0, 169.0, 173.0, 169.0, 173.0, 173.0]
        
        df = create_test_series(timestamps, temperatures)
        threshold_C = 172.0
        
        cum_hold, intervals = calculate_cumulative_hold_time(
            df["temp_C"], df["timestamp"], threshold_C, max_total_dips_s=120
        )
        
        # Should only count partial hold due to dip limit exceeded
        assert cum_hold < 240.0  # Less than total possible hold time
        assert len(intervals) <= 3  # Should stop early due to dip limit

    def test_marginal_dips_pass_cumulative(self):
        """Test that dips just within limit pass cumulative mode."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ]
        # Pattern: above (60s), below (30s), above (60s), below (30s), above (60s), above (60s)
        # Total dip time: 60s, max allowed: 120s
        temperatures = [173.0, 169.0, 173.0, 169.0, 173.0, 173.0]
        
        df = create_test_series(timestamps, temperatures)
        threshold_C = 172.0
        
        cum_hold, intervals = calculate_cumulative_hold_time(
            df["temp_C"], df["timestamp"], threshold_C, max_total_dips_s=120
        )
        
        # Should count all above-threshold time: 4 * 60s = 240s
        expected_hold = 240.0
        assert abs(cum_hold - expected_hold) < 30.0
        assert len(intervals) == 3  # Three above-threshold intervals


class TestTimeToThreshold:
    """Test time-to-threshold calculations."""
    
    @pytest.mark.parametrize("temp_profile,expected_time_s", [
        # Quick ramp - reaches threshold at index 2 (120s)
        ([165.0, 168.0, 172.5, 173.0, 173.0], 120.0),
        # Slow ramp - reaches threshold at index 4 (240s)
        ([165.0, 167.0, 169.0, 171.0, 172.5], 240.0),
        # Never reaches threshold
        ([165.0, 167.0, 169.0, 171.0, 171.5], None),
    ])
    def test_time_to_threshold_scenarios(
        self, temp_profile: List[float], expected_time_s: float
    ):
        """Test time-to-threshold calculation for different temperature profiles."""
        timestamps = [f"2024-01-01T10:0{i}:00Z" for i in range(len(temp_profile))]
        df = create_test_series(timestamps, temp_profile)
        threshold_C = 172.0
        
        time_to_threshold = find_threshold_crossing_time(
            df["temp_C"], df["timestamp"], threshold_C
        )
        
        if expected_time_s is None:
            assert time_to_threshold is None
        else:
            assert abs(time_to_threshold - expected_time_s) < 30.0

    def test_precondition_time_to_threshold_pass(self):
        """Test that acceptable time-to-threshold passes precondition check."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ]
        temperatures = [168.0, 170.0, 172.5, 173.0, 173.0, 173.0]  # Reaches threshold at 120s
        
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec(
            target_temp_C=170.0,
            hold_time_s=180,  # Require 3 minutes hold
            max_time_to_threshold=300  # Allow up to 5 minutes to reach threshold
        )
        
        result = make_decision(df, spec)
        
        assert result.pass_ is True
        # Should not have time-to-threshold failure reason
        time_failures = [r for r in result.reasons if "Time to threshold too long" in r]
        assert len(time_failures) == 0

    def test_precondition_time_to_threshold_fail(self):
        """Test that excessive time-to-threshold fails precondition check."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:02:00Z", "2024-01-01T10:04:00Z",
            "2024-01-01T10:06:00Z", "2024-01-01T10:08:00Z", "2024-01-01T10:10:00Z"
        ]
        temperatures = [168.0, 169.0, 170.0, 171.0, 172.5, 173.0]  # Reaches threshold at 480s
        
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec(
            target_temp_C=170.0,
            hold_time_s=120,  # Require 2 minutes hold
            max_time_to_threshold=300  # Allow only 5 minutes to reach threshold
        )
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        # Should have time-to-threshold failure reason
        time_failures = [r for r in result.reasons if "Time to threshold too long" in r]
        assert len(time_failures) == 1


class TestRampRate:
    """Test ramp rate calculations and validation."""
    
    @pytest.mark.parametrize("temp_profile,expected_max_rate", [
        # Gentle ramp: ~2°C/min
        ([168.0, 169.0, 170.0, 171.0, 172.0], 2.0),
        # Aggressive ramp: ~6°C/min  
        ([168.0, 171.0, 174.0, 177.0, 175.0], 6.0),
        # Mixed ramp rates
        ([168.0, 170.0, 174.0, 174.5, 175.0], 8.0),  # 4°C in 30s = 8°C/min max
    ])
    def test_ramp_rate_calculation(self, temp_profile: List[float], expected_max_rate: float):
        """Test ramp rate calculation for different temperature profiles."""
        timestamps = [f"2024-01-01T10:0{i}:30Z" for i in range(len(temp_profile))]
        df = create_test_series(timestamps, temp_profile)
        
        ramp_rates = calculate_ramp_rate(df["temp_C"], df["timestamp"])
        max_rate = ramp_rates.max()
        
        # Allow some tolerance for calculation differences
        assert abs(max_rate - expected_max_rate) < 1.0, f"Expected ~{expected_max_rate}°C/min, got {max_rate}°C/min"

    def test_precondition_ramp_rate_pass(self):
        """Test that acceptable ramp rate passes precondition check."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ]
        temperatures = [168.0, 170.0, 172.0, 172.5, 173.0, 173.0]  # ~2°C/min max
        
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec(
            target_temp_C=170.0,
            hold_time_s=180,
            max_ramp_rate=5.0  # Allow up to 5°C/min
        )
        
        result = make_decision(df, spec)
        
        assert result.pass_ is True
        # Should not have ramp rate failure reason
        ramp_failures = [r for r in result.reasons if "Ramp rate too high" in r]
        assert len(ramp_failures) == 0

    def test_precondition_ramp_rate_fail(self):
        """Test that excessive ramp rate fails precondition check."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z", "2024-01-01T10:01:00Z",
            "2024-01-01T10:01:30Z", "2024-01-01T10:02:00Z", "2024-01-01T10:02:30Z"
        ]
        temperatures = [168.0, 172.0, 176.0, 177.0, 177.0, 177.0]  # 8°C/min max (4°C in 30s)
        
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec(
            target_temp_C=170.0,
            hold_time_s=60,
            max_ramp_rate=5.0  # Allow only up to 5°C/min
        )
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        # Should have ramp rate failure reason
        ramp_failures = [r for r in result.reasons if "Ramp rate too high" in r]
        assert len(ramp_failures) == 1


class TestSensorCombination:
    """Test sensor combination modes and edge cases."""
    
    def test_min_of_set_basic(self):
        """Test MIN_OF_SET sensor combination mode."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"]),
            "sensor1": [172.0, 173.0],
            "sensor2": [174.0, 171.0],
            "sensor3": [173.0, 175.0]
        })
        
        combined = combine_sensor_readings(
            df, ["sensor1", "sensor2", "sensor3"], SensorMode.MIN_OF_SET
        )
        
        expected = pd.Series([172.0, 171.0])  # Min of each row
        pd.testing.assert_series_equal(combined, expected, check_names=False)

    def test_mean_of_set_basic(self):
        """Test MEAN_OF_SET sensor combination mode."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"]),
            "sensor1": [170.0, 172.0],
            "sensor2": [174.0, 176.0],
            "sensor3": [176.0, 174.0]
        })
        
        combined = combine_sensor_readings(
            df, ["sensor1", "sensor2", "sensor3"], SensorMode.MEAN_OF_SET
        )
        
        expected = pd.Series([173.33333333333334, 174.0])  # Mean of each row
        pd.testing.assert_series_equal(combined, expected, check_names=False, atol=0.01)

    def test_majority_over_threshold_basic(self):
        """Test MAJORITY_OVER_THRESHOLD sensor combination mode."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z"]),
            "sensor1": [171.0, 173.0, 169.0],
            "sensor2": [173.0, 171.0, 173.0],
            "sensor3": [169.0, 175.0, 171.0]
        })
        threshold_C = 172.0
        
        combined = combine_sensor_readings(
            df, ["sensor1", "sensor2", "sensor3"], SensorMode.MAJORITY_OVER_THRESHOLD,
            threshold_C=threshold_C
        )
        
        # Row 0: 1/3 sensors above 172°C -> False
        # Row 1: 2/3 sensors above 172°C -> True  
        # Row 2: 1/3 sensors above 172°C -> False
        expected = pd.Series([False, True, False])
        pd.testing.assert_series_equal(combined, expected, check_names=False)

    def test_sensor_combination_insufficient_sensors(self):
        """Test sensor combination with insufficient sensors."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"]),
            "sensor1": [172.0, np.nan],  # sensor1 fails at second reading
            "sensor2": [np.nan, 173.0]   # sensor2 fails at first reading
        })
        
        with pytest.raises(DecisionError, match="Insufficient valid sensors"):
            combine_sensor_readings(
                df, ["sensor1", "sensor2"], SensorMode.MIN_OF_SET, require_at_least=2
            )


class TestBooleanHoldTime:
    """Test boolean hold time calculations for majority_over_threshold mode."""
    
    def test_boolean_continuous_hold(self):
        """Test continuous boolean hold time calculation."""
        timestamps = pd.to_datetime([
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ])
        boolean_series = pd.Series([True, True, False, True, True, True])
        
        hold_time = calculate_boolean_hold_time(
            boolean_series, timestamps, continuous=True
        )
        
        # Longest continuous True period: indices 3-5 = 120 seconds
        expected = 120.0
        assert abs(hold_time - expected) < 30.0

    def test_boolean_cumulative_hold(self):
        """Test cumulative boolean hold time calculation."""
        timestamps = pd.to_datetime([
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ])
        boolean_series = pd.Series([True, True, False, True, True, True])
        
        hold_time = calculate_boolean_hold_time(
            boolean_series, timestamps, continuous=False, max_dips_s=120
        )
        
        # Total True time: 2*60 + 3*60 = 300 seconds, False time: 60s (within limit)
        expected = 240.0  # 4 True intervals * 60s each
        assert abs(hold_time - expected) < 30.0

    def test_boolean_cumulative_exceeds_dip_limit(self):
        """Test cumulative boolean with excessive False time."""
        timestamps = pd.to_datetime([
            "2024-01-01T10:00:00Z", "2024-01-01T10:02:00Z", "2024-01-01T10:04:00Z",
            "2024-01-01T10:06:00Z", "2024-01-01T10:08:00Z", "2024-01-01T10:10:00Z"
        ])
        boolean_series = pd.Series([True, False, False, False, True, True])
        
        hold_time = calculate_boolean_hold_time(
            boolean_series, timestamps, continuous=False, max_dips_s=120  # Allow only 2 minutes False
        )
        
        # False time: 6 minutes (360s) > limit of 120s -> should return 0
        assert hold_time == 0.0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_dataframe(self):
        """Test decision with empty DataFrame."""
        df = pd.DataFrame()
        spec = create_basic_spec()
        
        with pytest.raises(DecisionError, match="DataFrame is empty"):
            make_decision(df, spec)

    def test_insufficient_data_points(self):
        """Test decision with insufficient data points."""
        df = create_test_series(["2024-01-01T10:00:00Z"], [172.0])
        spec = create_basic_spec()
        
        with pytest.raises(DecisionError, match="Insufficient data points"):
            make_decision(df, spec)

    def test_all_nan_temperatures(self):
        """Test decision with all NaN temperature values."""
        timestamps = ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z"]
        temperatures = [np.nan, np.nan, np.nan]
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec()
        
        with pytest.raises(DecisionError, match="All temperature sensors have failed"):
            make_decision(df, spec)

    def test_no_timestamp_column(self):
        """Test decision with no recognizable timestamp column."""
        df = pd.DataFrame({
            "temp_C": [172.0, 173.0, 172.5],
            "other_data": [1, 2, 3]
        })
        spec = create_basic_spec()
        
        with pytest.raises(DecisionError, match="No timestamp column found"):
            make_decision(df, spec)

    def test_temperature_never_reaches_threshold(self):
        """Test decision when temperature never reaches conservative threshold."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z", "2024-01-01T10:05:00Z"
        ]
        temperatures = [168.0, 169.0, 170.0, 171.0, 171.5, 171.8]  # Never reaches 172°C
        
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec(target_temp_C=170.0, sensor_uncertainty_C=2.0)  # Threshold: 172°C
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert result.actual_hold_time_s == 0.0
        threshold_failures = [r for r in result.reasons if "never reached conservative threshold" in r]
        assert len(threshold_failures) == 1

    def test_insufficient_hold_time_continuous(self):
        """Test decision with insufficient continuous hold time."""
        timestamps = [
            "2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z",
            "2024-01-01T10:03:00Z", "2024-01-01T10:04:00Z"
        ]
        temperatures = [172.5, 173.0, 173.0, 173.0, 172.8]  # Only 240s hold
        
        df = create_test_series(timestamps, temperatures)
        spec = create_basic_spec(target_temp_C=170.0, hold_time_s=300)  # Require 300s
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert result.actual_hold_time_s < 300.0
        hold_failures = [r for r in result.reasons if "Insufficient continuous hold time" in r]
        assert len(hold_failures) == 1


class TestDetectTemperatureColumns:
    """Test temperature column detection logic."""
    
    @pytest.mark.parametrize("columns,expected", [
        # Standard temperature columns
        (["timestamp", "temp_C", "data"], ["temp_C"]),
        # Multiple temperature columns
        (["timestamp", "sensor1_temp", "sensor2_temperature", "other"], ["sensor1_temp", "sensor2_temperature"]),
        # PMT columns
        (["timestamp", "pmt1", "pmt2", "status"], ["pmt1", "pmt2"]),
        # No temperature columns
        (["timestamp", "pressure", "flow"], []),
        # Mixed patterns
        (["timestamp", "temp_degC", "sensor_F", "ambient_temperature"], ["temp_degC", "sensor_F", "ambient_temperature"]),
    ])
    def test_detect_temperature_columns_patterns(self, columns: List[str], expected: List[str]):
        """Test temperature column detection with various naming patterns."""
        # Create DataFrame with numeric columns for temperature candidates
        df_data = {}
        for col in columns:
            if col == "timestamp":
                df_data[col] = pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"])
            elif col in expected:
                df_data[col] = [172.0, 173.0]  # Numeric temperature data
            else:
                df_data[col] = ["text", "data"]  # Non-numeric data
        
        df = pd.DataFrame(df_data)
        detected = detect_temperature_columns(df)
        
        assert set(detected) == set(expected)

    def test_detect_temperature_columns_non_numeric_excluded(self):
        """Test that non-numeric temperature-named columns are excluded."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"]),
            "temp_C": [172.0, 173.0],  # Valid numeric temperature
            "temp_status": ["OK", "OK"],  # Text column with temp name - should be excluded
            "sensor_temp": ["high", "medium"]  # Text column with temp name - should be excluded
        })
        
        detected = detect_temperature_columns(df)
        
        assert detected == ["temp_C"]  # Only numeric temperature column


class TestValidatePreconditions:
    """Test precondition validation logic."""
    
    def test_validate_preconditions_pass(self):
        """Test precondition validation with valid data."""
        df = create_test_series(
            ["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z", "2024-01-01T10:02:00Z"],
            [172.0, 173.0, 173.5]
        )
        spec = create_basic_spec()
        
        valid, issues = validate_preconditions(df, spec)
        
        assert valid is True
        assert len(issues) == 0

    def test_validate_preconditions_empty_dataframe(self):
        """Test precondition validation with empty DataFrame."""
        df = pd.DataFrame()
        spec = create_basic_spec()
        
        valid, issues = validate_preconditions(df, spec)
        
        assert valid is False
        assert "DataFrame is empty" in issues

    def test_validate_preconditions_insufficient_data(self):
        """Test precondition validation with insufficient data points."""
        df = create_test_series(["2024-01-01T10:00:00Z"], [172.0])
        spec = create_basic_spec()
        
        valid, issues = validate_preconditions(df, spec)
        
        assert valid is False
        assert "Insufficient data points for analysis" in issues

    def test_validate_preconditions_no_temperature_columns(self):
        """Test precondition validation with no temperature columns."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"]),
            "pressure": [100, 101],
            "flow": [50, 52]
        })
        spec = create_basic_spec()
        
        valid, issues = validate_preconditions(df, spec)
        
        assert valid is False
        assert "No temperature columns found" in issues