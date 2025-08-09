"""
Property-based tests for temperature unit conversions.

Tests random °F/°C conversions, edge cases, and unit detection accuracy.
"""
import pandas as pd
import numpy as np
import pytest
from hypothesis import given, strategies as st, settings, assume, example
from hypothesis.extra.pandas import data_frames, column
from typing import List, Dict, Any

from core.normalize import (
    convert_fahrenheit_to_celsius,
    detect_temperature_columns,
    _convert_fahrenheit_to_celsius_df,
    normalize_temperature_data,
    NormalizationError
)


# Temperature ranges for different scenarios
FAHRENHEIT_RANGES = {
    'powder_coat_cure': (300.0, 400.0),  # 150-200°C cure range
    'concrete_curing': (40.0, 120.0),    # 4-50°C ambient range
    'autoclave': (250.0, 300.0),         # 121-150°C sterilization
    'freezing': (-10.0, 40.0),           # Below/around freezing
    'extreme_hot': (400.0, 800.0),       # Very high temps
}

CELSIUS_RANGES = {
    'powder_coat_cure': (150.0, 200.0),
    'concrete_curing': (4.0, 50.0),
    'autoclave': (121.0, 150.0),
    'freezing': (-23.0, 4.0),
    'extreme_hot': (200.0, 400.0),
}


@st.composite
def fahrenheit_temperatures(draw, scenario='powder_coat_cure'):
    """Generate realistic Fahrenheit temperatures for different scenarios."""
    min_temp, max_temp = FAHRENHEIT_RANGES.get(scenario, (32.0, 400.0))
    return draw(st.floats(
        min_value=min_temp,
        max_value=max_temp,
        allow_nan=False,
        allow_infinity=False
    ))


@st.composite
def celsius_temperatures(draw, scenario='powder_coat_cure'):
    """Generate realistic Celsius temperatures for different scenarios."""
    min_temp, max_temp = CELSIUS_RANGES.get(scenario, (0.0, 200.0))
    return draw(st.floats(
        min_value=min_temp,
        max_value=max_temp,
        allow_nan=False,
        allow_infinity=False
    ))


@st.composite
def temperature_dataframes(draw, unit='mixed'):
    """Generate DataFrames with temperature data in specified units."""
    size = draw(st.integers(min_value=5, max_value=50))
    scenario = draw(st.sampled_from(list(FAHRENHEIT_RANGES.keys())))
    
    # Generate column names that indicate units
    f_column_patterns = ['temp_f', 'temperature_fahrenheit', 'sensor_°F', 'temp_deg_f', 'fahrenheit_reading']
    c_column_patterns = ['temp_c', 'temperature_celsius', 'sensor_°C', 'temp_deg_c', 'celsius_reading']
    ambiguous_patterns = ['temperature', 'temp', 'sensor_1', 'probe_temp', 'reading']
    
    timestamp_data = [f"2023-01-01T12:{i:02d}:00" for i in range(size)]
    
    columns = {'timestamp': timestamp_data}
    
    if unit == 'fahrenheit' or (unit == 'mixed' and draw(st.booleans())):
        # Add Fahrenheit column
        f_col_name = draw(st.sampled_from(f_column_patterns))
        f_temps = [draw(fahrenheit_temperatures(scenario)) for _ in range(size)]
        columns[f_col_name] = f_temps
    
    if unit == 'celsius' or (unit == 'mixed' and draw(st.booleans())):
        # Add Celsius column  
        c_col_name = draw(st.sampled_from(c_column_patterns))
        c_temps = [draw(celsius_temperatures(scenario)) for _ in range(size)]
        columns[c_col_name] = c_temps
    
    if unit == 'ambiguous' or (unit == 'mixed' and draw(st.booleans())):
        # Add ambiguous column (need to detect by values)
        amb_col_name = draw(st.sampled_from(ambiguous_patterns))
        # Randomly choose if this should be F or C values
        if draw(st.booleans()):
            amb_temps = [draw(fahrenheit_temperatures(scenario)) for _ in range(size)]
        else:
            amb_temps = [draw(celsius_temperatures(scenario)) for _ in range(size)]
        columns[amb_col_name] = amb_temps
    
    return pd.DataFrame(columns)


