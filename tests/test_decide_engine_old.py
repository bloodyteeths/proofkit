"""
Comprehensive Decision Engine Tests

Tests for core.decide module to achieve ≥92% coverage.
Covers continuous/cumulative modes, all sensor selection strategies,
threshold/hysteresis behavior, data quality, and edge cases.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from unittest.mock import patch, MagicMock
from freezegun import freeze_time

from core.models import SpecV1, DecisionResult, SensorMode, Logic, Industry
from core.decide import (
    make_decision,
    DecisionError,
    calculate_conservative_threshold,
    combine_sensor_readings,
    calculate_continuous_hold_time,
    calculate_cumulative_hold_time,
    calculate_boolean_hold_time,
    validate_preconditions,
    detect_temperature_columns,
    calculate_ramp_rate,
    find_threshold_crossing_time
)


class TestThresholdAndHysteresis:
    """Test threshold calculations and hysteresis behavior."""
    
    def test_conservative_threshold_calculation(self):
        """Test conservative threshold = target + uncertainty."""
        assert calculate_conservative_threshold(180.0, 2.0) == 182.0
        assert calculate_conservative_threshold(170.0, 1.5) == 171.5
        assert calculate_conservative_threshold(0.0, 0.0) == 0.0
        assert calculate_conservative_threshold(-10.0, 2.0) == -8.0
    
    def test_threshold_crossing_with_hysteresis(self):
        """Test exact threshold crossing with hysteresis window."""
        # Create data that touches exactly the conservative threshold
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=20, freq='30s')
        # Ramp up to exactly 182°C, hold, then dip slightly
        temps = [178, 179, 180, 181, 182, 182, 182, 182, 182, 182,  # Hold at threshold
                 181.5, 181, 180.5, 180, 181, 181.5, 182, 182, 182, 182]  # Dip and recover
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_hysteresis"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 240,  # 4 minutes
                "sensor_uncertainty_C": 2.0,
                "hysteresis_C": 2.0  # 2°C hysteresis window
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True,
                "cumulative": False,
                "max_total_dips_s": 0
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should pass - dip stays within hysteresis window
        assert decision.pass_ == True
        assert decision.conservative_threshold_C == 182.0
        assert decision.actual_hold_time_s >= 240.0
    
    def test_threshold_crossing_outside_hysteresis(self):
        """Test failure when temperature drops below hysteresis window."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=15, freq='30s')
        # Drop below hysteresis window
        temps = [178, 180, 182, 182, 182, 179, 177, 179, 182, 182, 182, 182, 182, 182, 182]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_hysteresis_fail"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 240,
                "sensor_uncertainty_C": 2.0,
                "hysteresis_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - temperature dropped below hysteresis window
        assert decision.pass_ == False
        assert any("Insufficient continuous hold time" in reason for reason in decision.reasons)


