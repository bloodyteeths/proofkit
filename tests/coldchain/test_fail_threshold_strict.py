"""
Test fail fixture: require ≥95% in-range [2,8]°C per day
If below 95% ⇒ FAIL (not INDET if samples are sufficient)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from core.metrics_coldchain import calculate_daily_compliance


def test_fail_threshold_strict_95_percent():
    """Test that fail fixture returns FAIL when compliance is below 95%."""
    
    # Load fail fixture data - most temperatures are outside [2,8]°C range
    # From audit/fixtures/coldchain/fail.csv: temperatures range from 2.0 to 25.3°C
    # Only first few samples are in [2,8]°C range, most are well above 8°C
    
    timestamps = [
        "2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z", "2024-01-01T10:01:00Z",
        "2024-01-01T10:01:30Z", "2024-01-01T10:02:00Z", "2024-01-01T10:02:30Z",
        "2024-01-01T10:03:00Z", "2024-01-01T10:03:30Z", "2024-01-01T10:04:00Z",
        "2024-01-01T10:04:30Z", "2024-01-01T10:05:00Z", "2024-01-01T10:05:30Z",
        "2024-01-01T10:06:00Z", "2024-01-01T10:06:30Z", "2024-01-01T10:07:00Z",
        "2024-01-01T10:07:30Z", "2024-01-01T10:08:00Z", "2024-01-01T10:08:30Z",
        "2024-01-01T10:09:00Z", "2024-01-01T10:09:30Z"
    ]
    
    # Temperature values from fail fixture (using sensor_1 column)
    temperatures = [
        2.1, 5.0, 8.2, 12.9, 15.3, 18.0, 20.1, 22.8, 24.4, 25.0,
        25.2, 24.9, 24.1, 23.3, 22.0, 20.8, 19.2, 17.4, 15.1, 12.9
    ]
    
    # Create time series
    time_series = pd.Series([pd.to_datetime(ts) for ts in timestamps])
    temp_series = pd.Series(temperatures)
    
    # Calculate daily compliance
    result = calculate_daily_compliance(
        temperature_series=temp_series,
        time_series=time_series,
        min_temp_c=2.0,
        max_temp_c=8.0,
        required_compliance=95.0
    )
    
    # Check that compliance is below 95%
    # Only first 3 samples (2.1, 5.0, 8.2) are in [2,8]°C range using closed="both"
    # But 8.2 is outside [2,8], so only 2 out of 20 samples = 10% compliance
    expected_in_range = 2  # Only 2.1 and 5.0 are in [2,8]°C range
    expected_compliance_pct = (expected_in_range / len(temperatures)) * 100  # 10%
    
    assert result['overall_compliance_pct'] < 95.0, f"Expected < 95%, got {result['overall_compliance_pct']}%"
    assert result['overall_compliance_pct'] == expected_compliance_pct, f"Expected {expected_compliance_pct}%, got {result['overall_compliance_pct']}%"
    assert not result['days_meeting_requirement'], "Should not meet requirement with < 95% compliance"


def test_minimum_samples_threshold():
    """Test that with sufficient samples (≥96/24h), strict PASS/FAIL logic applies."""
    
    # Create 96 samples (minimum for 24h monitoring at 15-min intervals)
    timestamps = []
    base_time = pd.to_datetime("2024-01-01T00:00:00Z")
    
    for i in range(96):
        timestamps.append(base_time + timedelta(minutes=15*i))
    
    # 94 samples in range [2,8]°C, 2 samples outside = 97.9% compliance (above 95%)
    temperatures = [5.0] * 94 + [1.0, 9.0]  # 94 in range, 2 out of range
    
    time_series = pd.Series(timestamps)
    temp_series = pd.Series(temperatures)
    
    result = calculate_daily_compliance(
        temperature_series=temp_series,
        time_series=time_series,
        min_temp_c=2.0,
        max_temp_c=8.0,
        required_compliance=95.0
    )
    
    # Should PASS with 97.9% compliance
    expected_compliance = (94 / 96) * 100  # 97.916...%
    assert result['overall_compliance_pct'] >= 95.0, f"Expected ≥ 95%, got {result['overall_compliance_pct']}%"
    assert abs(result['overall_compliance_pct'] - expected_compliance) < 0.1, f"Expected ~{expected_compliance}%, got {result['overall_compliance_pct']}%"
    assert result['days_meeting_requirement'], "Should meet requirement with > 95% compliance"


def test_insufficient_samples_below_minimum():
    """Test behavior with insufficient samples (< 96/24h)."""
    
    # Create only 50 samples (insufficient for reliable 24h monitoring)
    timestamps = []
    base_time = pd.to_datetime("2024-01-01T00:00:00Z")
    
    for i in range(50):
        timestamps.append(base_time + timedelta(minutes=15*i))
    
    # All samples in range - should still show 100% compliance in the result
    temperatures = [5.0] * 50  # All in [2,8]°C range
    
    time_series = pd.Series(timestamps)
    temp_series = pd.Series(temperatures)
    
    result = calculate_daily_compliance(
        temperature_series=temp_series,
        time_series=time_series,
        min_temp_c=2.0,
        max_temp_c=8.0,
        required_compliance=95.0
    )
    
    # Should show 100% compliance even with insufficient samples
    assert result['overall_compliance_pct'] == 100.0, f"Expected 100%, got {result['overall_compliance_pct']}%"
    assert result['days_meeting_requirement'], "Should meet requirement with 100% compliance"


def test_closed_range_both_boundaries():
    """Test that [2,8]°C range uses closed="both" (inclusive of both 2.0 and 8.0)."""
    
    # Test boundary values
    timestamps = [
        pd.to_datetime("2024-01-01T10:00:00Z"),
        pd.to_datetime("2024-01-01T10:01:00Z"),
        pd.to_datetime("2024-01-01T10:02:00Z"),
        pd.to_datetime("2024-01-01T10:03:00Z")
    ]
    
    # Boundary test: 2.0 and 8.0 should be in range, 1.9 and 8.1 should be out of range
    temperatures = [1.9, 2.0, 8.0, 8.1]  # 2 in range, 2 out of range = 50%
    
    time_series = pd.Series(timestamps)
    temp_series = pd.Series(temperatures)
    
    result = calculate_daily_compliance(
        temperature_series=temp_series,
        time_series=time_series,
        min_temp_c=2.0,
        max_temp_c=8.0,
        required_compliance=95.0
    )
    
    # Should be exactly 50% compliance (2 out of 4 samples in range)
    assert result['overall_compliance_pct'] == 50.0, f"Expected 50%, got {result['overall_compliance_pct']}%"
    assert not result['days_meeting_requirement'], "Should not meet requirement with 50% compliance"


def test_actual_fail_fixture_data():
    """Test the actual fail fixture data from audit/fixtures/coldchain/fail.csv."""
    
    # Replicate the fail fixture data exactly
    fail_data = {
        'timestamp': [
            '2024-01-01T10:00:00Z', '2024-01-01T10:00:30Z', '2024-01-01T10:01:00Z',
            '2024-01-01T10:01:30Z', '2024-01-01T10:02:00Z', '2024-01-01T10:02:30Z',
            '2024-01-01T10:03:00Z', '2024-01-01T10:03:30Z', '2024-01-01T10:04:00Z',
            '2024-01-01T10:04:30Z', '2024-01-01T10:05:00Z', '2024-01-01T10:05:30Z',
            '2024-01-01T10:06:00Z', '2024-01-01T10:06:30Z', '2024-01-01T10:07:00Z',
            '2024-01-01T10:07:30Z', '2024-01-01T10:08:00Z', '2024-01-01T10:08:30Z',
            '2024-01-01T10:09:00Z', '2024-01-01T10:09:30Z'
        ],
        'sensor_1': [
            2.1, 5.0, 8.2, 12.9, 15.3, 18.0, 20.1, 22.8, 24.4, 25.0,
            25.2, 24.9, 24.1, 23.3, 22.0, 20.8, 19.2, 17.4, 15.1, 12.9
        ],
        'sensor_2': [
            2.0, 4.9, 8.1, 12.8, 15.2, 17.9, 20.0, 22.7, 24.3, 24.9,
            25.1, 24.8, 24.0, 23.2, 21.9, 20.7, 19.1, 17.3, 15.0, 12.8
        ],
        'sensor_3': [
            2.2, 5.1, 8.3, 13.0, 15.4, 18.1, 20.2, 22.9, 24.5, 25.1,
            25.3, 25.0, 24.2, 23.4, 22.1, 20.9, 19.3, 17.5, 15.2, 13.0
        ]
    }
    
    df = pd.DataFrame(fail_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Use sensor_1 for analysis
    time_series = df['timestamp']
    temp_series = df['sensor_1']
    
    result = calculate_daily_compliance(
        temperature_series=temp_series,
        time_series=time_series,
        min_temp_c=2.0,
        max_temp_c=8.0,
        required_compliance=95.0
    )
    
    # Count samples in [2,8]°C range
    in_range = (temp_series >= 2.0) & (temp_series <= 8.0)
    expected_in_range_count = in_range.sum()
    expected_compliance_pct = (expected_in_range_count / len(temp_series)) * 100
    
    # Only 2.1 and 5.0 are in [2,8]°C range, so 2/20 = 10%
    assert expected_compliance_pct == 10.0, f"Expected 10% compliance, calculated {expected_compliance_pct}%"
    assert result['overall_compliance_pct'] < 95.0, f"Expected < 95%, got {result['overall_compliance_pct']}%"
    assert not result['days_meeting_requirement'], "Should FAIL with < 95% compliance"