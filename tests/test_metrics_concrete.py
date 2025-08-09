"""
Test concrete curing metrics and validation logic.

This module tests the concrete curing industry-specific validation algorithms
to ensure proper pass/fail decisions based on temperature and humidity thresholds.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from core.metrics_concrete import (
    validate_concrete_curing,
    validate_concrete_curing_conditions,
    calculate_temperature_stability,
    detect_humidity_columns,
    fahrenheit_to_celsius,
    celsius_to_fahrenheit
)
from core.models import SpecV1, DecisionResult
from core.temperature_utils import DecisionError


class TestConcreteMetrics:
    """Test concrete curing validation metrics."""
    
    def test_temperature_conversion_utilities(self):
        """Test temperature conversion functions."""
        # Test Fahrenheit to Celsius
        assert abs(fahrenheit_to_celsius(32.0) - 0.0) < 0.01
        assert abs(fahrenheit_to_celsius(68.0) - 20.0) < 0.01
        assert abs(fahrenheit_to_celsius(212.0) - 100.0) < 0.01
        
        # Test Celsius to Fahrenheit
        assert abs(celsius_to_fahrenheit(0.0) - 32.0) < 0.01
        assert abs(celsius_to_fahrenheit(20.0) - 68.0) < 0.01
        assert abs(celsius_to_fahrenheit(100.0) - 212.0) < 0.01
        
        # Test round-trip conversion
        temp_c = 18.5
        temp_f = celsius_to_fahrenheit(temp_c)
        temp_c_back = fahrenheit_to_celsius(temp_f)
        assert abs(temp_c - temp_c_back) < 0.01

    def test_humidity_detection(self):
        """Test humidity column detection."""
        # Test various humidity column names
        df = pd.DataFrame({
            'timestamp': [datetime.now(timezone.utc)],
            'temp_1': [20.0],
            'humidity_1': [95.0],
            'rh_sensor': [92.0],
            'relative_humidity': [98.0],
            'moisture_content': [85.0],
            'sensor_1_rh': [96.0]
        })
        
        humidity_cols = detect_humidity_columns(df)
        expected_cols = ['humidity_1', 'rh_sensor', 'relative_humidity', 'moisture_content', 'sensor_1_rh']
        
        for col in expected_cols:
            assert col in humidity_cols, f"Expected humidity column {col} not detected"
        
        # Test no humidity columns
        df_no_humidity = pd.DataFrame({
            'timestamp': [datetime.now(timezone.utc)],
            'temp_1': [20.0],
            'temp_2': [21.0]
        })
        
        humidity_cols = detect_humidity_columns(df_no_humidity)
        assert len(humidity_cols) == 0

    def test_temperature_stability_calculation(self):
        """Test temperature stability metrics calculation."""
        # Create test data with stable temperatures
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=20, freq='30S', tz='UTC')
        stable_temps = pd.Series([18.0 + 0.1 * i for i in range(20)])
        
        stability = calculate_temperature_stability(stable_temps, timestamps, max_rate_change=5.0)
        
        assert stability['temp_stability_valid'] == True
        assert stability['max_temp_change_rate_C_per_h'] < 5.0
        assert 'temperature_range_C' in stability
        assert 'std_deviation_C' in stability
        
        # Test with rapid temperature changes
        rapid_temps = pd.Series([18.0, 25.0, 10.0, 30.0, 5.0] * 4)
        timestamps_rapid = pd.date_range('2024-01-01 10:00:00', periods=20, freq='1min', tz='UTC')
        
        stability_rapid = calculate_temperature_stability(rapid_temps, timestamps_rapid, max_rate_change=5.0)
        
        assert stability_rapid['temp_stability_valid'] == False
        assert stability_rapid['max_temp_change_rate_C_per_h'] > 5.0
        assert stability_rapid['temp_stability_violations'] > 0

    def test_temperature_stability_short_series(self):
        """Test temperature stability with insufficient data."""
        # Test with very short series
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=2, freq='30S', tz='UTC')
        temps = pd.Series([18.0, 18.5])
        
        stability = calculate_temperature_stability(temps, timestamps)
        
        # Should return safe defaults
        assert stability['temp_stability_valid'] == True
        assert stability['max_temp_change_rate_C_per_h'] == 0.0
        assert stability['avg_temp_change_rate_C_per_h'] == 0.0
        assert stability['temp_stability_violations'] == 0

    def test_concrete_curing_conditions_validation(self):
        """Test concrete curing conditions validation."""
        # Create good curing conditions data
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='30S', tz='UTC')
        good_temps = pd.Series([18.0 + np.sin(i/10) * 2 for i in range(50)])  # 16-20°C range
        good_humidity = pd.Series([96.0 + np.random.normal(0, 1) for _ in range(50)])  # ~96% RH
        
        metrics = validate_concrete_curing_conditions(good_temps, timestamps, good_humidity)
        
        assert metrics['temperature_range_valid'] == True
        assert metrics['critical_period_temp_valid'] == True
        assert metrics['humidity_valid'] == True
        assert metrics['temperature_stability_valid'] == True
        assert len(metrics['reasons']) == 0  # No failure reasons
        
        # Test with poor curing conditions
        bad_temps = pd.Series([5.0 + i * 0.5 for i in range(50)])  # Cold start, gradual warming
        bad_humidity = pd.Series([70.0 + np.random.normal(0, 5) for _ in range(50)])  # Low humidity
        
        metrics_bad = validate_concrete_curing_conditions(bad_temps, timestamps, bad_humidity)
        
        assert metrics_bad['temperature_range_valid'] == False
        assert metrics_bad['humidity_valid'] == False
        assert len(metrics_bad['reasons']) > 0

    def test_validate_concrete_curing_pass_case(self):
        """Test concrete curing validation with passing conditions."""
        # Create normalized dataframe with good curing data
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='30S', tz='UTC')
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': [18.0 + np.sin(i/10) * 1.5 for i in range(50)],  # 16.5-19.5°C
            'sensor_2': [17.8 + np.sin(i/10) * 1.5 for i in range(50)],
            'sensor_3': [18.2 + np.sin(i/10) * 1.5 for i in range(50)]
        })
        
        # Create concrete specification
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_concrete_pass"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,  # 1 hour
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 1800.0,
                "allowed_gaps_s": 7200.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 2
            }
        }
        
        spec = SpecV1(**spec_data)
        result = validate_concrete_curing(normalized_df, spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ == True
        assert result.status == 'PASS'
        assert result.industry == "concrete"
        assert result.job_id == "test_concrete_pass"
        assert len(result.reasons) > 0  # Should have success reasons

    def test_validate_concrete_curing_fail_case(self):
        """Test concrete curing validation with failing conditions."""
        # Create normalized dataframe with poor curing data
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='30S', tz='UTC')
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': [5.0 + i * 0.3 for i in range(50)],  # Cold temperatures
            'sensor_2': [4.8 + i * 0.3 for i in range(50)],
            'sensor_3': [5.2 + i * 0.3 for i in range(50)]
        })
        
        # Create concrete specification
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_concrete_fail"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 1800.0,
                "allowed_gaps_s": 7200.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 2
            }
        }
        
        spec = SpecV1(**spec_data)
        result = validate_concrete_curing(normalized_df, spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ == False
        assert result.status == 'FAIL'
        assert result.industry == "concrete"
        assert result.job_id == "test_concrete_fail"
        assert len(result.reasons) > 0  # Should have failure reasons

    def test_insufficient_data_points_error(self):
        """Test that insufficient data points raises appropriate error."""
        # Create dataframe with too few points
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=5, freq='30S', tz='UTC')
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': [18.0] * 5,
            'sensor_2': [17.8] * 5,
            'sensor_3': [18.2] * 5
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_insufficient"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 2
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="Insufficient data points for concrete curing analysis"):
            validate_concrete_curing(normalized_df, spec)

    def test_empty_dataframe_error(self):
        """Test that empty dataframe raises appropriate error."""
        normalized_df = pd.DataFrame()
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_empty"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="Normalized DataFrame is empty"):
            validate_concrete_curing(normalized_df, spec)

    def test_wrong_industry_error(self):
        """Test that wrong industry specification raises appropriate error."""
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=20, freq='30S', tz='UTC')
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': [18.0] * 20,
            'sensor_2': [17.8] * 20,
            'sensor_3': [18.2] * 20
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "powder",  # Wrong industry
            "job": {"job_id": "test_wrong_industry"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="Invalid industry 'powder' for concrete curing validation"):
            validate_concrete_curing(normalized_df, spec)

    def test_no_temperature_columns_error(self):
        """Test that dataframe without temperature columns raises error."""
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=20, freq='30S', tz='UTC')
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'humidity_1': [95.0] * 20,
            'other_data': [1.0] * 20
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_no_temp"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="No temperature columns found in normalized data"):
            validate_concrete_curing(normalized_df, spec)

    def test_concrete_with_humidity_sensors(self):
        """Test concrete validation with humidity sensors."""
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='30S', tz='UTC')
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': [18.0 + np.sin(i/10) * 1.0 for i in range(50)],
            'sensor_2': [17.8 + np.sin(i/10) * 1.0 for i in range(50)],
            'humidity_1': [96.0 + np.random.normal(0, 2) for _ in range(50)],
            'humidity_2': [95.5 + np.random.normal(0, 2) for _ in range(50)]
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_with_humidity"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            },
            "sensor_selection": {
                "mode": "mean",
                "sensors": ["sensor_1", "sensor_2", "humidity_1", "humidity_2"],
                "require_at_least": 2
            }
        }
        
        spec = SpecV1(**spec_data)
        result = validate_concrete_curing(normalized_df, spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ == True
        assert result.industry == "concrete"
        # Should include warnings about humidity data
        assert len(result.warnings) == 0 or any('humidity' in w.lower() for w in result.warnings)

    def test_concrete_rapid_temperature_changes(self):
        """Test concrete validation with rapid temperature changes."""
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=30, freq='1min', tz='UTC')
        
        # Create data with rapid temperature swings
        rapid_temps = []
        for i in range(30):
            if i % 5 == 0:
                rapid_temps.append(25.0)  # Hot spikes
            elif i % 5 == 2:
                rapid_temps.append(10.0)  # Cold dips
            else:
                rapid_temps.append(18.0)  # Normal
        
        normalized_df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': rapid_temps,
            'sensor_2': [t - 0.2 for t in rapid_temps],
            'sensor_3': [t + 0.2 for t in rapid_temps]
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete", 
            "job": {"job_id": "test_rapid_changes"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 2
            }
        }
        
        spec = SpecV1(**spec_data)
        result = validate_concrete_curing(normalized_df, spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ == False  # Should fail due to temperature instability
        assert result.industry == "concrete"
        # Should have failure reason about temperature changes
        failure_reasons = ' '.join(result.reasons).lower()
        assert 'temperature' in failure_reasons


if __name__ == "__main__":
    pytest.main([__file__])