"""
ProofKit Industry Algorithm Test Suite

Comprehensive test coverage for all industry-specific algorithms with focus on:
- Powder: threshold + hysteresis + continuous/cumulative logic
- HACCP: linear crossings (135→70≤2h, 135→41≤6h)  
- Autoclave: Fo integration (z=10°C), pressure≥15 psi requirement
- Sterile: temp + RH + gas windows
- Concrete: 24h temp 16-27°C + RH≥95%
- Cold-chain: daily percent in 2-8°C with TZ handling

Test scenarios: PASS, FAIL, BORDERLINE, MISSING_REQUIRED, INDETERMINATE
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from core.models import SpecV1, DecisionResult, SensorMode
from core.metrics_powder import (
    validate_powder_coating_cure,
    calculate_conservative_threshold,
    calculate_continuous_hold_time,
    calculate_cumulative_hold_time,
    calculate_ramp_rate,
    find_threshold_crossing_time
)
from core.metrics_haccp import (
    validate_haccp_cooling,
    validate_haccp_cooling_phases,
    find_temperature_time,
    fahrenheit_to_celsius,
    celsius_to_fahrenheit
)
from core.metrics_autoclave import (
    validate_autoclave_sterilization,
    validate_autoclave_cycle,
    calculate_fo_value,
    psi_to_kpa,
    kpa_to_psi
)
from core.metrics_sterile import (
    validate_eto_sterilization,
    validate_eto_sterilization_cycle,
    identify_eto_cycle_phases
)
from core.metrics_concrete import (
    validate_concrete_curing,
    validate_concrete_curing_conditions,
    calculate_temperature_stability
)
from core.metrics_coldchain import (
    validate_coldchain_storage,
    validate_coldchain_storage_conditions,
    identify_temperature_excursions,
    calculate_daily_compliance
)
from core.temperature_utils import DecisionError


class TestPowderAlgorithms:
    """Test powder coating cure validation algorithms."""

    @pytest.fixture
    def powder_spec_continuous(self):
        """Powder specification with continuous hold logic."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "powder_continuous_001"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,  # 10 minutes
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 1
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 300
            }
        })

    @pytest.fixture
    def powder_spec_cumulative(self):
        """Powder specification with cumulative hold logic."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "powder_cumulative_001"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,  # 10 minutes
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 1
            },
            "logic": {
                "continuous": False,
                "max_total_dips_s": 120  # Allow 2 minutes of dips
            }
        })

    def test_conservative_threshold_calculation(self):
        """Test conservative threshold = target + sensor_uncertainty."""
        assert calculate_conservative_threshold(180.0, 2.0) == 182.0
        assert calculate_conservative_threshold(160.0, 1.5) == 161.5
        assert calculate_conservative_threshold(200.0, 3.0) == 203.0

    def test_continuous_hold_time_with_hysteresis(self):
        """Test continuous hold time calculation with hysteresis."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=20, freq="30s")
        
        # Temperature crosses threshold multiple times but stays above with hysteresis
        temps = pd.Series([170, 175, 182, 184, 181, 183, 180, 182, 181, 183,
                          184, 183, 181, 182, 184, 183, 185, 184, 182, 180])
        
        hold_time_s, start_idx, end_idx = calculate_continuous_hold_time(
            temps, timestamps, 182.0, hysteresis_C=2.0
        )
        
        # Should capture longest continuous period above threshold considering hysteresis
        assert hold_time_s > 0
        assert start_idx >= 0
        assert end_idx >= start_idx

    def test_cumulative_hold_time_with_dips(self):
        """Test cumulative hold time allowing brief dips."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=20, freq="30s")
        
        # Temperature above threshold with brief dips
        temps = pd.Series([185, 184, 183, 179, 181, 183, 184, 178, 180, 183,
                          184, 182, 185, 177, 179, 183, 184, 185, 186, 184])
        
        hold_time_s, intervals = calculate_cumulative_hold_time(
            temps, timestamps, 182.0, max_total_dips_s=120
        )
        
        assert hold_time_s > 0
        assert len(intervals) > 0

    def test_ramp_rate_calculation(self):
        """Test ramp rate calculation using central differences."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=10, freq="1min")
        
        # Linear temperature rise: 10°C/min
        temps = pd.Series([20, 30, 40, 50, 60, 70, 80, 90, 100, 110])
        
        ramp_rates = calculate_ramp_rate(temps, timestamps)
        
        # Should be approximately 10°C/min (allowing for edge effects)
        valid_rates = ramp_rates[1:-1]  # Exclude edge effects
        assert abs(valid_rates.mean() - 10.0) < 1.0

    def test_time_to_threshold(self):
        """Test time to threshold measurement."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=10, freq="30s")
        
        # Temperature reaches 182°C at index 5
        temps = pd.Series([170, 174, 178, 179, 181, 182, 183, 184, 185, 186])
        
        time_to_threshold = find_threshold_crossing_time(temps, timestamps, 182.0)
        
        assert time_to_threshold is not None
        assert abs(time_to_threshold - 150.0) < 1.0  # 5 * 30s = 150s

    def test_powder_pass_continuous_logic(self, powder_spec_continuous):
        """Test powder validation PASS with continuous hold logic."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=40, freq="30s")
        
        # Good powder coat cure: ramp to target, hold continuously
        temps = [20 + i * 4 for i in range(10)] + [183, 184, 185] * 10 + [180, 175, 170]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temps,
            "pmt_sensor_2": [t + np.random.normal(0, 0.5) for t in temps]
        })
        
        result = validate_powder_coating_cure(df, powder_spec_continuous)
        
        assert result.pass_ is True
        assert result.status == "PASS"
        assert result.conservative_threshold_C == 182.0
        assert result.actual_hold_time_s >= 600
        assert any("Continuous hold time requirement met" in reason for reason in result.reasons)

    def test_powder_pass_cumulative_logic(self, powder_spec_cumulative):
        """Test powder validation PASS with cumulative hold logic."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=40, freq="30s")
        
        # Cumulative cure: multiple periods above threshold with brief dips
        temps = ([20 + i * 4 for i in range(10)] + 
                [184, 185, 181, 179, 183, 184, 185, 180, 178, 182] +
                [184, 185, 186, 184, 183, 185, 186, 187, 185, 184] +
                [180, 175, 170] * 3)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temps,
            "pmt_sensor_2": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_powder_coating_cure(df, powder_spec_cumulative)
        
        assert result.pass_ is True
        assert result.status == "PASS"
        assert result.actual_hold_time_s >= 600
        assert any("Cumulative hold time requirement met" in reason for reason in result.reasons)

    def test_powder_fail_insufficient_hold(self, powder_spec_continuous):
        """Test powder validation FAIL due to insufficient hold time."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=20, freq="30s")
        
        # Short hold time
        temps = [20 + i * 8 for i in range(10)] + [183, 184, 185, 184, 183] + [175] * 5
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temps,
            "pmt_sensor_2": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_powder_coating_cure(df, powder_spec_continuous)
        
        assert result.pass_ is False
        assert result.status == "FAIL"
        assert result.actual_hold_time_s < 600
        assert any("Insufficient continuous hold time" in reason for reason in result.reasons)

    def test_powder_fail_threshold_not_reached(self, powder_spec_continuous):
        """Test powder validation FAIL when threshold never reached."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=30, freq="30s")
        
        # Temperature never reaches conservative threshold (182°C)
        temps = [20 + i * 5 for i in range(15)] + [175, 178, 179, 180, 181] * 3
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temps,
            "pmt_sensor_2": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_powder_coating_cure(df, powder_spec_continuous)
        
        assert result.pass_ is False
        assert result.status == "FAIL"
        assert result.actual_hold_time_s == 0.0
        assert any("never reached conservative threshold" in reason for reason in result.reasons)

    def test_powder_borderline_threshold_crossing(self, powder_spec_continuous):
        """Test powder validation BORDERLINE - just reaches threshold."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=35, freq="30s")
        
        # Just reaches 182°C and holds minimally
        temps = ([20 + i * 6 for i in range(15)] + 
                [182.0, 182.1, 182.0, 182.2, 182.0] * 4)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temps,
            "pmt_sensor_2": [t + np.random.normal(0, 0.2) for t in temps]
        })
        
        result = validate_powder_coating_cure(df, powder_spec_continuous)
        
        # Should pass if hold time is sufficient, otherwise fail
        if result.actual_hold_time_s >= 600:
            assert result.pass_ is True
        else:
            assert result.pass_ is False

    def test_powder_fail_excessive_ramp_rate(self, powder_spec_continuous):
        """Test powder validation FAIL due to excessive ramp rate."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=20, freq="30s")
        
        # Very fast temperature rise (>10°C/min)
        temps = [20, 40, 80, 120, 160, 200] + [185] * 14
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": temps,
            "pmt_sensor_2": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_powder_coating_cure(df, powder_spec_continuous)
        
        assert result.pass_ is False
        assert any("Ramp rate too high" in reason for reason in result.reasons)

    def test_powder_missing_required_sensors(self):
        """Test powder validation INDETERMINATE when required sensors missing."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=20, freq="30s")
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "other_sensor": [100] * 20  # No temperature sensors
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "missing_sensors_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            "sensor_selection": {
                "require_at_least": 2  # Requires 2 sensors but none available
            }
        })
        
        result = validate_powder_coating_cure(df, spec)
        
        assert result.pass_ is False
        assert result.status == "INDETERMINATE"
        assert any("No temperature sensors detected" in reason for reason in result.reasons)


