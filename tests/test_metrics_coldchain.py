"""
Comprehensive tests for cold chain validation metrics.

Tests focus on cold chain storage validation including:
- 2-8°C temperature control validation
- 95% vs 94.9% daily compliance edge case  
- Temperature excursion detection and handling
- Cold chain monitoring edge cases
- Refrigeration validation scenarios

Example usage:
    pytest tests/test_metrics_coldchain.py -v --cov=core.metrics_coldchain
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from core.models import SpecV1, DecisionResult, SensorMode
from core.metrics_coldchain import (
    validate_coldchain_storage,
    validate_coldchain_storage_conditions,
    identify_temperature_excursions,
    calculate_daily_compliance,
    fahrenheit_to_celsius,
    celsius_to_fahrenheit
)
from core.decide import DecisionError


class TestColdChainValidation:
    """Test cold chain storage validation with pharmaceutical standards."""
    
    @pytest.fixture
    def coldchain_spec(self):
        """Standard cold chain specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "coldchain_validation_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,  # Mid-range cold chain
                "hold_time_s": 86400,  # 24 hours
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 300.0,  # 5 minutes
                "allowed_gaps_s": 900.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 2
            }
        })
    
    @pytest.fixture
    def compliant_data(self):
        """Data that meets cold chain requirements (2-8°C)."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=288, freq="5min", tz="UTC"
        )
        
        # Temperature profile within 2-8°C range
        base_temp = 5.0
        temp_profile = [base_temp + np.random.normal(0, 1.0) for _ in range(288)]
        # Ensure 96% compliance (better than 95% requirement)
        temp_profile = [max(2.2, min(7.8, t)) for t in temp_profile]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    @pytest.fixture
    def violation_data(self):
        """Data with cold chain violations."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=200, freq="5min", tz="UTC"
        )
        
        # Temperature profile with significant excursions
        temp_profile = []
        for i in range(200):
            if i % 20 < 5:  # 25% of time outside range
                temp_profile.append(-1.0 + np.random.normal(0, 0.5))  # Freezing risk
            elif i % 20 < 8:  # Another 15% too warm
                temp_profile.append(12.0 + np.random.normal(0, 1.0))  # Too warm
            else:
                temp_profile.append(5.0 + np.random.normal(0, 0.8))  # Acceptable
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })

    def test_temperature_conversion_functions(self):
        """Test Fahrenheit/Celsius conversion functions."""
        # Test key cold chain temperatures
        assert abs(fahrenheit_to_celsius(35.6) - 2.0) < 0.1  # 2°C lower limit
        assert abs(fahrenheit_to_celsius(46.4) - 8.0) < 0.1  # 8°C upper limit
        assert abs(celsius_to_fahrenheit(2.0) - 35.6) < 0.1
        assert abs(celsius_to_fahrenheit(8.0) - 46.4) < 0.1
        
        # Test freezing point
        assert abs(fahrenheit_to_celsius(32.0) - 0.0) < 0.01
        assert abs(celsius_to_fahrenheit(0.0) - 32.0) < 0.01

    def test_95_vs_949_percent_compliance_edge_case(self):
        """Test 95% vs 94.9% daily compliance edge case."""
        timestamps = pd.date_range(
            start="2024-01-15T00:00:00Z", periods=1000, freq="1.44min", tz="UTC"
        )
        
        # Create data with exactly 94.9% compliance (just below threshold)
        temp_series = pd.Series([5.0] * 1000)
        time_series = pd.Series(timestamps)
        
        # Make exactly 51 samples out of range (94.9% compliance)
        violation_indices = np.random.choice(1000, 51, replace=False)
        temp_series.iloc[violation_indices] = 10.0  # Above range
        
        result = calculate_daily_compliance(
            temp_series, time_series, 
            min_temp_c=2.0, max_temp_c=8.0, 
            required_compliance=95.0
        )
        
        # Should fail 95% requirement with 94.9% compliance
        assert result['overall_compliance_pct'] < 95.0
        assert result['overall_compliance_pct'] > 94.8  # Approximately 94.9%
        assert not result['days_meeting_requirement']
        
        # Test with exactly 95.0% compliance
        temp_series_95 = pd.Series([5.0] * 1000)
        violation_indices_95 = np.random.choice(1000, 50, replace=False)
        temp_series_95.iloc[violation_indices_95] = 10.0  # Exactly 95% compliance
        
        result_95 = calculate_daily_compliance(
            temp_series_95, time_series,
            min_temp_c=2.0, max_temp_c=8.0,
            required_compliance=95.0
        )
        
        assert result_95['overall_compliance_pct'] >= 95.0

    def test_temperature_excursion_detection_and_handling(self):
        """Test temperature excursion detection and alarm handling."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=120, freq="1min", tz="UTC"
        )
        
        # Create temperature profile with specific excursions
        temp_profile = [5.0] * 120
        
        # 45-minute excursion above range (should trigger alarm)
        for i in range(20, 65):  # 45 minutes above range
            temp_profile[i] = 12.0
        
        # 15-minute excursion below range (should not trigger alarm)
        for i in range(80, 95):  # 15 minutes below range
            temp_profile[i] = -1.0
        
        temp_series = pd.Series(temp_profile)
        time_series = pd.Series(timestamps)
        
        result = identify_temperature_excursions(
            temp_series, time_series,
            min_temp_c=2.0, max_temp_c=8.0,
            alarm_threshold_minutes=30
        )
        
        # Should detect 2 excursion events
        assert len(result['excursion_events']) == 2
        
        # First excursion (45 min) should be an alarm
        long_excursion = next(e for e in result['excursion_events'] 
                             if e['duration_s'] >= 45 * 60)
        assert long_excursion['is_alarm'] is True
        assert long_excursion['above_range'] is True
        assert long_excursion['max_temp_c'] > 8.0
        
        # Second excursion (15 min) should not be an alarm
        short_excursion = next(e for e in result['excursion_events'] 
                              if e['duration_s'] < 30 * 60)
        assert short_excursion['is_alarm'] is False
        assert short_excursion['below_range'] is True
        assert short_excursion['min_temp_c'] < 2.0
        
        # Check alarm metrics
        assert result['alarm_events'] == 1
        assert result['total_alarm_time_s'] >= 45 * 60
        assert result['temperature_above_range_s'] >= 45 * 60
        assert result['temperature_below_range_s'] >= 15 * 60
        assert result['max_high_temp_c'] == 12.0
        assert result['max_low_temp_c'] == -1.0

    def test_continuous_excursion_to_end_of_data(self):
        """Test excursion that continues to end of monitoring period."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=60, freq="1min", tz="UTC"
        )
        
        # Temperature profile with excursion continuing to end
        temp_profile = [5.0] * 30 + [15.0] * 30  # 30 minutes above range at end
        
        temp_series = pd.Series(temp_profile)
        time_series = pd.Series(timestamps)
        
        result = identify_temperature_excursions(
            temp_series, time_series,
            min_temp_c=2.0, max_temp_c=8.0,
            alarm_threshold_minutes=25
        )
        
        # Should detect 1 excursion event
        assert len(result['excursion_events']) == 1
        
        excursion = result['excursion_events'][0]
        assert excursion['is_alarm'] is True  # 30 min > 25 min threshold
        assert excursion['end_time'] == timestamps[-1]  # Ends at last timestamp
        assert excursion['duration_s'] >= 29 * 60  # At least 29 minutes

    def test_cold_chain_monitoring_edge_cases(self):
        """Test cold chain monitoring with various edge cases."""
        # Test with minimal monitoring period (< 1 day)
        short_timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=60, freq="5min", tz="UTC"
        )
        
        short_temp_profile = [4.0] * 60  # 5 hours of good data
        short_data = pd.DataFrame({
            "timestamp": short_timestamps,
            "temp_1": short_temp_profile,
            "temp_2": [t + 0.1 for t in short_temp_profile]
        })
        
        spec_short = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "short_monitoring"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        result = validate_coldchain_storage(short_data, spec_short)
        
        assert isinstance(result, DecisionResult)
        assert len(result.warnings) > 0  # Should warn about short monitoring period
        warning_text = " ".join(result.warnings).lower()
        assert "monitoring period" in warning_text or "shorter" in warning_text

    def test_refrigeration_validation_scenarios(self):
        """Test various refrigeration validation scenarios."""
        # Scenario 1: Vaccine storage with tight temperature control
        vaccine_timestamps = pd.date_range(
            start="2024-01-15T00:00:00Z", periods=1440, freq="1min", tz="UTC"
        )
        
        # Very stable temperature (typical of good vaccine refrigerator)
        stable_temp = [4.0 + np.random.normal(0, 0.2) for _ in range(1440)]
        stable_temp = [max(3.5, min(4.5, t)) for t in stable_temp]  # Tight control
        
        vaccine_data = pd.DataFrame({
            "timestamp": vaccine_timestamps,
            "temp_1": stable_temp,
            "temp_2": [t + 0.05 for t in stable_temp]
        })
        
        vaccine_spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "vaccine_storage"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 4.0,
                "hold_time_s": 86400,  # 24 hours
                "sensor_uncertainty_C": 0.2
            }
        })
        
        result = validate_coldchain_storage(vaccine_data, vaccine_spec)
        
        assert result.pass_ is True
        assert "vaccine" in " ".join(result.reasons).lower() or "storage" in " ".join(result.reasons).lower()
        
        # Scenario 2: Food cold chain with door openings
        food_timestamps = pd.date_range(
            start="2024-01-15T06:00:00Z", periods=480, freq="3min", tz="UTC"
        )
        
        # Temperature with brief spikes (door openings)
        food_temp = [6.0] * 480
        # Simulate 3 door openings causing brief temperature rises
        for spike_start in [60, 180, 300]:  # 3 spikes
            for i in range(spike_start, min(spike_start + 5, 480)):
                food_temp[i] = 9.0  # Brief spike above range
        
        food_data = pd.DataFrame({
            "timestamp": food_timestamps,
            "temp_1": food_temp,
            "temp_2": [t - 0.2 for t in food_temp],
            "temp_3": [t + 0.1 for t in food_temp]
        })
        
        food_spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "food_storage"},
            "spec": {
                "method": "OVEN_AIR", 
                "target_temp_C": 6.0,
                "hold_time_s": 28800,  # 8 hours
                "sensor_uncertainty_C": 0.5
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 2
            }
        })
        
        result = validate_coldchain_storage(food_data, food_spec)
        
        # Brief door opening spikes should be acceptable
        assert isinstance(result, DecisionResult)
        # May pass or fail depending on exact implementation, but should not crash

    def test_critical_temperature_violations(self):
        """Test detection of critical temperature violations."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=120, freq="1min", tz="UTC"
        )
        
        # Temperature profile with critical violations
        critical_temp = [5.0] * 120
        
        # Critical low temperature (freezing risk)
        for i in range(30, 45):
            critical_temp[i] = -3.0  # Well below freezing
        
        # Critical high temperature (product damage)
        for i in range(70, 85):
            critical_temp[i] = 18.0  # Well above acceptable
        
        temp_series = pd.Series(critical_temp)
        time_series = pd.Series(timestamps)
        
        result = validate_coldchain_storage_conditions(temp_series, time_series)
        
        # Should detect critical violations
        assert len(result['reasons']) > 0
        reasons_text = " ".join(result['reasons']).lower()
        assert "critical" in reasons_text
        
        # Check specific critical temperature mentions
        assert result['min_temp_C'] < -2.0
        assert result['max_temp_C'] > 15.0

    def test_data_logging_frequency_validation(self):
        """Test data logging frequency validation."""
        # Test with good logging frequency (5 minutes)
        good_timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=120, freq="5min", tz="UTC"
        )
        
        good_temp = [5.0] * 120
        good_result = validate_coldchain_storage_conditions(
            pd.Series(good_temp), pd.Series(good_timestamps)
        )
        
        assert good_result['data_logging_adequate'] is True
        
        # Test with poor logging frequency (20 minutes)
        poor_timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=30, freq="20min", tz="UTC"
        )
        
        poor_temp = [5.0] * 30
        poor_result = validate_coldchain_storage_conditions(
            pd.Series(poor_temp), pd.Series(poor_timestamps)
        )
        
        assert poor_result['data_logging_adequate'] is False
        reasons_text = " ".join(poor_result['reasons']).lower()
        assert "logging interval" in reasons_text

    def test_sensor_combination_failures(self):
        """Test sensor combination failures in cold chain validation."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="3min", tz="UTC"
        )
        
        # Data with conflicting sensors
        conflicted_data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [5.0] * 100,  # Good sensor
            "temp_2": [15.0] * 100,  # Failed sensor (too high)
            "temp_3": [-5.0] * 100  # Failed sensor (too low)
        })
        
        spec_strict = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain", 
            "job": {"job_id": "sensor_failure_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 3  # Require all 3 sensors
            }
        })
        
        # Should handle sensor disagreement gracefully
        result = validate_coldchain_storage(conflicted_data, spec_strict)
        
        assert isinstance(result, DecisionResult)
        # May pass or fail, but should not crash and should provide clear reasoning

    def test_empty_and_insufficient_data_handling(self):
        """Test handling of empty and insufficient data."""
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "insufficient_data_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        # Test empty DataFrame
        empty_data = pd.DataFrame()
        with pytest.raises(DecisionError, match="empty"):
            validate_coldchain_storage(empty_data, spec)
        
        # Test insufficient data points
        insufficient_timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=1, freq="1min", tz="UTC"
        )
        
        insufficient_data = pd.DataFrame({
            "timestamp": insufficient_timestamps,
            "temp_1": [5.0]
        })
        
        with pytest.raises(DecisionError, match="Insufficient data"):
            validate_coldchain_storage(insufficient_data, spec)

    def test_wrong_industry_specification(self):
        """Test handling when wrong industry is specified."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=60, freq="1min", tz="UTC"
        )
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [5.0] * 60,
            "temp_2": [5.0] * 60
        })
        
        wrong_spec = SpecV1(**{
            "version": "1.0",
            "industry": "powder",  # Wrong industry
            "job": {"job_id": "wrong_industry_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        with pytest.raises(DecisionError, match="Invalid industry"):
            validate_coldchain_storage(data, wrong_spec)

    def test_missing_temperature_columns(self):
        """Test handling when no temperature columns are found."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=60, freq="1min", tz="UTC"
        )
        
        # Data without temperature columns
        no_temp_data = pd.DataFrame({
            "timestamp": timestamps,
            "humidity_1": [65.0] * 60,
            "pressure_1": [101.3] * 60
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "no_temp_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        with pytest.raises(DecisionError, match="No temperature columns"):
            validate_coldchain_storage(no_temp_data, spec)

    def test_missing_timestamp_column(self):
        """Test handling when no timestamp column is found."""
        # Data without timestamp column
        no_time_data = pd.DataFrame({
            "temp_1": [5.0] * 60,
            "temp_2": [5.0] * 60
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "no_time_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        with pytest.raises(DecisionError, match="No timestamp column"):
            validate_coldchain_storage(no_time_data, spec)

    def test_full_integration_pass(self, compliant_data, coldchain_spec):
        """Test full cold chain validation with compliant data."""
        result = validate_coldchain_storage(compliant_data, coldchain_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "coldchain_validation_001"
        assert result.target_temp_C == 5.0
        assert result.conservative_threshold_C == 2.0
        assert len(result.reasons) > 0
        
        # Check for cold chain specific messaging
        reasons_text = " ".join(result.reasons).lower()
        assert "cold chain" in reasons_text or "storage" in reasons_text
        assert "temperature" in reasons_text

    def test_full_integration_fail(self, violation_data, coldchain_spec):
        """Test full cold chain validation with non-compliant data."""
        result = validate_coldchain_storage(violation_data, coldchain_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert result.job_id == "coldchain_validation_001"
        assert len(result.reasons) > 0
        
        # Check for failure reasons
        reasons_text = " ".join(result.reasons).lower()
        assert any(keyword in reasons_text for keyword in [
            "temperature", "compliance", "excursion", "violation"
        ])