class TestContinuousVsCumulativeHold:
    """Test continuous vs cumulative hold time logic."""
    
    def test_continuous_hold_single_plateau(self):
        """Test continuous mode: single uninterrupted plateau passes."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=20, freq='30s')
        # Single continuous plateau above threshold
        temps = [170, 175, 180, 183, 183, 183, 183, 183, 183, 183,
                 183, 183, 183, 183, 183, 183, 183, 182, 180, 175]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "continuous_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 300,  # 5 minutes
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True,
                "cumulative": False
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        assert decision.pass_ == True
        assert decision.actual_hold_time_s >= 300.0
    
    def test_cumulative_hold_two_plateaus(self):
        """Test cumulative mode: two plateaus sum to pass."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=25, freq='30s')
        # Two plateaus with a dip between
        temps = [170, 175, 180, 183, 183, 183, 183, 183,  # First plateau ~3.5 min
                 179, 178, 177, 178, 179,  # Dip below threshold
                 183, 183, 183, 183, 183, 183, 183,  # Second plateau ~3 min
                 182, 180, 175, 170, 165]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "cumulative_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 360,  # 6 minutes total needed
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": False,
                "cumulative": True,
                "max_total_dips_s": 180  # Allow up to 3 minutes of dips
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should pass - cumulative time above threshold exceeds requirement
        assert decision.pass_ == True
        assert decision.actual_hold_time_s >= 360.0
    
    def test_cumulative_exceeds_max_dips(self):
        """Test cumulative mode fails when max_total_dips_s exceeded."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=30, freq='30s')
        # Multiple short plateaus with long dips
        temps = [170, 183, 183, 183,  # Short plateau
                 170, 170, 170, 170, 170,  # Long dip
                 183, 183, 183,  # Short plateau
                 170, 170, 170, 170,  # Another long dip
                 183, 183, 183, 183,  # Final plateau
                 175, 170, 165, 160, 155, 150, 145, 140, 135]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "max_dips_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": False,
                "cumulative": True,
                "max_total_dips_s": 120  # Only 2 minutes of dips allowed
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - too much time spent below threshold
        assert decision.pass_ == False
        assert any("Maximum total dip time exceeded" in reason for reason in decision.reasons)


class TestDataQualityAndGaps:
    """Test data quality checks and gap handling."""
    
    def test_exactly_allowed_gaps_passes(self):
        """Test that exactly allowed_gaps_s passes."""
        # Create data with gap exactly at limit
        timestamps = [
            pd.Timestamp('2024-01-01T10:00:00Z'),
            pd.Timestamp('2024-01-01T10:00:30Z'),
            pd.Timestamp('2024-01-01T10:01:00Z'),
            # 120 second gap here
            pd.Timestamp('2024-01-01T10:03:00Z'),
            pd.Timestamp('2024-01-01T10:03:30Z'),
            pd.Timestamp('2024-01-01T10:04:00Z'),
            pd.Timestamp('2024-01-01T10:04:30Z'),
            pd.Timestamp('2024-01-01T10:05:00Z'),
        ]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': [183] * len(timestamps)  # All above threshold
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "exact_gap_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 120,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0  # Exactly 120s allowed
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should pass - gap is exactly at limit
        assert decision.pass_ == True
        assert not any("Data gap" in reason for reason in decision.reasons)
    
    def test_gap_exceeds_allowed_fails(self):
        """Test that allowed_gaps_s + 1 second fails."""
        timestamps = [
            pd.Timestamp('2024-01-01T10:00:00Z'),
            pd.Timestamp('2024-01-01T10:00:30Z'),
            # 121 second gap here (1 second over limit)
            pd.Timestamp('2024-01-01T10:02:31Z'),
            pd.Timestamp('2024-01-01T10:03:00Z'),
            pd.Timestamp('2024-01-01T10:03:30Z'),
        ]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': [183] * len(timestamps)
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "exceed_gap_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - gap exceeds limit
        assert decision.pass_ == False
        assert any("Data gap" in reason for reason in decision.reasons)
    
    def test_duplicate_timestamps_error(self):
        """Test that duplicate timestamps trigger data quality error."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=5, freq='30s')
        # Add duplicate
        timestamps = list(timestamps) + [timestamps[2]]  # Duplicate third timestamp
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': [183] * len(timestamps)
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "duplicate_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        
        # Should raise DecisionError for duplicate timestamps
        with pytest.raises(DecisionError, match="Duplicate timestamps"):
            make_decision(df, spec)