class TestHACCPAlgorithms:
    """Test HACCP cooling validation algorithms."""

    @pytest.fixture
    def haccp_spec(self):
        """HACCP cooling specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "haccp",
            "job": {"job_id": "haccp_cooling_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,  # 41°F target
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            }
        })

    def test_temperature_conversion_functions(self):
        """Test Fahrenheit/Celsius conversion accuracy."""
        # Test HACCP critical temperatures
        assert abs(fahrenheit_to_celsius(135.0) - 57.2222) < 0.01
        assert abs(fahrenheit_to_celsius(70.0) - 21.1111) < 0.01
        assert abs(fahrenheit_to_celsius(41.0) - 5.0) < 0.01
        
        assert abs(celsius_to_fahrenheit(57.2222) - 135.0) < 0.01
        assert abs(celsius_to_fahrenheit(21.1111) - 70.0) < 0.01
        assert abs(celsius_to_fahrenheit(5.0) - 41.0) < 0.01

    def test_linear_crossing_detection(self):
        """Test linear temperature crossing detection."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=20, freq="15min")
        
        # Cooling from 57°C to 5°C
        temps = pd.Series([57.2, 55, 52, 48, 45, 40, 35, 30, 25, 21.1,
                          18, 15, 12, 10, 8, 6, 5.0, 5, 5, 5])
        
        # Find time to 70°F (21.1°C)
        time_to_70f = find_temperature_time(temps, timestamps, 21.1111, 'cooling')
        assert time_to_70f is not None
        
        # Find time to 41°F (5°C)  
        time_to_41f = find_temperature_time(temps, timestamps, 5.0, 'cooling')
        assert time_to_41f is not None
        assert time_to_41f > time_to_70f

    def test_haccp_pass_proper_cooling(self, haccp_spec):
        """Test HACCP PASS - proper 135→70≤2h, 135→41≤6h."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=25, freq="15min")
        
        # Proper cooling: 135°F to 70°F in 1.5h, to 41°F in 4h total
        temps = [57.2, 54, 51, 47, 43, 38, 33, 28, 24, 21.1,  # Reach 70°F at 2.25h
                18, 15, 12, 10, 8, 6, 5.0,  # Reach 41°F at 4h
                5, 5, 5, 4.5, 4.5, 4.5, 4.5, 4.5]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps,
            "temp_backup": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is True
        assert any("Phase 1 cooling" in reason for reason in result.reasons)
        assert any("Phase 2 cooling" in reason for reason in result.reasons)
        assert any("HACCP cooling requirements met" in reason for reason in result.reasons)

    def test_haccp_fail_phase1_too_slow(self, haccp_spec):
        """Test HACCP FAIL - Phase 1 (135→70°F) takes >2h."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=30, freq="15min")
        
        # Slow Phase 1: Takes 3+ hours to reach 70°F
        temps = ([57.2, 56, 55, 54, 53, 52, 50, 48, 46, 44,
                 42, 40, 38, 35, 33, 30, 28, 25, 23, 21.1] +  # Reach 70°F at 4.75h (too slow)
                [19, 17, 15, 12, 10, 8, 6, 5, 5, 5])
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps,
            "temp_backup": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is False
        assert any("Phase 1 cooling took" in reason and "2h limit" in reason 
                  for reason in result.reasons)

    def test_haccp_fail_phase2_too_slow(self, haccp_spec):
        """Test HACCP FAIL - Phase 2 (135→41°F) takes >6h."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=35, freq="20min")
        
        # Phase 1 OK, but Phase 2 too slow (8+ hours total)
        temps = ([57.2, 54, 50, 45, 40, 35, 30, 25, 21.1] +  # Phase 1 OK (2.67h)
                [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10,
                 9, 8, 7, 6, 5.5, 5.2, 5.0] + [5] * 8)  # Phase 2 at 10+ hours
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps,
            "temp_backup": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is False
        assert any("Phase 2 cooling took" in reason and "6h limit" in reason 
                  for reason in result.reasons)

    def test_haccp_borderline_timing(self, haccp_spec):
        """Test HACCP BORDERLINE - exactly at time limits."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=25, freq="15min")
        
        # Exactly at limits: 70°F at 2h, 41°F at 6h
        temps = ([57.2, 55, 52, 48, 44, 40, 35, 30, 21.1] +  # 70°F at exactly 2h
                [19, 17, 15, 13, 11, 9, 7, 5.0] +  # 41°F at exactly 4.25h (within 6h)
                [5, 5, 5, 5, 5, 5, 5, 5])
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps,
            "temp_backup": [t + np.random.normal(0, 0.2) for t in temps]
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is True  # Should pass at limits

    def test_haccp_fail_invalid_start_temp(self, haccp_spec):
        """Test HACCP FAIL - starting temperature below 135°F."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=20, freq="15min")
        
        # Start at 120°F (48.9°C) - below 135°F requirement
        temps = [48.9, 46, 43, 40, 37, 34, 31, 28, 25, 22,
                19, 16, 13, 10, 8, 6, 5, 5, 5, 5]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps,
            "temp_backup": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is False
        assert any("135°F" in reason for reason in result.reasons)

    def test_haccp_fail_heating_detected(self, haccp_spec):
        """Test HACCP FAIL - temperature increases during cooling."""
        timestamps = pd.date_range("2024-01-01T12:00:00Z", periods=15, freq="15min")
        
        # Temperature increases (heating) during process
        temps = [57.2, 55, 53, 58, 62, 55, 50, 45, 40, 35,
                30, 25, 20, 15, 10]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps,
            "temp_backup": [t + np.random.normal(0, 0.3) for t in temps]
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is False
        assert any("heating detected" in reason for reason in result.reasons)

    def test_haccp_missing_required_data(self):
        """Test HACCP INDETERMINATE when critical data missing."""
        # Empty DataFrame
        df = pd.DataFrame()
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "haccp",
            "job": {"job_id": "missing_data_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            }
        })
        
        with pytest.raises(DecisionError):
            validate_haccp_cooling(df, spec)


class TestAutoclaveAlgorithms:
    """Test autoclave sterilization validation algorithms."""

    @pytest.fixture
    def autoclave_spec(self):
        """Autoclave sterilization specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "autoclave",
            "job": {"job_id": "autoclave_sterilization_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 121.0,
                "hold_time_s": 900,  # 15 minutes
                "sensor_uncertainty_C": 0.5
            },
            "parameter_requirements": {
                "require_pressure": True,
                "require_fo": True
            }
        })

    def test_fo_value_integration(self):
        """Test Fo value integration with z=10°C."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=16, freq="1min")
        
        # 121°C for 15 minutes should give Fo ≈ 15
        temps = pd.Series([121.0] * 16)
        fo_value = calculate_fo_value(temps, timestamps, z_value=10.0, reference_temp_c=121.0)
        
        assert 14.0 <= fo_value <= 16.0

        # Higher temperature should give higher Fo
        temps_high = pd.Series([125.0] * 16)
        fo_high = calculate_fo_value(temps_high, timestamps)
        assert fo_high > fo_value

        # Lower temperature should give lower Fo
        temps_low = pd.Series([115.0] * 16)
        fo_low = calculate_fo_value(temps_low, timestamps)
        assert fo_low < fo_value

    def test_pressure_requirement_15psi(self):
        """Test pressure ≥15 psi requirement."""
        assert abs(psi_to_kpa(15.0) - 103.421) < 0.1
        assert abs(kpa_to_psi(103.421) - 15.0) < 0.1

    def test_autoclave_pass_all_requirements(self, autoclave_spec):
        """Test autoclave PASS - Fo≥12, pressure≥15psi, temp 119-123°C."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=120, freq="30s")
        
        # Proper sterilization cycle
        temp_profile = ([20 + i * 5 for i in range(20)] +  # Ramp to 121°C
                       [121.0 + np.random.normal(0, 0.5) for _ in range(60)] +  # Hold 30min
                       [121 - i * 2 for i in range(40)])  # Cool down
        
        pressure_profile = ([101.3 + i * 1 for i in range(20)] +  # Ramp pressure
                           [105.0 + np.random.normal(0, 1.0) for _ in range(60)] +  # Hold >15psi
                           [105 - i * 1 for i in range(40)])  # Release pressure
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "pressure_1": pressure_profile,
            "pressure_2": [p + np.random.normal(0, 0.5) for p in pressure_profile]
        })
        
        result = validate_autoclave_sterilization(df, autoclave_spec)
        
        assert result.pass_ is True
        assert result.status == "PASS"
        assert result.target_temp_C == 121.0
        assert result.conservative_threshold_C == 119.0
        assert any("Fo value" in reason for reason in result.reasons)
        assert any("Pressure maintained" in reason for reason in result.reasons)

    def test_autoclave_fail_insufficient_fo(self, autoclave_spec):
        """Test autoclave FAIL - Fo value <12."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=60, freq="30s")
        
        # Low temperature - insufficient Fo value
        temp_profile = ([20 + i * 4 for i in range(15)] +  # Ramp to 115°C only
                       [115.0 + np.random.normal(0, 0.5) for _ in range(30)] +  # Hold at low temp
                       [115 - i * 2 for i in range(15)])
        
        pressure_profile = [105.0] * 60  # Good pressure
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "pressure_1": pressure_profile,
            "pressure_2": [p + np.random.normal(0, 0.5) for p in pressure_profile]
        })
        
        result = validate_autoclave_sterilization(df, autoclave_spec)
        
        assert result.pass_ is False
        assert any("Fo value" in reason and "12" in reason for reason in result.reasons)

    def test_autoclave_fail_insufficient_pressure(self, autoclave_spec):
        """Test autoclave FAIL - pressure <15 psi during sterilization."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=80, freq="30s")
        
        # Good temperature but poor pressure
        temp_profile = ([20 + i * 5 for i in range(20)] +
                       [121.0 + np.random.normal(0, 0.5) for _ in range(40)] +
                       [121 - i * 2 for i in range(20)])
        
        pressure_profile = ([101.3 + i * 0.5 for i in range(20)] +
                           [95.0 + np.random.normal(0, 2.0) for _ in range(40)] +  # <15 psi
                           [95 - i * 1 for i in range(20)])
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "pressure_1": pressure_profile,
            "pressure_2": [p + np.random.normal(0, 0.5) for p in pressure_profile]
        })
        
        result = validate_autoclave_sterilization(df, autoclave_spec)
        
        assert result.pass_ is False
        assert any("Pressure" in reason and "psi" in reason for reason in result.reasons)

    def test_autoclave_fail_temperature_range(self, autoclave_spec):
        """Test autoclave FAIL - temperature outside 119-123°C range."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=60, freq="30s")
        
        # Temperature too high (>123°C)
        temp_profile = [130.0] * 60
        pressure_profile = [105.0] * 60
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "pressure_1": pressure_profile,
            "pressure_2": [p + np.random.normal(0, 0.5) for p in pressure_profile]
        })
        
        result = validate_autoclave_sterilization(df, autoclave_spec)
        
        assert result.pass_ is False
        assert any("123°C limit" in reason for reason in result.reasons)

    def test_autoclave_borderline_fo_value(self, autoclave_spec):
        """Test autoclave BORDERLINE - Fo value exactly at 12."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=80, freq="30s")
        
        # Temperature/time combination to give Fo ≈ 12
        temp_profile = ([20 + i * 5 for i in range(20)] +
                       [119.5 + np.random.normal(0, 0.3) for _ in range(40)] +  # Just above min
                       [119 - i * 2 for i in range(20)])
        
        pressure_profile = [105.0] * 80
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "pressure_1": pressure_profile,
            "pressure_2": [p + np.random.normal(0, 0.5) for p in pressure_profile]
        })
        
        result = validate_autoclave_sterilization(df, autoclave_spec)
        
        # Should pass if Fo ≥ 12, otherwise fail
        if "Fo value" in str(result.reasons) and "12" in str(result.reasons):
            assert result.pass_ is False
        else:
            assert result.pass_ is True

    def test_autoclave_missing_required_pressure(self):
        """Test autoclave INDETERMINATE when required pressure data missing."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=40, freq="30s")
        
        # Only temperature data, no pressure
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [121.0] * 40,
            "temp_2": [121.5] * 40
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "autoclave",
            "job": {"job_id": "missing_pressure_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 121.0,
                "hold_time_s": 900,
                "sensor_uncertainty_C": 0.5
            },
            "parameter_requirements": {
                "require_pressure": True  # Pressure required but missing
            }
        })
        
        result = validate_autoclave_sterilization(df, spec)
        
        assert result.status == "INDETERMINATE"
        assert any("Pressure data required" in reason for reason in result.reasons)


class TestSterileAlgorithms:
    """Test sterile (EtO) sterilization validation algorithms."""

    @pytest.fixture
    def sterile_spec(self):
        """Sterile EtO sterilization specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "sterile_eto_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 55.0,
                "hold_time_s": 7200,  # 2 hours
                "sensor_uncertainty_C": 1.0
            },
            "parameter_requirements": {
                "require_humidity": True,
                "require_gas_concentration": True
            }
        })

    def test_eto_pass_temp_rh_gas_windows(self, sterile_spec):
        """Test sterile PASS - temp 50-60°C, RH 45-85%, gas maintained."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=180, freq="5min")
        
        # Temperature: preconditioning → sterilization → aeration
        temp_profile = ([20 + i * 1.5 for i in range(30)] +  # Precondition to 55°C
                       [55.0 + np.random.normal(0, 1.0) for _ in range(100)] +  # Hold 55°C
                       [55 - i * 0.8 for i in range(50)])  # Cool down
        
        # Humidity: 45-85% RH during sterilization
        humidity_profile = ([30 + i * 1.5 for i in range(30)] +
                           [70.0 + np.random.normal(0, 5.0) for _ in range(100)] +
                           [70 - i * 0.5 for i in range(50)])
        
        # Gas: injection → hold → evacuation
        gas_profile = ([0.0] * 30 +
                      [800.0 + np.random.normal(0, 50.0) for _ in range(100)] +
                      [800 * (1 - i/50) for i in range(50)])
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.5) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "eto_concentration": gas_profile
        })
        
        result = validate_eto_sterilization(df, sterile_spec)
        
        assert result.pass_ is True
        assert result.status == "PASS"
        assert result.target_temp_C == 55.0
        assert result.conservative_threshold_C == 50.0
        assert any("sterilization requirements met" in reason for reason in result.reasons)

    def test_sterile_fail_temperature_too_low(self, sterile_spec):
        """Test sterile FAIL - temperature below 50°C minimum."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=100, freq="5min")
        
        # Temperature too low (45°C)
        temp_profile = [45.0 + np.random.normal(0, 2.0) for _ in range(100)]
        humidity_profile = [70.0] * 100
        gas_profile = [800.0] * 100
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "eto_concentration": gas_profile
        })
        
        result = validate_eto_sterilization(df, sterile_spec)
        
        assert result.pass_ is False
        assert any("temperature" in reason.lower() for reason in result.reasons)

    def test_sterile_fail_temperature_too_high(self, sterile_spec):
        """Test sterile FAIL - temperature above 60°C maximum."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=80, freq="5min")
        
        # Temperature too high (70°C)
        temp_profile = [70.0] * 80
        humidity_profile = [70.0] * 80
        gas_profile = [800.0] * 80
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "eto_concentration": gas_profile
        })
        
        result = validate_eto_sterilization(df, sterile_spec)
        
        assert result.pass_ is False
        assert any("60°C limit" in reason for reason in result.reasons)

    def test_sterile_fail_humidity_out_of_range(self, sterile_spec):
        """Test sterile FAIL - humidity outside 45-85% RH range."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=80, freq="5min")
        
        temp_profile = [55.0] * 80
        humidity_profile = [30.0] * 80  # Too low (should be 45-85%)
        gas_profile = [800.0] * 80
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "eto_concentration": gas_profile
        })
        
        result = validate_eto_sterilization(df, sterile_spec)
        
        assert result.pass_ is False
        assert any("Humidity" in reason and "range" in reason for reason in result.reasons)

    def test_sterile_borderline_sterilization_time(self, sterile_spec):
        """Test sterile BORDERLINE - exactly at minimum sterilization time."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=145, freq="5min")
        
        # Exactly 2 hours sterilization time
        temp_profile = ([20 + i * 1.5 for i in range(25)] +  # Precondition
                       [55.0] * 24 +  # Exactly 2 hours at temp
                       [55 - i for i in range(96)])  # Cool down quickly
        
        humidity_profile = ([45 + i for i in range(25)] + [70.0] * 120)
        gas_profile = ([0] * 25 + [800.0] * 24 + [400, 200, 100] + [50] * 93)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "humidity_1": humidity_profile,
            "eto_concentration": gas_profile
        })
        
        result = validate_eto_sterilization(df, sterile_spec)
        
        # Should pass if sterilization time ≥ 2 hours
        if result.actual_hold_time_s >= 7200:
            assert result.pass_ is True
        else:
            assert result.pass_ is False

    def test_sterile_missing_required_humidity(self):
        """Test sterile INDETERMINATE when required humidity data missing."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=80, freq="5min")
        
        # Missing humidity data
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [55.0] * 80,
            "temp_2": [55.5] * 80,
            "temp_3": [54.5] * 80,
            "eto_concentration": [800.0] * 80
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "missing_humidity_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 55.0,
                "hold_time_s": 7200,
                "sensor_uncertainty_C": 1.0
            },
            "parameter_requirements": {
                "require_humidity": True  # Required but missing
            }
        })
        
        result = validate_eto_sterilization(df, spec)
        
        assert result.status == "INDETERMINATE"
        assert any("Humidity data required" in reason for reason in result.reasons)

    def test_sterile_missing_required_gas(self):
        """Test sterile INDETERMINATE when required gas data missing."""
        timestamps = pd.date_range("2024-01-01T08:00:00Z", periods=80, freq="5min")
        
        # Missing gas data
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [55.0] * 80,
            "temp_2": [55.5] * 80,
            "temp_3": [54.5] * 80,
            "humidity_1": [70.0] * 80
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "missing_gas_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 55.0,
                "hold_time_s": 7200,
                "sensor_uncertainty_C": 1.0
            },
            "parameter_requirements": {
                "require_gas_concentration": True  # Required but missing
            }
        })
        
        result = validate_eto_sterilization(df, spec)
        
        assert result.status == "INDETERMINATE"
        assert any("EtO gas concentration data required" in reason for reason in result.reasons)


