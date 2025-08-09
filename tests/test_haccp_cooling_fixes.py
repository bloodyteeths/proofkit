"""
Test HACCP cooling validation fixes.

Tests for:
1. Linear interpolation for temperature crossings at 135→70°F (≤2h) and 135→41°F (≤6h)
2. RequiredSignalMissingError when temperature column missing
3. Return FAIL when cooling rules not met (not PASS)
"""

import pandas as pd
from datetime import datetime, timezone, timedelta
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.metrics_haccp import validate_haccp_cooling, RequiredSignalMissingError, find_temperature_time
from core.models import SpecV1


def create_haccp_spec():
    """Create a standard HACCP specification for testing."""
    return SpecV1(**{
        "version": "1.0",
        "industry": "haccp",
        "job": {"job_id": "test_haccp_001"},
        "spec": {
            "method": "OVEN_AIR",
            "target_temp_C": 5.0,  # 41°F target
            "hold_time_s": 3600,   # 1 hour hold
            "sensor_uncertainty_C": 1.0
        },
        "data_requirements": {
            "max_sample_period_s": 60.0,
            "allowed_gaps_s": 120.0
        },
        "sensor_selection": {
            "mode": "mean_of_set",
            "require_at_least": 1
        }
    })


def test_linear_interpolation_exact_crossing():
    """Test that linear interpolation finds exact temperature crossing times."""
    # Create test data with known crossing points
    timestamps = [
        datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),  # Start at 57.2°C (135°F)
        datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc),  # 30 min: 25°C (between 135°F and 70°F)
        datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc),   # 60 min: 18°C (below 70°F = 21.1°C)
        datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc),   # 120 min: 3°C (below 41°F = 5.0°C)
    ]
    
    temperatures = pd.Series([57.2, 25.0, 18.0, 3.0])  # Values crossing both thresholds
    time_series = pd.Series(timestamps)
    
    # Test 70°F crossing (21.1°C) - should interpolate between 25°C and 18°C at 30-60 min
    time_to_70f = find_temperature_time(temperatures, time_series, 21.1, 'cooling')
    assert time_to_70f is not None
    assert 1800 < time_to_70f < 3600  # Between 30 and 60 minutes
    
    # Test 41°F crossing (5.0°C) - should interpolate between 18°C and 3°C at 60-120 min  
    time_to_41f = find_temperature_time(temperatures, time_series, 5.0, 'cooling')
    assert time_to_41f is not None
    assert 3600 < time_to_41f < 7200  # Between 60 and 120 minutes


def test_missing_temperature_columns_raises_error():
    """Test that missing temperature columns raises RequiredSignalMissingError."""
    spec = create_haccp_spec()
    
    # Create DataFrame with no temperature columns (only timestamp)
    df_no_temp = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-15 12:00:00', periods=10, freq='15min', tz='UTC'),
        'humidity': [50, 51, 52, 53, 54, 55, 56, 57, 58, 59],  # Not temperature
        'pressure': [1013, 1013, 1013, 1013, 1013, 1013, 1013, 1013, 1013, 1013]  # Not temperature
    })
    
    try:
        validate_haccp_cooling(df_no_temp, spec)
        assert False, "Expected RequiredSignalMissingError but none was raised"
    except RequiredSignalMissingError as e:
        assert "No temperature columns found" in str(e)


def test_cooling_failure_returns_fail():
    """Test that cooling rule violations return FAIL (not PASS)."""
    spec = create_haccp_spec()
    
    # Create failing cooling data - takes too long to reach 70°F (over 2 hours)
    timestamps = pd.date_range('2024-01-15 12:00:00', periods=20, freq='30min', tz='UTC')
    
    # Slow cooling: 135°F to 70°F takes 4.5 hours (should be ≤2h)
    temperatures = np.linspace(57.2, 5.0, 20)  # Linear cooling over 9.5 hours total
    temperatures[0] = 57.2  # Start at 135°F (57.2°C)
    temperatures[9] = 21.1  # Reach 70°F (21.1°C) at 4.5 hours - TOO SLOW
    temperatures[-1] = 5.0  # End at 41°F (5.0°C)
    
    df_fail = pd.DataFrame({
        'timestamp': timestamps,
        'temp_sensor': temperatures
    })
    
    result = validate_haccp_cooling(df_fail, spec)
    
    # Must return FAIL for cooling violation
    assert result.pass_ is False
    assert any("Phase 1 cooling took" in reason and "> 2h limit" in reason for reason in result.reasons)