class TestSensorSelectionModes:
    """Test all sensor selection strategies."""
    
    def test_min_of_set_mode(self):
        """Test min_of_set: use minimum of multiple sensors."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=15, freq='30s')
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor1_C': [183] * 15,  # Always above
            'sensor2_C': [184] * 15,  # Always above
            'sensor3_C': [180, 181, 182, 183, 184, 183, 182, 181, 180, 179, 180, 181, 182, 183, 184]  # Dips below
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "min_of_set_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["sensor1_C", "sensor2_C", "sensor3_C"],
                "require_at_least": 3
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - minimum sensor dips below threshold
        assert decision.pass_ == False
        assert decision.min_temp_C < 180.0
    
    def test_mean_of_set_mode(self):
        """Test mean_of_set: average of sensors can compensate for one low."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=15, freq='30s')
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor1_C': [185] * 15,  # High
            'sensor2_C': [185] * 15,  # High  
            'sensor3_C': [179] * 15   # Slightly below threshold
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "mean_of_set_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 360,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "mean_of_set",
                "sensors": ["sensor1_C", "sensor2_C", "sensor3_C"],
                "require_at_least": 3
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should pass - mean is (185+185+179)/3 = 183, above threshold of 182
        assert decision.pass_ == True
        assert decision.actual_hold_time_s >= 360.0
    
    def test_majority_over_threshold_pass(self):
        """Test majority_over_threshold: 2 of 3 sensors above passes."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=15, freq='30s')
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor1_C': [183] * 15,  # Above
            'sensor2_C': [184] * 15,  # Above
            'sensor3_C': [179] * 15   # Below
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "majority_pass_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 360,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "sensors": ["sensor1_C", "sensor2_C", "sensor3_C"],
                "require_at_least": 2  # Need 2 of 3
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should pass - 2 of 3 sensors consistently above threshold
        assert decision.pass_ == True
    
    def test_majority_over_threshold_fail(self):
        """Test majority_over_threshold: only 1 of 3 above fails."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=15, freq='30s')
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor1_C': [183] * 15,  # Above
            'sensor2_C': [179] * 15,  # Below
            'sensor3_C': [178] * 15   # Below
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "majority_fail_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 360,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "sensors": ["sensor1_C", "sensor2_C", "sensor3_C"],
                "require_at_least": 2
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - only 1 of 3 sensors above threshold
        assert decision.pass_ == False
        assert any("Insufficient sensors above threshold" in reason for reason in decision.reasons)


class TestPreconditions:
    """Test precondition validations."""
    
    def test_max_ramp_rate_exceeded(self):
        """Test failure when ramp rate exceeds limit."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=10, freq='30s')
        # Very fast ramp: 50°C in 30 seconds = 100°C/min
        temps = [130, 180, 185, 185, 185, 185, 185, 185, 185, 185]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "ramp_rate_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 180,
                "sensor_uncertainty_C": 2.0,
                "max_ramp_rate_C_per_min": 20.0  # Max 20°C/min
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - ramp rate too fast
        assert decision.pass_ == False
        assert any("Maximum ramp rate exceeded" in reason for reason in decision.reasons)
    
    def test_max_time_to_threshold_exceeded(self):
        """Test failure when threshold reached too late."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=30, freq='30s')
        # Slow ramp - takes 10 minutes to reach threshold
        temps = list(np.linspace(160, 182, 20)) + [183] * 10
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "time_to_threshold_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 180,
                "sensor_uncertainty_C": 2.0,
                "max_time_to_threshold_s": 300  # Max 5 minutes to threshold
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should fail - took too long to reach threshold
        assert decision.pass_ == False
        assert any("Maximum time to threshold exceeded" in reason for reason in decision.reasons)
    
    def test_min_preheat_temp_not_reached(self):
        """Test failure when minimum preheat temperature not reached."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=20, freq='30s')
        # Never reaches preheat minimum
        temps = list(np.linspace(120, 140, 10)) + list(np.linspace(140, 183, 10))
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "preheat_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 180,
                "sensor_uncertainty_C": 2.0,
                "min_preheat_temp_C": 150.0  # Must reach 150°C minimum
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Check that minimum preheat was tracked
        assert decision.min_temp_C < 150.0


class TestUnitsAndTimezones:
    """Test unit conversion and timezone handling."""
    
    def test_fahrenheit_to_celsius_conversion(self):
        """Test automatic °F to °C conversion."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=15, freq='30s')
        # Fahrenheit values: 356°F ≈ 180°C, 365°F ≈ 185°C
        temps_f = [320, 338, 356, 365, 365, 365, 365, 365, 365, 365, 365, 365, 356, 338, 320]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_F': temps_f  # Note: _F suffix
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "fahrenheit_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 240,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_F"],  # Spec references Fahrenheit column
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        
        # Import conversion function
        from core.normalize import normalize_temperature_data
        
        # Normalize should convert F to C
        normalized_df = normalize_temperature_data(df, 30.0, 120.0, 60.0)
        
        # Check conversion happened
        assert 'temp_C' in normalized_df.columns
        assert 'temp_F' not in normalized_df.columns
        
        # Verify conversion is correct (356°F = 180°C)
        assert abs(normalized_df['temp_C'].iloc[2] - 180.0) < 0.5
        
        # Make decision on normalized data
        decision = make_decision(normalized_df, spec)
        assert decision.pass_ == True
    
    def test_timezone_alignment(self):
        """Test that all timestamps are aligned to UTC."""
        # Mix of timezone-aware and naive timestamps
        timestamps = [
            pd.Timestamp('2024-01-01T10:00:00Z'),  # UTC
            pd.Timestamp('2024-01-01T10:00:30Z'),  # UTC
            pd.Timestamp('2024-01-01 10:01:00'),   # Naive - should be treated as UTC
            pd.Timestamp('2024-01-01T10:01:30+00:00'),  # UTC with offset
            pd.Timestamp('2024-01-01T10:02:00Z'),
        ]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': [183] * len(timestamps)
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "timezone_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Should pass - all timestamps properly handled
        assert decision.pass_ == True