class TestConcreteAlgorithms:
    """Test concrete curing validation algorithms."""

    @pytest.fixture
    def concrete_spec(self):
        """Concrete curing specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "concrete_curing_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 21.5,  # 70°F optimal
                "hold_time_s": 86400,   # 24 hours
                "sensor_uncertainty_C": 0.5
            },
            "parameter_requirements": {
                "require_humidity": True
            }
        })

    def test_concrete_pass_24h_temp_rh_requirements(self, concrete_spec):
        """Test concrete PASS - 24h temp 16-27°C + RH≥95%."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=200, freq="30min")
        
        # Stable temperature 20-22°C for 100+ hours
        temp_profile = [21.0 + np.random.normal(0, 1.0) for _ in range(200)]
        temp_profile = [max(16.5, min(26.5, t)) for t in temp_profile]  # Keep in range
        
        # Humidity >95%
        humidity_profile = [96.0 + np.random.normal(0, 2.0) for _ in range(200)]
        humidity_profile = [max(95.0, min(99.0, h)) for h in humidity_profile]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 1.0) for h in humidity_profile]
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is True
        assert result.status == "PASS"
        assert result.target_temp_C == 21.5
        assert result.conservative_threshold_C == 16.0
        assert any("curing requirements met" in reason for reason in result.reasons)

    def test_concrete_fail_temperature_too_cold(self, concrete_spec):
        """Test concrete FAIL - temperature below 16°C."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=100, freq="30min")
        
        # Temperature too cold
        temp_profile = [12.0 + np.random.normal(0, 2.0) for _ in range(100)]
        humidity_profile = [96.0] * 100
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 1.0) for h in humidity_profile]
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is False
        assert any("16°C" in reason for reason in result.reasons)

    def test_concrete_fail_temperature_too_hot(self, concrete_spec):
        """Test concrete FAIL - temperature above 27°C."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=80, freq="30min")
        
        # Temperature too hot
        temp_profile = [35.0] * 80
        humidity_profile = [96.0] * 80
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 1.0) for h in humidity_profile]
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is False
        assert any("27°C" in reason for reason in result.reasons)

    def test_concrete_fail_humidity_too_low(self, concrete_spec):
        """Test concrete FAIL - humidity below 95%."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=100, freq="30min")
        
        temp_profile = [21.0] * 100  # Good temperature
        humidity_profile = [80.0] * 100  # Too low humidity
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 1.0) for h in humidity_profile]
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is False
        assert any("95%RH" in reason for reason in result.reasons)

    def test_concrete_fail_rapid_temperature_changes(self, concrete_spec):
        """Test concrete FAIL - rapid temperature changes >5°C/hour."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=20, freq="30min")
        
        # Rapid temperature swings
        temp_profile = [20.0, 30.0, 15.0, 25.0, 10.0] * 4
        humidity_profile = [96.0] * 20
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 1.0) for h in humidity_profile]
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is False
        assert any("change rate" in reason for reason in result.reasons)

    def test_concrete_borderline_24h_monitoring(self, concrete_spec):
        """Test concrete BORDERLINE - exactly 24h monitoring period."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=49, freq="30min")
        
        # Exactly 24 hours of data
        temp_profile = [21.0 + np.random.normal(0, 0.5) for _ in range(49)]
        temp_profile = [max(16.5, min(26.5, t)) for t in temp_profile]
        
        humidity_profile = [96.0] * 49
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 0.5) for h in humidity_profile]
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        # Should pass if conditions met for critical 24h period
        if result.pass_:
            assert any("24h" in reason or "Critical" in reason for reason in result.reasons)

    def test_concrete_missing_required_humidity(self):
        """Test concrete INDETERMINATE when required humidity data missing."""
        timestamps = pd.date_range("2024-01-01T06:00:00Z", periods=80, freq="30min")
        
        # Missing humidity data
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [21.0] * 80,
            "temp_2": [21.5] * 80
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "missing_humidity_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 21.5,
                "hold_time_s": 86400,
                "sensor_uncertainty_C": 0.5
            },
            "parameter_requirements": {
                "require_humidity": True  # Required but missing
            }
        })
        
        result = validate_concrete_curing(df, spec)
        
        assert result.status == "INDETERMINATE"
        assert any("Humidity data required" in reason for reason in result.reasons)


class TestColdChainAlgorithms:
    """Test cold chain storage validation algorithms."""

    @pytest.fixture
    def coldchain_spec(self):
        """Cold chain storage specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "coldchain_storage_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 86400,  # 24 hours
                "sensor_uncertainty_C": 0.5
            }
        })

    def test_coldchain_pass_daily_95_percent_in_range(self, coldchain_spec):
        """Test cold chain PASS - ≥95% samples/day in 2-8°C."""
        timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=300, freq="5min")
        
        # 98% of temperatures in 2-8°C range
        temp_profile = [5.0 + np.random.normal(0, 1.0) for _ in range(300)]
        
        # Ensure 98% compliance with occasional brief excursions
        for i in range(len(temp_profile)):
            if i % 50 == 0:  # 2% brief excursions
                temp_profile[i] = 9.0 if np.random.random() > 0.5 else 1.5
            else:
                temp_profile[i] = max(2.5, min(7.5, temp_profile[i]))
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        assert result.pass_ is True
        assert result.status == "PASS"
        assert result.target_temp_C == 5.0
        assert result.conservative_threshold_C == 2.0
        assert any("cold chain" in reason.lower() for reason in result.reasons)

    def test_coldchain_fail_too_many_excursions(self, coldchain_spec):
        """Test cold chain FAIL - <95% samples in range."""
        timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=200, freq="5min")
        
        # Only 70% in range (too many excursions)
        temp_profile = []
        for i in range(200):
            if i % 10 < 3:  # 30% outside range
                temp_profile.append(12.0 + np.random.normal(0, 2.0))
            else:
                temp_profile.append(5.0 + np.random.normal(0, 1.0))
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        assert result.pass_ is False
        assert any("compliance" in reason.lower() or "excursion" in reason.lower() 
                  for reason in result.reasons)

    def test_coldchain_fail_critical_freezing(self, coldchain_spec):
        """Test cold chain FAIL - critical freezing risk."""
        timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=60, freq="5min")
        
        # Temperature drops to freezing (-5°C)
        temp_profile = [-5.0] * 60
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile]
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        assert result.pass_ is False
        assert any("Critical low temperature" in reason for reason in result.reasons)

    def test_coldchain_fail_critical_high_temperature(self, coldchain_spec):
        """Test cold chain FAIL - critical high temperature abuse."""
        timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=60, freq="5min")
        
        # Temperature too high (20°C - product efficacy compromised)
        temp_profile = [20.0] * 60
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile]
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        assert result.pass_ is False
        assert any("Critical high temperature" in reason for reason in result.reasons)

    def test_coldchain_borderline_95_percent_compliance(self, coldchain_spec):
        """Test cold chain BORDERLINE - exactly 95% compliance."""
        timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=100, freq="5min")
        
        # Exactly 95% in range
        temp_profile = []
        for i in range(100):
            if i < 5:  # 5% out of range
                temp_profile.append(9.0)
            else:  # 95% in range
                temp_profile.append(5.0 + np.random.normal(0, 0.8))
                temp_profile[-1] = max(2.2, min(7.8, temp_profile[-1]))
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile]
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        # Should pass at exactly 95% compliance
        assert result.pass_ is True

    def test_coldchain_timezone_handling(self, coldchain_spec):
        """Test cold chain with timezone-aware timestamps."""
        # Test with different timezone
        timestamps = pd.date_range(
            "2024-01-01T00:00:00-05:00", periods=200, freq="5min", tz="US/Eastern"
        )
        
        temp_profile = [5.0 + np.random.normal(0, 0.8) for _ in range(200)]
        temp_profile = [max(2.5, min(7.5, t)) for t in temp_profile]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile]
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        # Should handle timezone properly
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True

    def test_coldchain_missing_required_sensors(self):
        """Test cold chain INDETERMINATE when no temperature sensors found."""
        timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=50, freq="5min")
        
        # No temperature columns
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pressure_1": [100.0] * 50,
            "humidity_1": [60.0] * 50
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "no_temp_sensors_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 86400,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        with pytest.raises(DecisionError):
            validate_coldchain_storage(df, spec)