def test_successful_cooling_returns_pass():
    """Test that successful cooling within time limits returns PASS."""
    spec = create_haccp_spec()
    
    # Create passing cooling data - meets both phase requirements
    timestamps = pd.date_range('2024-01-15 12:00:00', periods=25, freq='15min', tz='UTC')
    
    # Fast cooling: 135°F to 70°F in 1.5h, 135°F to 41°F in 4h
    temperatures = []
    for i in range(25):
        if i <= 6:  # First 1.5 hours: 135°F to 70°F
            temp = 57.2 - (57.2 - 21.1) * (i / 6)
        elif i <= 16:  # Next 2.5 hours: 70°F to 41°F  
            temp = 21.1 - (21.1 - 5.0) * ((i - 6) / 10)
        else:  # Hold at 41°F
            temp = 5.0
        temperatures.append(temp)
    
    df_pass = pd.DataFrame({
        'timestamp': timestamps,
        'temp_sensor': temperatures
    })
    
    result = validate_haccp_cooling(df_pass, spec)
    
    # Must return PASS for successful cooling
    assert result.pass_ is True
    assert any("Phase 1 cooling" in reason and "≤ 2h" in reason for reason in result.reasons)
    assert any("Phase 2 cooling" in reason and "≤ 6h" in reason for reason in result.reasons)


def test_phase_timing_with_interpolation():
    """Test that phase timing calculations use interpolated crossing times."""
    spec = create_haccp_spec()
    
    # Test with actual test data files
    test_data_dir = os.path.join(os.path.dirname(__file__), 'data')
    
    # Test failing case
    df_fail = pd.read_csv(os.path.join(test_data_dir, 'haccp_cooling_fail.csv'))
    df_fail['timestamp'] = pd.to_datetime(df_fail['timestamp'])
    
    result_fail = validate_haccp_cooling(df_fail, spec)
    assert result_fail.pass_ is False
    
    # Test "pass" data - actually fails Phase 1 (takes 2.5h to reach 70°F, limit is 2h)
    df_pass = pd.read_csv(os.path.join(test_data_dir, 'haccp_cooling_pass.csv'))  
    df_pass['timestamp'] = pd.to_datetime(df_pass['timestamp'])
    
    result_pass = validate_haccp_cooling(df_pass, spec)
    # The "pass" test data actually violates Phase 1 timing (2.5h > 2h limit)
    assert result_pass.pass_ is False  # Correctly fails Phase 1 requirement


def test_invalid_industry_spec():
    """Test that invalid industry specs raise DecisionError.""" 
    from core.temperature_utils import DecisionError
    
    spec_data = {
        "version": "1.0",
        "industry": "invalid_industry",  # Wrong industry
        "job": {"job_id": "test_invalid"},
        "spec": {
            "method": "OVEN_AIR",
            "target_temp_C": 5.0,
            "hold_time_s": 3600,
            "sensor_uncertainty_C": 1.0
        }
    }
    spec = SpecV1(**spec_data)
    
    df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-15 12:00:00', periods=5, freq='15min', tz='UTC'),
        'temp_sensor': [57.2, 50.0, 40.0, 30.0, 5.0]
    })
    
    try:
        validate_haccp_cooling(df, spec)
        assert False, "Expected DecisionError but none was raised"
    except DecisionError as e:
        assert "Invalid industry" in str(e)


def test_insufficient_data_points():
    """Test that insufficient data points raise DecisionError."""
    from core.temperature_utils import DecisionError
    
    spec = create_haccp_spec()
    
    # Create DataFrame with only 1 data point
    df_insufficient = pd.DataFrame({
        'timestamp': [datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)],
        'temp_sensor': [57.2]
    })
    
    try:
        validate_haccp_cooling(df_insufficient, spec)
        assert False, "Expected DecisionError but none was raised"
    except DecisionError as e:
        assert "Insufficient data points" in str(e)


if __name__ == "__main__":
    # Run core tests
    test_linear_interpolation_exact_crossing()
    print("✓ Linear interpolation test passed")
    
    test_missing_temperature_columns_raises_error()
    print("✓ Missing temperature columns test passed")
    
    test_cooling_failure_returns_fail()
    print("✓ Cooling failure returns FAIL test passed")
    
    test_successful_cooling_returns_pass()
    print("✓ Successful cooling returns PASS test passed")
    
    test_phase_timing_with_interpolation()
    print("✓ Phase timing with interpolation test passed")
    
    test_insufficient_data_points()
    print("✓ Insufficient data points test passed")
    
    print("All HACCP cooling validation fix tests passed!")