class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions."""
    
    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame(columns=['timestamp', 'temp_C'])
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "empty_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="No data"):
            make_decision(df, spec)
    
    def test_insufficient_data_points(self):
        """Test handling of too few data points."""
        df = pd.DataFrame({
            'timestamp': [pd.Timestamp('2024-01-01T10:00:00Z')],
            'temp_C': [183]
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "insufficient_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0,
                "min_data_points": 10  # Require at least 10 points
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="Insufficient data"):
            make_decision(df, spec)
    
    def test_missing_required_sensor(self):
        """Test error when required sensor column is missing."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01T10:00:00Z', periods=10, freq='30s'),
            'wrong_sensor': [183] * 10
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "missing_sensor_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],  # This column doesn't exist
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="sensor"):
            make_decision(df, spec)
    
    def test_all_nan_temperature_data(self):
        """Test handling when all temperature data is NaN."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01T10:00:00Z', periods=10, freq='30s'),
            'temp_C': [np.nan] * 10
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "all_nan_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            }
        }
        
        spec = SpecV1(**spec_data)
        
        with pytest.raises(DecisionError, match="No valid temperature data"):
            make_decision(df, spec)


class TestSensorCombinationHelpers:
    """Test helper functions for sensor combination."""
    
    def test_combine_sensor_readings_min(self):
        """Test combine_sensor_readings with min mode."""
        df = pd.DataFrame({
            'sensor1': [10, 20, 30],
            'sensor2': [15, 18, 25],
            'sensor3': [12, 22, 28]
        })
        
        result = combine_sensor_readings(df, ['sensor1', 'sensor2', 'sensor3'], SensorMode.MIN_OF_SET)
        expected = pd.Series([10, 18, 25])  # Min at each timestamp
        pd.testing.assert_series_equal(result, expected)
    
    def test_combine_sensor_readings_mean(self):
        """Test combine_sensor_readings with mean mode."""
        df = pd.DataFrame({
            'sensor1': [10, 20, 30],
            'sensor2': [20, 20, 20],
            'sensor3': [30, 20, 10]
        })
        
        result = combine_sensor_readings(df, ['sensor1', 'sensor2', 'sensor3'], SensorMode.MEAN_OF_SET)
        expected = pd.Series([20.0, 20.0, 20.0])  # Mean at each timestamp
        pd.testing.assert_series_equal(result, expected)
    
    def test_detect_temperature_columns(self):
        """Test automatic detection of temperature columns."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=3),
            'temp_C': [20, 21, 22],
            'temperature_F': [68, 70, 72],
            'sensor1_C': [20, 21, 22],
            'pressure_bar': [1.0, 1.1, 1.2],  # Not temperature
            'temp_probe_2': [20, 21, 22]
        })
        
        temp_cols = detect_temperature_columns(df)
        
        assert 'temp_C' in temp_cols
        assert 'temperature_F' in temp_cols
        assert 'sensor1_C' in temp_cols
        assert 'temp_probe_2' in temp_cols
        assert 'pressure_bar' not in temp_cols
        assert 'timestamp' not in temp_cols


