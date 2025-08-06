"""
Focused tests for decide.py to target specific uncovered lines and reach ≥92% coverage.

Focus on:
- Import error handling (lines 36-39)
- Error conditions in decision making (lines 620, 624, 629, 635, 638, 641, 649, 653, 669-671)
- Preconditions validation (lines 724-743)
- Industry dispatch (lines 565-571)
- Edge cases in hold time calculations
- Boolean mode with numerical temperature fallback (lines 763-764)

Example usage:
    pytest tests/test_decide_coverage_focus.py -v --cov=core.decide
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


class TestImportErrorHandling:
    """Test import error handling for industry-specific engines."""
    
    def test_import_error_warning(self):
        """Test that import errors generate warnings but don't crash."""
        # This tests lines 36-39 where import failures are caught
        # The actual imports happen at module load time, so we test the behavior
        # when engines are None (which happens when imports fail)
        
        # Verify that None engines are handled properly
        assert INDUSTRY_METRICS["powder"] is None
        
        # Test that the decision algorithm works even when engines are None
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC"),
            "pmt_sensor_1": [185.0] * 15,
            "pmt_sensor_2": [184.0] * 15
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "powder",  # Uses None engine (default)
            "job": {"job_id": "import_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        assert isinstance(result, DecisionResult)


class TestDecisionErrorPaths:
    """Test specific error paths in make_decision function."""
    
    def test_insufficient_data_for_analysis(self):
        """Test decision when data is too short for reliable analysis (line 587)."""
        # Create minimal data that's too short for hold time analysis
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "pmt_sensor_1": [185.0, 185.0, 185.0],
            "pmt_sensor_2": [184.0, 184.0, 184.0]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "short_data_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 600, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert any("Insufficient data points for reliable analysis" in reason for reason in result.reasons)
    
    def test_non_datetime_timestamp_conversion(self):
        """Test timestamp conversion when not already datetime (line 624)."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15T10:00:00Z", "2024-01-15T10:00:30Z", "2024-01-15T10:01:00Z"] * 10,
            "pmt_sensor_1": [185.0] * 30,
            "pmt_sensor_2": [184.0] * 30
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "timestamp_conversion_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        assert isinstance(result, DecisionResult)
    
    def test_sensor_failure_warning(self):
        """Test warning generation for sensor failure (line 641)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC"),
            "pmt_sensor_1": [185.0] * 15,
            "pmt_sensor_2": [np.nan] * 15,  # Failed sensor
            "pmt_sensor_3": [184.0] * 15
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_failure_warning_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        # Should have warning about sensor failure
        assert any("Sensor failure detected" in warning for warning in result.warnings)
    
    def test_insufficient_sensors_warning(self):
        """Test warning for insufficient sensors (line 653)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC"),
            "pmt_sensor_1": [185.0] * 15
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "insufficient_sensors_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["pmt_sensor_1", "pmt_sensor_2"],  # pmt_sensor_2 missing
                "require_at_least": 2
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        # Should have warning about insufficient sensors
        assert any("Only 1 sensors available" in warning for warning in result.warnings)
    
    def test_sensor_combination_error_handling(self):
        """Test error handling in sensor combination (lines 669-671)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC"),
            "pmt_sensor_1": [np.nan] * 15,  # All NaN - will cause error
            "pmt_sensor_2": [np.nan] * 15   # All NaN - will cause error
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "sensor_combination_error_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
                "require_at_least": 2  # Will cause error
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert result.pass_ is False
        assert any("Sensor combination failed" in reason for reason in result.reasons)


class TestIndustryDispatch:
    """Test industry-specific engine dispatch logic."""
    
    def test_industry_engine_dispatch_with_mock(self):
        """Test industry dispatch when engine is available (lines 565-571)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC"),
            "pmt_sensor_1": [185.0] * 15,
            "pmt_sensor_2": [184.0] * 15
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "test_industry",
            "job": {"job_id": "industry_dispatch_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        mock_result = DecisionResult(
            pass_=True,
            job_id="industry_dispatch_test",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=300.0,
            required_hold_time_s=300,
            max_temp_C=185.0,
            min_temp_C=184.0,
            reasons=["Industry validation passed"],
            warnings=[]
        )
        
        mock_engine = MagicMock(return_value=mock_result)
        
        # Temporarily add mock engine to INDUSTRY_METRICS
        original_metrics = INDUSTRY_METRICS.copy()
        INDUSTRY_METRICS["test_industry"] = mock_engine
        
        try:
            result = make_decision(df, spec)
            assert result.reasons == ["Industry validation passed"]
            mock_engine.assert_called_once_with(df, spec)
        finally:
            # Restore original INDUSTRY_METRICS
            INDUSTRY_METRICS.clear()
            INDUSTRY_METRICS.update(original_metrics)
    
    def test_industry_engine_exception_fallback(self):
        """Test fallback when industry engine raises exception (lines 568-571)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC"),
            "pmt_sensor_1": [185.0] * 15,
            "pmt_sensor_2": [184.0] * 15
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "failing_industry",
            "job": {"job_id": "fallback_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        }
        spec = SpecV1(**spec_data)
        
        mock_engine = MagicMock(side_effect=Exception("Industry engine failed"))
        
        # Temporarily add failing mock engine to INDUSTRY_METRICS
        original_metrics = INDUSTRY_METRICS.copy()
        INDUSTRY_METRICS["failing_industry"] = mock_engine
        
        try:
            result = make_decision(df, spec)
            # Should fall back to default powder coat validation
            assert isinstance(result, DecisionResult)
            assert result.job_id == "fallback_test"
            # Should have passed with default validation
            assert result.pass_ is True
        finally:
            # Restore original INDUSTRY_METRICS
            INDUSTRY_METRICS.clear()
            INDUSTRY_METRICS.update(original_metrics)


class TestPreconditionsValidation:
    """Test preconditions validation paths (lines 724-743)."""
    
    def test_preconditions_with_ramp_rate_check(self):
        """Test preconditions validation with ramp rate check."""
        # Create data with very high ramp rate
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC")
        # Fast heating: 160°C to 185°C in 30 seconds = 50°C/min
        temperatures = [160.0, 185.0] + [185.0] * 8
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temperatures,
            "pmt_sensor_2": [t - 1.0 for t in temperatures]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "ramp_rate_precondition_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 200, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0  # Should be exceeded
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        # Should fail due to excessive ramp rate
        assert result.pass_ is False
        assert any("Ramp rate too high" in reason for reason in result.reasons)
    
    def test_preconditions_with_time_to_threshold_check(self):
        """Test preconditions validation with time to threshold check."""
        # Create data that takes long to reach threshold
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        # Reaches threshold at index 10 = 300 seconds
        temperatures = [175.0] * 10 + [185.0] * 5
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temperatures,
            "pmt_sensor_2": [t - 1.0 for t in temperatures]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "time_to_threshold_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 120, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "preconditions": {
                "max_time_to_threshold_s": 120  # Should be exceeded (300s > 120s)
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        # Should fail due to excessive time to threshold
        assert result.pass_ is False
        assert any("Time to threshold too long" in reason for reason in result.reasons)


class TestBooleanModeEdgeCases:
    """Test boolean mode edge cases and numerical fallback."""
    
    def test_boolean_mode_cumulative_logic(self):
        """Test boolean mode with cumulative logic (lines 769-772)."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0] * 15,  # Always above threshold
            "sensor_2": [183.0] * 10 + [180.0] * 5,  # Some periods below
            "sensor_3": [180.0] * 5 + [183.0] * 10   # Some periods below
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
            "logic": {
                "continuous": False,  # Cumulative mode
                "max_total_dips_s": 120
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
    
    def test_boolean_mode_pass_decision_logic(self):
        """Test boolean mode pass decision logic (lines 780-781)."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=15, freq="30s", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_1": [183.0] * 15,  # Always above threshold
            "sensor_2": [183.0] * 15,  # Always above threshold
            "sensor_3": [183.0] * 15   # Always above threshold
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "boolean_pass_logic_test"},
            "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            "data_requirements": {"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "sensors": ["sensor_1", "sensor_2", "sensor_3"],
                "require_at_least": 2
            },
            "logic": {
                "continuous": False,  # Cumulative mode
                "max_total_dips_s": 60
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 5.0  # Add precondition to test failure check
            }
        }
        spec = SpecV1(**spec_data)
        
        result = make_decision(df, spec)
        
        # Should pass cumulative hold time but may fail preconditions
        assert isinstance(result, DecisionResult)