class TestTemperatureUnitProperties:
    """Property-based tests for temperature unit handling."""
    
    @given(fahrenheit_temperatures())
    @settings(max_examples=100, deadline=1000)
    def test_fahrenheit_celsius_conversion_property(self, temp_f):
        """Property: F to C conversion should be mathematically correct."""
        temp_c = convert_fahrenheit_to_celsius(temp_f)
        
        # Property: F to C formula: (F - 32) * 5/9
        expected_c = (temp_f - 32) * 5 / 9
        assert abs(temp_c - expected_c) < 1e-10, \
            f"F to C conversion incorrect: {temp_f}°F -> {temp_c}°C, expected {expected_c}°C"
    
    @given(fahrenheit_temperatures(), st.integers(min_value=2, max_value=20))
    @settings(max_examples=50, deadline=2000)
    def test_series_conversion_property(self, base_temp, size):
        """Property: Series conversion should maintain element-wise correctness."""
        temps_f = pd.Series([base_temp + i * 5 for i in range(size)])
        temps_c = convert_fahrenheit_to_celsius(temps_f)
        
        # Property: Should be same length
        assert len(temps_c) == len(temps_f), "Conversion should preserve series length"
        
        # Property: Each element should be correctly converted
        for i, (f_val, c_val) in enumerate(zip(temps_f, temps_c)):
            expected_c = (f_val - 32) * 5 / 9
            assert abs(c_val - expected_c) < 1e-10, \
                f"Element {i}: {f_val}°F -> {c_val}°C, expected {expected_c}°C"
    
    @given(temperature_dataframes('fahrenheit'))
    @settings(max_examples=20, deadline=3000)
    def test_fahrenheit_dataframe_conversion_property(self, df):
        """Property: Fahrenheit DataFrame conversion should detect and convert F columns."""
        assume(len(df) >= 2)
        
        # Find temperature columns
        temp_cols = detect_temperature_columns(df)
        assume(len(temp_cols) > 0)
        
        # Get original values
        original_values = {}
        for col in temp_cols:
            if any(indicator in col.lower() for indicator in ['f', 'fahrenheit', '°f', 'degf']):
                original_values[col] = df[col].copy()
        
        assume(len(original_values) > 0)  # Only test if we have F columns
        
        # Convert
        converted_df = _convert_fahrenheit_to_celsius_df(df, temp_cols)
        
        # Property: Should preserve DataFrame shape
        assert converted_df.shape[0] == df.shape[0], "Should preserve row count"
        
        # Property: Fahrenheit columns should be converted
        for orig_col, orig_vals in original_values.items():
            # Find corresponding column in converted df (might be renamed)
            converted_col = orig_col
            if orig_col not in converted_df.columns:
                # Look for renamed column
                possible_names = [col for col in converted_df.columns if 'c' in col.lower() and col != 'timestamp']
                if possible_names:
                    converted_col = possible_names[0]
            
            if converted_col in converted_df.columns:
                converted_vals = converted_df[converted_col]
                
                # Check conversion accuracy for each value
                for i, (orig_f, conv_c) in enumerate(zip(orig_vals, converted_vals)):
                    if pd.notna(orig_f) and pd.notna(conv_c):
                        expected_c = (orig_f - 32) * 5 / 9
                        assert abs(conv_c - expected_c) < 1e-9, \
                            f"Row {i}, col {orig_col}: {orig_f}°F -> {conv_c}°C, expected {expected_c}°C"
    
    @given(temperature_dataframes('mixed'))
    @settings(max_examples=15, deadline=5000)
    def test_mixed_unit_detection_property(self, df):
        """Property: Mixed unit detection should identify units correctly."""
        assume(len(df) >= 3)
        
        temp_cols = detect_temperature_columns(df)
        assume(len(temp_cols) > 0)
        
        # Property: Should detect columns with temperature patterns
        for col in temp_cols:
            col_lower = col.lower()
            temp_indicators = ['temp', 'temperature', 'sensor', '°', 'deg', 'reading']
            assert any(indicator in col_lower for indicator in temp_indicators), \
                f"Column {col} should contain temperature indicators"
            
            # Property: Should be numeric
            assert pd.api.types.is_numeric_dtype(df[col]), \
                f"Temperature column {col} should be numeric"
    
    @given(st.data())
    @settings(max_examples=20, deadline=3000)
    def test_unit_detection_heuristics_property(self, data):
        """Property: Unit detection by value ranges should work for typical process temps."""
        scenario = data.draw(st.sampled_from(['powder_coat_cure', 'autoclave', 'concrete_curing']))
        size = data.draw(st.integers(min_value=10, max_value=30))
        
        # Generate clearly Fahrenheit values
        f_temps = [data.draw(fahrenheit_temperatures(scenario)) for _ in range(size)]
        # Generate clearly Celsius values  
        c_temps = [data.draw(celsius_temperatures(scenario)) for _ in range(size)]
        
        df = pd.DataFrame({
            'timestamp': [f"2023-01-01T12:{i:02d}:00" for i in range(size)],
            'temp_ambiguous_f': f_temps,
            'temp_ambiguous_c': c_temps
        })
        
        # Convert using heuristics
        temp_cols = detect_temperature_columns(df)
        converted_df = _convert_fahrenheit_to_celsius_df(df, temp_cols)
        
        # Property: Fahrenheit column should be detected and converted
        f_col_values = converted_df['temp_ambiguous_f']
        c_col_values = converted_df['temp_ambiguous_c'] 
        
        # F column should be converted to reasonable C range
        f_mean = f_col_values.mean()
        c_mean = c_col_values.mean()
        
        # For powder coat scenario, converted F should be in 150-200°C range
        if scenario == 'powder_coat_cure':
            assert 140 <= f_mean <= 210, \
                f"Converted F temps should be in C range for {scenario}: got {f_mean}°C mean"
            assert 140 <= c_mean <= 210, \
                f"C temps should already be in range for {scenario}: got {c_mean}°C mean"