class TestIndustryAlgorithmEdgeCases:
    """Test edge cases and error conditions across all industry algorithms."""

    def test_empty_dataframe_handling(self):
        """Test that all industry algorithms handle empty DataFrames."""
        df = pd.DataFrame()
        
        industries = ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]
        
        for industry in industries:
            spec = SpecV1(**{
                "version": "1.0",
                "industry": industry,
                "job": {"job_id": f"empty_df_{industry}"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 50.0,
                    "hold_time_s": 3600,
                    "sensor_uncertainty_C": 1.0
                }
            })
            
            # All should raise DecisionError for empty DataFrame
            with pytest.raises(DecisionError):
                if industry == "powder":
                    validate_powder_coating_cure(df, spec)
                elif industry == "haccp":
                    validate_haccp_cooling(df, spec)
                elif industry == "autoclave":
                    validate_autoclave_sterilization(df, spec)
                elif industry == "sterile":
                    validate_eto_sterilization(df, spec)
                elif industry == "concrete":
                    validate_concrete_curing(df, spec)
                elif industry == "coldchain":
                    validate_coldchain_storage(df, spec)

    def test_insufficient_data_points(self):
        """Test handling of insufficient data points."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=1, freq="30s")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [20.0]
        })
        
        industries = ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]
        
        for industry in industries:
            spec = SpecV1(**{
                "version": "1.0",
                "industry": industry,
                "job": {"job_id": f"insufficient_data_{industry}"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 50.0,
                    "hold_time_s": 3600,
                    "sensor_uncertainty_C": 1.0
                }
            })
            
            # All should raise DecisionError for insufficient data
            with pytest.raises(DecisionError):
                if industry == "powder":
                    validate_powder_coating_cure(df, spec)
                elif industry == "haccp":
                    validate_haccp_cooling(df, spec)
                elif industry == "autoclave":
                    validate_autoclave_sterilization(df, spec)
                elif industry == "sterile":
                    validate_eto_sterilization(df, spec)
                elif industry == "concrete":
                    validate_concrete_curing(df, spec)
                elif industry == "coldchain":
                    validate_coldchain_storage(df, spec)

    def test_invalid_industry_validation(self):
        """Test that each algorithm validates industry field correctly."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=10, freq="30s")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [20.0] * 10,
            "temp_2": [21.0] * 10
        })
        
        # Test each engine with wrong industry
        test_cases = [
            ("powder", "haccp", validate_powder_coating_cure),
            ("haccp", "powder", validate_haccp_cooling),
            ("autoclave", "sterile", validate_autoclave_sterilization),
            ("sterile", "concrete", validate_eto_sterilization),
            ("concrete", "coldchain", validate_concrete_curing),
            ("coldchain", "autoclave", validate_coldchain_storage)
        ]
        
        for correct_industry, wrong_industry, validation_func in test_cases:
            spec = SpecV1(**{
                "version": "1.0",
                "industry": wrong_industry,  # Wrong industry
                "job": {"job_id": f"wrong_industry_{correct_industry}"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 50.0,
                    "hold_time_s": 3600,
                    "sensor_uncertainty_C": 1.0
                }
            })
            
            with pytest.raises(DecisionError):
                validation_func(df, spec)

    def test_missing_timestamp_column(self):
        """Test handling of missing timestamp column."""
        # DataFrame without timestamp column
        df = pd.DataFrame({
            "temp_1": [20.0, 21.0, 22.0],
            "temp_2": [20.5, 21.5, 22.5]
        })
        
        industries = ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]
        
        for industry in industries:
            spec = SpecV1(**{
                "version": "1.0",
                "industry": industry,
                "job": {"job_id": f"no_timestamp_{industry}"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 50.0,
                    "hold_time_s": 3600,
                    "sensor_uncertainty_C": 1.0
                }
            })
            
            # All should raise DecisionError for missing timestamp
            with pytest.raises(DecisionError):
                if industry == "powder":
                    validate_powder_coating_cure(df, spec)
                elif industry == "haccp":
                    validate_haccp_cooling(df, spec)
                elif industry == "autoclave":
                    validate_autoclave_sterilization(df, spec)
                elif industry == "sterile":
                    validate_eto_sterilization(df, spec)
                elif industry == "concrete":
                    validate_concrete_curing(df, spec)
                elif industry == "coldchain":
                    validate_coldchain_storage(df, spec)

    def test_all_nan_sensor_values(self):
        """Test handling of all-NaN sensor values (sensor failure)."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=20, freq="30s")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [np.nan] * 20,  # Failed sensor
            "temp_2": [np.nan] * 20   # Failed sensor
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "sensor_failure_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            }
        })
        
        result = validate_powder_coating_cure(df, spec)
        
        assert result.pass_ is False
        assert result.status == "INDETERMINATE"
        assert any("sensor" in reason.lower() and "failed" in reason.lower() 
                  for reason in result.reasons)

    def test_decision_result_consistency(self):
        """Test that all industry algorithms return consistent DecisionResult objects."""
        timestamps = pd.date_range("2024-01-01T10:00:00Z", periods=50, freq="30s")
        
        # Generic test data with all sensor types
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [20.0 + i * 0.5 for i in range(50)],
            "temp_2": [21.0 + i * 0.5 for i in range(50)],
            "temp_3": [19.0 + i * 0.5 for i in range(50)],
            "humidity_1": [60.0] * 50,
            "pressure_1": [100.0] * 50,
            "eto_concentration": [100.0] * 50,
            "pmt_sensor_1": [150.0 + i * 2 for i in range(50)]
        })
        
        validation_functions = [
            ("powder", validate_powder_coating_cure),
            ("haccp", validate_haccp_cooling),
            ("autoclave", validate_autoclave_sterilization),
            ("sterile", validate_eto_sterilization),
            ("concrete", validate_concrete_curing),
            ("coldchain", validate_coldchain_storage)
        ]
        
        for industry, validation_func in validation_functions:
            spec = SpecV1(**{
                "version": "1.0",
                "industry": industry,
                "job": {"job_id": f"consistency_{industry}"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 50.0,
                    "hold_time_s": 3600,
                    "sensor_uncertainty_C": 1.0
                }
            })
            
            result = validation_func(df, spec)
            
            # Verify DecisionResult structure
            assert isinstance(result, DecisionResult)
            assert hasattr(result, 'pass_') and isinstance(result.pass_, bool)
            assert hasattr(result, 'status') and isinstance(result.status, str)
            assert hasattr(result, 'job_id') and isinstance(result.job_id, str)
            assert hasattr(result, 'target_temp_C') and isinstance(result.target_temp_C, float)
            assert hasattr(result, 'conservative_threshold_C') and isinstance(result.conservative_threshold_C, float)
            assert hasattr(result, 'actual_hold_time_s') and isinstance(result.actual_hold_time_s, float)
            assert hasattr(result, 'required_hold_time_s') and isinstance(result.required_hold_time_s, (int, float))
            assert hasattr(result, 'max_temp_C') and isinstance(result.max_temp_C, float)
            assert hasattr(result, 'min_temp_C') and isinstance(result.min_temp_C, float)
            assert hasattr(result, 'reasons') and isinstance(result.reasons, list)
            assert hasattr(result, 'warnings') and isinstance(result.warnings, list)
            
            # Verify reasonable values
            assert result.target_temp_C > 0
            assert result.conservative_threshold_C > 0
            assert result.actual_hold_time_s >= 0
            assert result.required_hold_time_s > 0
            assert result.max_temp_C >= result.min_temp_C
            assert result.job_id == f"consistency_{industry}"
            assert result.status in ["PASS", "FAIL", "INDETERMINATE"]