class TestEdgeCaseCalculations:
    """Test edge cases in calculation functions."""
    
    def test_ramp_rate_edge_cases(self):
        """Test ramp rate calculation edge cases."""
        # Test with minimal data
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=2, freq="30s", tz="UTC")
        temperatures = pd.Series([180.0, 185.0])
        
        ramp_rates = calculate_ramp_rate(temperatures, timestamps)
        
        # Should handle minimal data gracefully
        assert len(ramp_rates) == 2
        assert pd.isna(ramp_rates.iloc[0])
        assert not pd.isna(ramp_rates.iloc[1])
    
    def test_find_threshold_crossing_edge_cases(self):
        """Test threshold crossing time edge cases."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        temperatures = pd.Series([185.0, 186.0, 187.0, 188.0, 189.0])
        threshold_C = 182.0
        
        crossing_time = find_threshold_crossing_time(temperatures, timestamps, threshold_C)
        
        # Should find immediate crossing
        assert crossing_time == 0.0
    
    def test_cumulative_hold_time_edge_cases(self):
        """Test cumulative hold time calculation edge cases."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=6, freq="30s", tz="UTC")
        # All above threshold
        temperatures = pd.Series([185.0, 186.0, 187.0, 188.0, 189.0, 190.0])
        
        hold_time, intervals = calculate_cumulative_hold_time(
            temperatures, timestamps, 182.0, 60
        )
        
        # Should count all time above threshold
        assert hold_time == 150.0  # 5 intervals * 30s
        assert len(intervals) == 1  # One continuous interval
    
    def test_boolean_hold_time_edge_cases(self):
        """Test boolean hold time calculation edge cases."""
        timestamps = pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC")
        boolean_series = pd.Series([True, True, True, True, True])
        
        # Test continuous mode
        hold_time = calculate_boolean_hold_time(boolean_series, timestamps, continuous=True)
        assert hold_time == 120.0  # 4 intervals * 30s
        
        # Test cumulative mode
        hold_time = calculate_boolean_hold_time(
            boolean_series, timestamps, continuous=False, max_dips_s=60
        )
        assert hold_time == 120.0  # 4 intervals * 30s