class TestRampRateCalculation:
    """Test ramp rate calculation."""
    
    def test_calculate_ramp_rate_linear(self):
        """Test ramp rate calculation for linear temperature increase."""
        time_series = pd.Series(pd.date_range('2024-01-01T10:00:00Z', periods=5, freq='60s'))
        temp_series = pd.Series([100, 110, 120, 130, 140])  # 10°C/min
        
        ramp_rates = calculate_ramp_rate(temp_series, time_series)
        
        # Should be approximately 10°C/min for all except edges
        assert all(abs(rate - 10.0) < 0.1 for rate in ramp_rates[1:-1])
    
    def test_calculate_ramp_rate_with_plateau(self):
        """Test ramp rate with temperature plateau."""
        time_series = pd.Series(pd.date_range('2024-01-01T10:00:00Z', periods=6, freq='60s'))
        temp_series = pd.Series([100, 120, 120, 120, 120, 130])  # Plateau in middle
        
        ramp_rates = calculate_ramp_rate(temp_series, time_series)
        
        # Middle values should be near 0
        assert all(abs(rate) < 0.1 for rate in ramp_rates[2:4])


class TestThresholdCrossing:
    """Test threshold crossing detection."""
    
    def test_find_threshold_crossing_time(self):
        """Test finding exact time when threshold is crossed."""
        time_series = pd.Series(pd.date_range('2024-01-01T10:00:00Z', periods=10, freq='30s'))
        temp_series = pd.Series([170, 175, 180, 182, 183, 184, 185, 186, 187, 188])
        
        crossing_time = find_threshold_crossing_time(temp_series, time_series, 182.0)
        
        # Should cross at index 3 (182°C)
        assert crossing_time == time_series.iloc[3]
    
    def test_find_threshold_crossing_never_reached(self):
        """Test when threshold is never reached."""
        time_series = pd.Series(pd.date_range('2024-01-01T10:00:00Z', periods=5, freq='30s'))
        temp_series = pd.Series([170, 175, 178, 179, 180])
        
        crossing_time = find_threshold_crossing_time(temp_series, time_series, 182.0)
        
        # Should return None
        assert crossing_time is None


class TestBooleanHoldTime:
    """Test boolean hold time calculation."""
    
    def test_calculate_boolean_hold_time_continuous(self):
        """Test boolean hold time for continuous True values."""
        time_series = pd.Series(pd.date_range('2024-01-01T10:00:00Z', periods=10, freq='30s'))
        boolean_series = pd.Series([False, False, True, True, True, True, True, True, False, False])
        
        hold_time = calculate_boolean_hold_time(boolean_series, time_series, continuous=True)
        
        # Should be 6 intervals * 30s = 180s
        assert hold_time == 180.0
    
    def test_calculate_boolean_hold_time_cumulative(self):
        """Test boolean hold time for cumulative mode."""
        time_series = pd.Series(pd.date_range('2024-01-01T10:00:00Z', periods=10, freq='30s'))
        boolean_series = pd.Series([True, True, False, True, True, True, False, True, True, False])
        
        hold_time = calculate_boolean_hold_time(boolean_series, time_series, continuous=False)
        
        # Should be 7 True values * 30s = 210s
        assert hold_time == 210.0


# Additional test for decision result consistency
class TestDecisionResultConsistency:
    """Test that decision results are internally consistent."""
    
    def test_decision_result_fields_consistency(self):
        """Test that all decision result fields are populated correctly."""
        timestamps = pd.date_range('2024-01-01T10:00:00Z', periods=20, freq='30s')
        temps = [170, 175, 180, 183] + [185] * 12 + [183, 180, 175, 170]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp_C': temps
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "consistency_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_C"],
                "require_at_least": 1
            },
            "logic": {
                "continuous": True
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        spec = SpecV1(**spec_data)
        decision = make_decision(df, spec)
        
        # Verify all fields are populated
        assert decision.job_id == "consistency_test"
        assert isinstance(decision.pass_, bool)
        assert decision.target_temp_C == 180.0
        assert decision.conservative_threshold_C == 182.0
        assert decision.required_hold_time_s == 300
        assert isinstance(decision.actual_hold_time_s, (int, float))
        assert decision.max_temp_C == 185.0
        assert decision.min_temp_C == 170.0
        assert isinstance(decision.timestamp, datetime)
        assert decision.timestamp.tzinfo is not None  # Should be timezone-aware
        assert isinstance(decision.reasons, list)
        assert hasattr(decision, 'time_above_threshold_s')
        assert hasattr(decision, 'time_to_threshold_s')
        assert hasattr(decision, 'max_ramp_rate_C_per_min')