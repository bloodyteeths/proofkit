"""
Comprehensive test cases for metrics_coldchain module.

Tests focus on:
- Cold chain temperature compliance (2-8 degrees C)
- Daily compliance calculations
- Temperature excursions detection
- Fahrenheit to Celsius conversions
- Various compliance scenarios

Example usage:
    pytest tests/test_metrics_coldchain_cases.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch

from core.metrics_coldchain import (
    validate_coldchain_storage,
    calculate_daily_compliance,
    identify_temperature_excursions,
    fahrenheit_to_celsius,
    celsius_to_fahrenheit,
    DecisionResult
)


class TestColdChainValidation:
    """Test cold chain storage validation scenarios."""
    
    @pytest.mark.parametrize("temp_profile,expected_pass,expected_keywords", [
        # Pass cases
        ([5.0] * 100, True, ["maintained within range"]),  # Perfect temperature
        ([2.5, 7.5] * 50, True, ["maintained within range"]),  # Oscillating within range
        ([4.0, 5.0, 6.0] * 33, True, ["maintained within range"]),  # Gradual variation
        
        # Fail cases
        ([0.0] * 100, False, ["below acceptable range"]),  # Too cold
        ([10.0] * 100, False, ["above acceptable range"]),  # Too warm
        ([1.0, 9.0] * 50, False, ["Temperature excursions"]),  # Oscillating outside
        ([5.0] * 50 + [15.0] * 50, False, ["excursions detected"]),  # Half good, half bad
    ])
    def test_coldchain_temperature_scenarios(self, temp_profile, expected_pass, expected_keywords):
        """Test various cold chain temperature scenarios."""
        timestamps = pd.date_range('2024-01-01', periods=len(temp_profile), freq='1h')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temp_profile
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400,  # 24 hours
            'sensor_uncertainty_C': 0.5
        }
        
        result = validate_coldchain_storage(df, spec)
        
        assert result['pass'] == expected_pass
        for keyword in expected_keywords:
            assert any(keyword in reason for reason in result['reasons'])
    
    def test_coldchain_with_brief_excursions(self):
        """Test cold chain with brief temperature excursions."""
        # Create 48 hours of data
        hours = 48
        timestamps = pd.date_range('2024-01-01', periods=hours, freq='1h')
        
        # Mostly good temperatures with brief excursions
        temperatures = [5.0] * hours
        temperatures[10] = 12.0  # 1-hour excursion
        temperatures[20] = -1.0  # 1-hour excursion
        temperatures[30:32] = [15.0, 14.0]  # 2-hour excursion
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400,
            'sensor_uncertainty_C': 0.5
        }
        
        result = validate_coldchain_storage(df, spec)
        
        assert not result['pass']
        assert result['metrics']['excursion_count'] == 3
        assert result['metrics']['total_excursion_time_h'] == 4.0
    
    def test_coldchain_missing_temperature_column(self):
        """Test cold chain validation with missing temperature column."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=24, freq='1h'),
            'humidity': [50.0] * 24
        })
        
        spec = {'target_temp_C': 5.0, 'hold_time_s': 86400}
        
        result = validate_coldchain_storage(df, spec)
        
        assert not result['pass']
        assert any('temperature_C column' in r for r in result['reasons'])
    
    def test_coldchain_insufficient_data(self):
        """Test cold chain with insufficient monitoring duration."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=12, freq='1h'),
            'temperature_C': [5.0] * 12
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400  # Requires 24 hours
        }
        
        result = validate_coldchain_storage(df, spec)
        
        assert not result['pass']
        assert any('Insufficient monitoring' in r for r in result['reasons'])


class TestDailyCompliance:
    """Test daily compliance calculation."""
    
    def test_perfect_daily_compliance(self):
        """Test calculation with perfect compliance every day."""
        # 7 days of perfect temperatures
        days = 7
        hours_per_day = 24
        total_hours = days * hours_per_day
        
        timestamps = pd.date_range('2024-01-01', periods=total_hours, freq='1h')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': [5.0] * total_hours
        })
        
        daily_stats = calculate_daily_compliance(df)
        
        assert len(daily_stats) == days
        for day_stat in daily_stats:
            assert day_stat['compliant']
            assert day_stat['compliance_percent'] == 100.0
            assert day_stat['excursion_count'] == 0
    
    def test_mixed_daily_compliance(self):
        """Test calculation with mixed compliance days."""
        # Day 1: Perfect
        day1_temps = [5.0] * 24
        
        # Day 2: 50% compliance (12 hours out of range)
        day2_temps = [5.0] * 12 + [15.0] * 12
        
        # Day 3: 75% compliance (6 hours out of range)
        day3_temps = [5.0] * 18 + [10.0] * 6
        
        all_temps = day1_temps + day2_temps + day3_temps
        timestamps = pd.date_range('2024-01-01', periods=len(all_temps), freq='1h')
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': all_temps
        })
        
        daily_stats = calculate_daily_compliance(df)
        
        assert len(daily_stats) == 3
        assert daily_stats[0]['compliance_percent'] == 100.0
        assert daily_stats[1]['compliance_percent'] == 50.0
        assert daily_stats[2]['compliance_percent'] == 75.0
    
    def test_daily_compliance_with_data_gaps(self):
        """Test daily compliance with missing data points."""
        # Create data with gaps
        timestamps = []
        temperatures = []
        
        # Day 1: Full data
        day1_start = pd.Timestamp('2024-01-01')
        for hour in range(24):
            timestamps.append(day1_start + pd.Timedelta(hours=hour))
            temperatures.append(5.0)
        
        # Day 2: Only 12 hours of data (gap from hours 12-23)
        day2_start = pd.Timestamp('2024-01-02')
        for hour in range(12):
            timestamps.append(day2_start + pd.Timedelta(hours=hour))
            temperatures.append(5.0)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        daily_stats = calculate_daily_compliance(df)
        
        assert len(daily_stats) == 2
        assert daily_stats[0]['data_points'] == 24
        assert daily_stats[1]['data_points'] == 12


class TestTemperatureExcursions:
    """Test temperature excursion identification."""
    
    def test_no_excursions(self):
        """Test identification when no excursions exist."""
        timestamps = pd.date_range('2024-01-01', periods=48, freq='1h')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': [5.0] * 48
        })
        
        excursions = identify_temperature_excursions(df)
        
        assert len(excursions) == 0
    
    def test_single_excursion(self):
        """Test identification of single excursion."""
        temperatures = [5.0] * 48
        temperatures[10:15] = [12.0] * 5  # 5-hour excursion
        
        timestamps = pd.date_range('2024-01-01', periods=48, freq='1h')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        excursions = identify_temperature_excursions(df)
        
        assert len(excursions) == 1
        assert excursions[0]['duration_hours'] == 5.0
        assert excursions[0]['max_temp'] == 12.0
        assert excursions[0]['type'] == 'high'
    
    def test_multiple_excursions(self):
        """Test identification of multiple excursions."""
        temperatures = [5.0] * 72
        
        # High excursion
        temperatures[10:13] = [10.0, 11.0, 10.5]
        
        # Low excursion
        temperatures[30:32] = [0.0, -1.0]
        
        # Another high excursion
        temperatures[50:55] = [9.0] * 5
        
        timestamps = pd.date_range('2024-01-01', periods=72, freq='1h')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        excursions = identify_temperature_excursions(df)
        
        assert len(excursions) == 3
        
        # Check excursion types
        types = [e['type'] for e in excursions]
        assert 'high' in types
        assert 'low' in types
    
    def test_excursion_with_brief_returns(self):
        """Test excursion identification with brief returns to range."""
        temperatures = [5.0] * 48
        
        # Excursion with brief return to range
        temperatures[10:20] = [10.0, 11.0, 5.0, 12.0, 13.0, 14.0, 5.0, 15.0, 16.0, 10.0]
        
        timestamps = pd.date_range('2024-01-01', periods=48, freq='1h')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        excursions = identify_temperature_excursions(df, merge_threshold_hours=2)
        
        # Should merge into fewer excursions due to brief returns
        assert len(excursions) >= 1
        assert max(e['max_temp'] for e in excursions) == 16.0


class TestTemperatureConversions:
    """Test temperature conversion functions."""
    
    @pytest.mark.parametrize("fahrenheit,expected_celsius", [
        (32.0, 0.0),      # Freezing point
        (212.0, 100.0),   # Boiling point
        (98.6, 37.0),     # Body temperature
        (68.0, 20.0),     # Room temperature
        (-40.0, -40.0),   # Same in both scales
        (35.6, 2.0),      # Cold chain lower limit
        (46.4, 8.0),      # Cold chain upper limit
    ])
    def test_fahrenheit_to_celsius(self, fahrenheit, expected_celsius):
        """Test Fahrenheit to Celsius conversion."""
        result = fahrenheit_to_celsius(fahrenheit)
        assert abs(result - expected_celsius) < 0.1
    
    @pytest.mark.parametrize("celsius,expected_fahrenheit", [
        (0.0, 32.0),      # Freezing point
        (100.0, 212.0),   # Boiling point
        (37.0, 98.6),     # Body temperature
        (20.0, 68.0),     # Room temperature
        (-40.0, -40.0),   # Same in both scales
        (2.0, 35.6),      # Cold chain lower limit
        (8.0, 46.4),      # Cold chain upper limit
    ])
    def test_celsius_to_fahrenheit(self, celsius, expected_fahrenheit):
        """Test Celsius to Fahrenheit conversion."""
        result = celsius_to_fahrenheit(celsius)
        assert abs(result - expected_fahrenheit) < 0.1
    
    def test_conversion_round_trip(self):
        """Test that conversions are reversible."""
        test_values = [-40, -20, 0, 20, 37, 100]
        
        for celsius in test_values:
            fahrenheit = celsius_to_fahrenheit(celsius)
            back_to_celsius = fahrenheit_to_celsius(fahrenheit)
            assert abs(back_to_celsius - celsius) < 0.001


class TestComplexScenarios:
    """Test complex cold chain scenarios."""
    
    def test_gradual_temperature_drift(self):
        """Test detection of gradual temperature drift."""
        hours = 72
        timestamps = pd.date_range('2024-01-01', periods=hours, freq='1h')
        
        # Start in range, gradually drift out
        temperatures = []
        for i in range(hours):
            temp = 5.0 + (i * 0.1)  # Gradual increase
            temperatures.append(temp)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400,
            'sensor_uncertainty_C': 0.5
        }
        
        result = validate_coldchain_storage(df, spec)
        
        # Should fail due to drift out of range
        assert not result['pass']
        assert result['metrics']['excursion_count'] > 0
    
    def test_seasonal_variation_simulation(self):
        """Test with simulated seasonal temperature variations."""
        days = 7
        hours_per_day = 24
        total_hours = days * hours_per_day
        
        timestamps = pd.date_range('2024-01-01', periods=total_hours, freq='1h')
        
        # Simulate day/night temperature cycles
        temperatures = []
        for hour in range(total_hours):
            hour_of_day = hour % 24
            
            # Warmer during day (12-18), cooler at night
            if 12 <= hour_of_day <= 18:
                base_temp = 6.5
            else:
                base_temp = 4.5
            
            # Add some random variation
            temp = base_temp + np.random.normal(0, 0.5)
            temperatures.append(temp)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400 * days,
            'sensor_uncertainty_C': 0.5
        }
        
        result = validate_coldchain_storage(df, spec)
        
        # Check that metrics are calculated
        assert 'compliance_percent' in result['metrics']
        assert 'daily_stats' in result['metrics']
        assert len(result['metrics']['daily_stats']) == days
    
    def test_power_failure_scenario(self):
        """Test scenario simulating power failure."""
        hours = 48
        timestamps = pd.date_range('2024-01-01', periods=hours, freq='1h')
        
        temperatures = []
        for i in range(hours):
            if 10 <= i <= 18:  # 8-hour power failure
                # Temperature rises during power failure
                temp = 5.0 + (i - 10) * 2.0  # Rising temperature
                temp = min(temp, 20.0)  # Cap at 20 degrees C
            elif i > 18 and i <= 24:  # Recovery period
                # Temperature drops back down
                temp = 20.0 - (i - 18) * 2.5
                temp = max(temp, 5.0)
            else:
                temp = 5.0  # Normal operation
            
            temperatures.append(temp)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400,
            'sensor_uncertainty_C': 0.5
        }
        
        result = validate_coldchain_storage(df, spec)
        
        assert not result['pass']
        assert result['metrics']['excursion_count'] >= 1
        assert result['metrics']['max_temp'] >= 15.0
    
    def test_sensor_malfunction_handling(self):
        """Test handling of sensor malfunction (NaN values)."""
        hours = 48
        timestamps = pd.date_range('2024-01-01', periods=hours, freq='1h')
        
        temperatures = [5.0] * hours
        # Simulate sensor malfunction with NaN values
        temperatures[20:25] = [np.nan] * 5
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        spec = {
            'target_temp_C': 5.0,
            'hold_time_s': 86400,
            'sensor_uncertainty_C': 0.5
        }
        
        result = validate_coldchain_storage(df, spec)
        
        # Should handle NaN values gracefully
        assert 'metrics' in result
        assert isinstance(result['pass'], bool)