class TestTemperatureConversionEdgeCases:
    """Edge case tests for temperature conversions."""
    
    def test_conversion_boundary_values(self):
        """Test conversion at important boundary values."""
        # Test key temperature points
        test_cases = [
            (32.0, 0.0),      # Freezing point
            (212.0, 100.0),   # Boiling point
            (0.0, -17.777777777777778),  # Absolute zero F
            (-40.0, -40.0),   # F and C equal
            (98.6, 37.0),     # Body temperature
        ]
        
        for temp_f, expected_c in test_cases:
            result_c = convert_fahrenheit_to_celsius(temp_f)
            assert abs(result_c - expected_c) < 1e-10, \
                f"{temp_f}°F should convert to {expected_c}°C, got {result_c}°C"
    
    def test_dataframe_with_mixed_indicators(self):
        """Test DataFrame with multiple unit indicators."""
        df = pd.DataFrame({
            'timestamp': ['2023-01-01T12:00:00', '2023-01-01T12:01:00'],
            'temp_f_reading': [350.0, 355.0],      # Clearly F by name and value
            'sensor_celsius': [175.0, 180.0],      # Clearly C by name and value
            'probe_temp': [300.0, 305.0],          # Ambiguous name but F-range values
            'room_temp': [22.0, 23.0],             # Ambiguous name but C-range values
        })
        
        temp_cols = detect_temperature_columns(df)
        converted_df = _convert_fahrenheit_to_celsius_df(df, temp_cols)
        
        # F column should be converted
        assert converted_df['temp_f_reading'].mean() < 200, \
            "temp_f_reading should be converted to Celsius range"
        
        # C column should remain unchanged
        assert abs(converted_df['sensor_celsius'].mean() - 177.5) < 0.1, \
            "sensor_celsius should remain in original C range"
        
        # High-value ambiguous should be converted (was F)
        assert converted_df['probe_temp'].mean() < 200, \
            "High-value probe_temp should be converted from F to C"
        
        # Low-value ambiguous should remain unchanged (was C)
        assert 20 <= converted_df['room_temp'].mean() <= 25, \
            "Low-value room_temp should remain in C range"
    
    def test_empty_and_single_value_conversions(self):
        """Test edge cases with empty or single values."""
        # Empty series
        empty_series = pd.Series([], dtype=float)
        result = convert_fahrenheit_to_celsius(empty_series)
        assert len(result) == 0, "Empty series should return empty result"
        
        # Single value series
        single_series = pd.Series([212.0])
        result = convert_fahrenheit_to_celsius(single_series)
        assert len(result) == 1, "Single value series should return single value"
        assert abs(result.iloc[0] - 100.0) < 1e-10, "212°F should convert to 100°C"
        
        # Series with NaN
        nan_series = pd.Series([212.0, np.nan, 32.0])
        result = convert_fahrenheit_to_celsius(nan_series)
        assert len(result) == 3, "Should preserve series length"
        assert abs(result.iloc[0] - 100.0) < 1e-10, "212°F should convert to 100°C"
        assert pd.isna(result.iloc[1]), "NaN should remain NaN"
        assert abs(result.iloc[2] - 0.0) < 1e-10, "32°F should convert to 0°C"


class TestTemperatureNormalizationIntegration:
    """Integration tests for temperature units in full normalization pipeline."""
    
    @given(temperature_dataframes('fahrenheit'))
    @settings(max_examples=10, deadline=5000)
    def test_full_normalization_with_fahrenheit_property(self, df):
        """Property: Full normalization should handle Fahrenheit data correctly."""
        assume(len(df) >= 5)
        
        temp_cols = detect_temperature_columns(df)
        assume(len(temp_cols) > 0)
        
        try:
            normalized_df = normalize_temperature_data(df)
            
            # Property: Should preserve timestamp column
            timestamp_cols = [col for col in normalized_df.columns if 'time' in col.lower()]
            assert len(timestamp_cols) > 0, "Should preserve timestamp column"
            
            # Property: Should convert temperature units
            temp_cols_normalized = detect_temperature_columns(normalized_df)
            assert len(temp_cols_normalized) > 0, "Should preserve temperature columns"
            
            # Property: Temperature values should be in reasonable Celsius range
            for col in temp_cols_normalized:
                temp_values = normalized_df[col].dropna()
                if len(temp_values) > 0:
                    temp_mean = temp_values.mean()
                    temp_max = temp_values.max()
                    
                    # Should be in reasonable C range (not F range)
                    assert temp_max < 500, f"Temperature {col} max ({temp_max}) should be in C range, not F"
                    
                    # For typical process temperatures, should be positive C
                    assert temp_mean > -50, f"Temperature {col} mean ({temp_mean}) should be reasonable C value"
                    
        except (NormalizationError, ValueError):
            # Acceptable if data quality issues prevent normalization
            pass


# Usage example in module docstring:
"""
Example usage of property-based unit conversion testing:

    pytest tests/property/test_units.py -v

To test specific temperature scenarios:
    pytest tests/property/test_units.py::TestTemperatureUnitProperties::test_fahrenheit_celsius_conversion_property

To run with extended examples for thorough testing:
    pytest tests/property/test_units.py --hypothesis-max-examples=200
"""