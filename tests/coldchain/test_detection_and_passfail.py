"""Tests for cold chain temperature column detection and pass/fail logic."""

import pytest
import pandas as pd
from core.metrics_coldchain import analyze_coldchain, RequiredSignalMissingError


def test_temperature_column_detection():
    """Test various temperature column names are detected correctly."""
    
    # Test sensor_1
    df1 = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'sensor_1': [5.0, 6.0]
    })
    result1 = analyze_coldchain(df1, target_min=2.0, target_max=8.0)
    assert result1['temp_column'] == 'sensor_1'
    
    # Test CH1 Temp (°C)
    df2 = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'CH1 Temp (°C)': [4.0, 7.0]
    })
    result2 = analyze_coldchain(df2, target_min=2.0, target_max=8.0)
    assert result2['temp_column'] == 'CH1 Temp (°C)'
    
    # Test Value
    df3 = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'Value': [3.0, 5.0]
    })
    result3 = analyze_coldchain(df3, target_min=2.0, target_max=8.0)
    assert result3['temp_column'] == 'Value'


def test_multiple_candidates_preference():
    """Test that temp/temperature/°C are preferred over other matches."""
    
    # Multiple candidates, should prefer 'temperature'
    df = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'sensor_1': [5.0, 6.0],
        'temperature': [4.0, 7.0],
        'probe1': [3.0, 8.0]
    })
    result = analyze_coldchain(df, target_min=2.0, target_max=8.0)
    assert result['temp_column'] == 'temperature'


def test_no_temperature_columns_raises_error():
    """Test that missing temperature columns raises RequiredSignalMissingError."""
    
    df = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'pressure': [100.0, 101.0],
        'humidity': [50.0, 55.0]
    })
    
    with pytest.raises(RequiredSignalMissingError):
        analyze_coldchain(df, target_min=2.0, target_max=8.0)


def test_pass_fixture():
    """Test that temperatures within range result in PASS."""
    
    # All temperatures within [2, 8]°C range
    df = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00', '2024-01-01 02:00:00'],
        'temperature': [3.0, 5.0, 7.0]
    })
    result = analyze_coldchain(df, target_min=2.0, target_max=8.0)
    assert result['status'] == 'PASS'


def test_fail_fixture():
    """Test that temperatures outside range result in FAIL."""
    
    # Some temperatures outside [2, 8]°C range
    df = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00', '2024-01-01 02:00:00'],
        'temperature': [1.0, 5.0, 9.0]  # 1.0 and 9.0 are outside range
    })
    result = analyze_coldchain(df, target_min=2.0, target_max=8.0)
    assert result['status'] == 'FAIL'


def test_no_numeric_columns_raises_error():
    """Test that DataFrames with no numeric columns raise RequiredSignalMissingError."""
    
    df = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'notes': ['good', 'okay'],
        'location': ['A', 'B']
    })
    
    with pytest.raises(RequiredSignalMissingError):
        analyze_coldchain(df, target_min=2.0, target_max=8.0)


def test_edge_case_temperatures():
    """Test edge cases at exact boundaries."""
    
    # Exactly at boundaries should PASS
    df = pd.DataFrame({
        'timestamp': ['2024-01-01 00:00:00', '2024-01-01 01:00:00'],
        'temp': [2.0, 8.0]  # Exactly at min and max
    })
    result = analyze_coldchain(df, target_min=2.0, target_max=8.0)
    assert result['status'] == 'PASS'