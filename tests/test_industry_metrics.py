"""
ProofKit Industry-Specific Metrics Engine Tests

Comprehensive test suite for all industry-specific validation engines including:
- HACCP cooling validation (135°F→70°F ≤2h, 135°F→41°F ≤6h)
- Autoclave sterilization (Fo≥12, pressure≥15psi, 121°C hold≥15min)
- EtO sterilization (Gas flow + humidity steps validation)
- Concrete curing (First 24h temp 16-27°C & RH>95%)
- Cold chain storage (2-8°C ≥95% samples/day validation)

Example usage:
    pytest tests/test_industry_metrics.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

from core.models import SpecV1, DecisionResult, SensorMode
from core.metrics_haccp import validate_haccp_cooling, fahrenheit_to_celsius, celsius_to_fahrenheit
from core.metrics_autoclave import validate_autoclave_sterilization, calculate_fo_value, psi_to_kpa, kpa_to_psi
from core.metrics_sterile import validate_eto_sterilization
from core.metrics_concrete import validate_concrete_curing
from core.metrics_coldchain import validate_coldchain_storage
from core.decide import make_decision, DecisionError


class TestHACCPCoolingValidation:
    """Test HACCP cooling validation engine."""
    
    @pytest.fixture
    def haccp_spec(self):
        """HACCP cooling specification fixture."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "haccp",
            "job": {"job_id": "restaurant_cooling_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,  # 41°F target
                "hold_time_s": 3600,   # 1 hour hold at final temp
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
    
    @pytest.fixture
    def haccp_cooling_pass_data(self):
        """HACCP cooling data that should PASS."""
        # Simulate proper cooling: 135°F → 70°F in 1.5h, then 70°F → 41°F in total 5h
        timestamps = pd.date_range(
            start="2024-01-15T12:00:00Z", periods=25, freq="15min", tz="UTC"
        )
        
        # Temperature profile: Start at 57°C (135°F), cool to 21°C (70°F) by point 6, then to 5°C (41°F) by point 20
        temp_profile = [
            57.2, 54.0, 51.0, 47.0, 43.0, 38.0,  # First 1.5 hours to 70°F
            35.0, 32.0, 28.0, 25.0, 21.1,        # 70°F reached
            18.0, 15.0, 12.0, 10.0, 8.0, 6.0, 5.0,  # Cool to 41°F
            5.0, 5.0, 5.0, 5.0, 4.5, 4.5, 4.5   # Hold at 41°F
        ]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temp_profile,
            "temp_backup": [t + np.random.normal(0, 0.5) for t in temp_profile]
        })
    
    @pytest.fixture
    def haccp_cooling_fail_data(self):
        """HACCP cooling data that should FAIL (too slow cooling)."""
        timestamps = pd.date_range(
            start="2024-01-15T12:00:00Z", periods=30, freq="20min", tz="UTC"
        )
        
        # Temperature profile: Takes too long to cool (3h to 70°F, 8h total to 41°F)
        temp_profile = [
            57.2, 56.0, 55.0, 53.0, 51.0, 49.0, 47.0, 45.0, 43.0,  # Slow start
            40.0, 37.0, 34.0, 31.0, 28.0, 25.0, 22.0, 21.1,       # Finally reach 70°F at 5.3h
            19.0, 17.0, 15.0, 13.0, 11.0, 9.0, 7.0, 6.0, 5.5,     # Very slow to 41°F
            5.0, 5.0, 5.0, 4.8                                      # Finally reach 41°F at 8.7h
        ]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temp_profile,
            "temp_backup": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    def test_temperature_conversion_functions(self):
        """Test Fahrenheit/Celsius conversion functions."""
        # Test specific HACCP temperatures
        assert abs(fahrenheit_to_celsius(135.0) - 57.2222) < 0.01
        assert abs(fahrenheit_to_celsius(70.0) - 21.1111) < 0.01
        assert abs(fahrenheit_to_celsius(41.0) - 5.0) < 0.01
        
        assert abs(celsius_to_fahrenheit(57.2222) - 135.0) < 0.01
        assert abs(celsius_to_fahrenheit(21.1111) - 70.0) < 0.01
        assert abs(celsius_to_fahrenheit(5.0) - 41.0) < 0.01
    
    def test_haccp_cooling_pass_scenario(self, haccp_cooling_pass_data, haccp_spec):
        """Test HACCP cooling validation with passing data."""
        result = validate_haccp_cooling(haccp_cooling_pass_data, haccp_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "restaurant_cooling_001"
        assert result.target_temp_C == 5.0  # 41°F target
        assert len(result.reasons) > 0
        assert any("Phase 1" in reason for reason in result.reasons)
        assert any("Phase 2" in reason for reason in result.reasons)
        assert any("HACCP cooling requirements met" in reason for reason in result.reasons)
    
    def test_haccp_cooling_fail_scenario(self, haccp_cooling_fail_data, haccp_spec):
        """Test HACCP cooling validation with failing data."""
        result = validate_haccp_cooling(haccp_cooling_fail_data, haccp_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert result.job_id == "restaurant_cooling_001"
        assert len(result.reasons) > 0
        assert any("took" in reason and "limit" in reason for reason in result.reasons)
    
    def test_haccp_invalid_starting_temperature(self, haccp_spec):
        """Test HACCP cooling with invalid starting temperature."""
        # Start below 135°F
        timestamps = pd.date_range(
            start="2024-01-15T12:00:00Z", periods=10, freq="30min", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": [50.0] * 10,  # Start at 50°C (122°F) - below 135°F requirement
            "temp_backup": [49.5] * 10
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is False
        assert any("135°F" in reason for reason in result.reasons)
    
    def test_haccp_temperature_increase_detected(self, haccp_spec):
        """Test HACCP cooling fails when temperature increases (heating detected)."""
        timestamps = pd.date_range(
            start="2024-01-15T12:00:00Z", periods=10, freq="30min", tz="UTC"
        )
        
        # Temperature increases during cooling
        temp_profile = [57.2, 55.0, 53.0, 56.0, 59.0, 52.0, 48.0, 45.0, 42.0, 38.0]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temp_profile,
            "temp_backup": temp_profile
        })
        
        result = validate_haccp_cooling(df, haccp_spec)
        
        assert result.pass_ is False
        assert any("heating detected" in reason for reason in result.reasons)
    
    def test_haccp_integration_with_main_decision(self, haccp_cooling_pass_data, haccp_spec):
        """Test HACCP cooling integration with main decision algorithm."""
        result = make_decision(haccp_cooling_pass_data, haccp_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "restaurant_cooling_001"


class TestAutoclaveValidation:
    """Test autoclave sterilization validation engine."""
    
    @pytest.fixture
    def autoclave_spec(self):
        """Autoclave sterilization specification fixture."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "autoclave",
            "job": {"job_id": "pharma_sterilization_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 121.0,
                "hold_time_s": 900,  # 15 minutes
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 10.0,
                "allowed_gaps_s": 30.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            }
        })
    
    @pytest.fixture
    def autoclave_pass_data(self):
        """Autoclave sterilization data that should PASS."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=200, freq="30s", tz="UTC"
        )
        
        # Temperature profile: Ramp to 121°C, hold for 20 minutes, then cool
        temp_profile = (
            [20.0 + i * 5.0 for i in range(20)] +  # Ramp up to 120°C
            [121.0 + np.random.normal(0, 0.3) for _ in range(40)] +  # Hold at 121°C for 20 min
            [121.0 - i * 2.0 for i in range(40)] +  # Cool down
            [40.0] * 100  # Continue cooling
        )[:200]
        
        # Pressure profile in kPa (15 psi = 103.4 kPa)
        pressure_profile = (
            [101.3 + i * 1.0 for i in range(20)] +  # Ramp up pressure
            [105.0 + np.random.normal(0, 1.0) for _ in range(40)] +  # Hold pressure
            [105.0 - i * 1.0 for i in range(40)] +  # Release pressure
            [101.3] * 100  # Atmospheric pressure
        )[:200]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.5) for t in temp_profile],
            "pressure_1": pressure_profile,
            "pressure_2": [p + np.random.normal(0, 0.5) for p in pressure_profile]
        })
    
    @pytest.fixture
    def autoclave_fail_data(self):
        """Autoclave sterilization data that should FAIL (insufficient Fo value)."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="30s", tz="UTC"
        )
        
        # Temperature profile: Only reaches 115°C for short time
        temp_profile = (
            [20.0 + i * 4.0 for i in range(20)] +  # Ramp to 100°C
            [115.0 + np.random.normal(0, 1.0) for _ in range(20)] +  # Hold at 115°C (too low)
            [115.0 - i * 2.0 for i in range(20)] +  # Cool down
            [40.0] * 40
        )[:100]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    def test_fo_value_calculation(self):
        """Test Fo value calculation for sterilization lethality."""
        # Simple test case: 121°C for 15 minutes should give Fo ≈ 15
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=16, freq="1min", tz="UTC"
        )
        temps = pd.Series([121.0] * 16)
        
        fo_value = calculate_fo_value(temps, timestamps)
        assert 14.0 <= fo_value <= 16.0  # Should be close to 15
        
        # Higher temperature should give higher Fo value
        temps_high = pd.Series([125.0] * 16)
        fo_high = calculate_fo_value(temps_high, timestamps)
        assert fo_high > fo_value
    
    def test_pressure_conversion_functions(self):
        """Test pressure conversion functions."""
        assert abs(psi_to_kpa(15.0) - 103.421) < 0.1
        assert abs(kpa_to_psi(103.421) - 15.0) < 0.1
    
    def test_autoclave_pass_scenario(self, autoclave_pass_data, autoclave_spec):
        """Test autoclave validation with passing data."""
        result = validate_autoclave_sterilization(autoclave_pass_data, autoclave_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "pharma_sterilization_001"
        assert result.target_temp_C == 121.0
        assert result.conservative_threshold_C == 119.0
        assert len(result.reasons) > 0
        assert any("Fo value" in reason for reason in result.reasons)
        assert any("sterilization requirements met" in reason for reason in result.reasons)
    
    def test_autoclave_fail_scenario(self, autoclave_fail_data, autoclave_spec):
        """Test autoclave validation with failing data."""
        result = validate_autoclave_sterilization(autoclave_fail_data, autoclave_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert len(result.reasons) > 0
        assert any("Fo value" in reason or "temperature" in reason for reason in result.reasons)
    
    def test_autoclave_excessive_temperature(self, autoclave_spec):
        """Test autoclave validation with excessive temperature."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=50, freq="30s", tz="UTC"
        )
        
        # Temperature too high (>123°C limit)
        temp_profile = [130.0] * 50
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": temp_profile
        })
        
        result = validate_autoclave_sterilization(df, autoclave_spec)
        
        assert result.pass_ is False
        assert any("123°C limit" in reason for reason in result.reasons)
    
    def test_autoclave_integration_with_main_decision(self, autoclave_pass_data, autoclave_spec):
        """Test autoclave integration with main decision algorithm."""
        result = make_decision(autoclave_pass_data, autoclave_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "pharma_sterilization_001"


class TestEtOSterilizationValidation:
    """Test EtO (Ethylene Oxide) sterilization validation engine."""
    
    @pytest.fixture
    def eto_spec(self):
        """EtO sterilization specification fixture."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "medical_device_sterilization_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 55.0,
                "hold_time_s": 7200,  # 2 hours
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 120.0,
                "allowed_gaps_s": 300.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 3
            }
        })
    
    @pytest.fixture
    def eto_pass_data(self):
        """EtO sterilization data that should PASS."""
        timestamps = pd.date_range(
            start="2024-01-15T08:00:00Z", periods=150, freq="5min", tz="UTC"
        )
        
        # Temperature profile: Preconditioning, sterilization, aeration
        temp_profile = (
            [20.0 + i * 1.5 for i in range(20)] +  # Preconditioning ramp
            [55.0 + np.random.normal(0, 1.0) for _ in range(60)] +  # Hold at 55°C for 5 hours
            [55.0 - i * 1.0 for i in range(30)] +  # Cool down
            [25.0] * 40  # Aeration phase
        )[:150]
        
        # Humidity profile (45-85% RH range)
        humidity_profile = (
            [30.0 + i * 2.0 for i in range(20)] +  # Ramp to 70% RH
            [70.0 + np.random.normal(0, 5.0) for _ in range(60)] +  # Hold humidity
            [70.0 - i * 1.0 for i in range(30)] +  # Reduce humidity
            [40.0] * 40
        )[:150]
        
        # Gas concentration profile (arbitrary units)
        gas_profile = (
            [0.0] * 20 +  # No gas during preconditioning
            [800.0 + np.random.normal(0, 50.0) for _ in range(60)] +  # Gas injection and hold
            [800.0 * (1 - i/30) for i in range(30)] +  # Gas evacuation
            [10.0] * 40  # Residual gas
        )[:150]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.5) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "eto_concentration": gas_profile
        })
    
    @pytest.fixture
    def eto_fail_data(self):
        """EtO sterilization data that should FAIL (temperature too low)."""
        timestamps = pd.date_range(
            start="2024-01-15T08:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # Temperature profile: Never reaches proper sterilization temperature
        temp_profile = [45.0 + np.random.normal(0, 2.0) for _ in range(100)]  # Too low (45°C vs 50°C min)
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.5) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    def test_eto_pass_scenario(self, eto_pass_data, eto_spec):
        """Test EtO sterilization validation with passing data."""
        result = validate_eto_sterilization(eto_pass_data, eto_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "medical_device_sterilization_001"
        assert result.target_temp_C == 55.0
        assert result.conservative_threshold_C == 50.0
        assert len(result.reasons) > 0
        assert any("sterilization requirements met" in reason for reason in result.reasons)
    
    def test_eto_fail_scenario(self, eto_fail_data, eto_spec):
        """Test EtO sterilization validation with failing data."""
        result = validate_eto_sterilization(eto_fail_data, eto_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert len(result.reasons) > 0
        assert any("temperature" in reason.lower() for reason in result.reasons)
    
    def test_eto_temperature_too_high(self, eto_spec):
        """Test EtO sterilization with excessive temperature."""
        timestamps = pd.date_range(
            start="2024-01-15T08:00:00Z", periods=50, freq="5min", tz="UTC"
        )
        
        # Temperature too high (>60°C limit)
        temp_profile = [70.0] * 50
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": temp_profile,
            "temp_3": temp_profile
        })
        
        result = validate_eto_sterilization(df, eto_spec)
        
        assert result.pass_ is False
        assert any("60°C limit" in reason for reason in result.reasons)
    
    def test_eto_integration_with_main_decision(self, eto_pass_data, eto_spec):
        """Test EtO sterilization integration with main decision algorithm."""
        result = make_decision(eto_pass_data, eto_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "medical_device_sterilization_001"


class TestConcreteValidation:
    """Test concrete curing validation engine."""
    
    @pytest.fixture
    def concrete_spec(self):
        """Concrete curing specification fixture."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "building_foundation_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 21.5,  # 70°F optimal
                "hold_time_s": 86400,   # 24 hours minimum
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 600.0,
                "allowed_gaps_s": 1800.0
            },
            "sensor_selection": {
                "mode": "mean_of_set",
                "require_at_least": 2
            }
        })
    
    @pytest.fixture
    def concrete_pass_data(self):
        """Concrete curing data that should PASS."""
        timestamps = pd.date_range(
            start="2024-01-15T06:00:00Z", periods=200, freq="30min", tz="UTC"
        )
        
        # Temperature profile: Stable 20-22°C for extended period
        temp_profile = [21.0 + np.random.normal(0, 1.0) for _ in range(200)]
        # Ensure all temperatures are in valid range (16-27°C)
        temp_profile = [max(16.5, min(26.5, t)) for t in temp_profile]
        
        # Humidity profile: >95% RH
        humidity_profile = [96.0 + np.random.normal(0, 2.0) for _ in range(200)]
        humidity_profile = [max(95.0, min(99.0, h)) for h in humidity_profile]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 1.0) for h in humidity_profile]
        })
    
    @pytest.fixture
    def concrete_fail_data(self):
        """Concrete curing data that should FAIL (temperature too cold)."""
        timestamps = pd.date_range(
            start="2024-01-15T06:00:00Z", periods=100, freq="30min", tz="UTC"
        )
        
        # Temperature profile: Too cold (<16°C)
        temp_profile = [12.0 + np.random.normal(0, 2.0) for _ in range(100)]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    def test_concrete_pass_scenario(self, concrete_pass_data, concrete_spec):
        """Test concrete curing validation with passing data."""
        result = validate_concrete_curing(concrete_pass_data, concrete_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "building_foundation_001"
        assert result.target_temp_C == 21.5
        assert result.conservative_threshold_C == 16.0
        assert len(result.reasons) > 0
        assert any("curing requirements met" in reason for reason in result.reasons)
    
    def test_concrete_fail_scenario(self, concrete_fail_data, concrete_spec):
        """Test concrete curing validation with failing data."""
        result = validate_concrete_curing(concrete_fail_data, concrete_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert len(result.reasons) > 0
        assert any("16°C" in reason for reason in result.reasons)
    
    def test_concrete_temperature_too_high(self, concrete_spec):
        """Test concrete curing with excessive temperature."""
        timestamps = pd.date_range(
            start="2024-01-15T06:00:00Z", periods=50, freq="30min", tz="UTC"
        )
        
        # Temperature too high (>27°C)
        temp_profile = [35.0] * 50
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": temp_profile
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is False
        assert any("27°C" in reason for reason in result.reasons)
    
    def test_concrete_rapid_temperature_change(self, concrete_spec):
        """Test concrete curing with rapid temperature changes."""
        timestamps = pd.date_range(
            start="2024-01-15T06:00:00Z", periods=20, freq="30min", tz="UTC"
        )
        
        # Rapid temperature swings (>5°C/hour)
        temp_profile = [20.0, 30.0, 15.0, 25.0, 10.0] * 4
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": temp_profile
        })
        
        result = validate_concrete_curing(df, concrete_spec)
        
        assert result.pass_ is False
        assert any("change rate" in reason for reason in result.reasons)
    
    def test_concrete_integration_with_main_decision(self, concrete_pass_data, concrete_spec):
        """Test concrete curing integration with main decision algorithm."""
        result = make_decision(concrete_pass_data, concrete_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "building_foundation_001"


class TestColdChainValidation:
    """Test cold chain storage validation engine."""
    
    @pytest.fixture
    def coldchain_spec(self):
        """Cold chain storage specification fixture."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "vaccine_storage_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,  # Mid-range cold chain
                "hold_time_s": 82800,  # 23 hours (daily monitoring)
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 300.0,  # 5 minute intervals
                "allowed_gaps_s": 900.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 2
            }
        })
    
    @pytest.fixture
    def coldchain_pass_data(self):
        """Cold chain storage data that should PASS."""
        timestamps = pd.date_range(
            start="2024-01-15T00:00:00Z", periods=300, freq="5min", tz="UTC"
        )
        
        # Temperature profile: Stable 3-7°C (within 2-8°C range)
        temp_profile = [5.0 + np.random.normal(0, 1.0) for _ in range(300)]
        # Ensure 98% of temperatures are in valid range
        for i in range(len(temp_profile)):
            if i % 50 == 0:  # Allow occasional brief excursions
                temp_profile[i] = 9.0 if np.random.random() > 0.5 else 1.5
            else:
                temp_profile[i] = max(2.5, min(7.5, temp_profile[i]))
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.2) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    @pytest.fixture
    def coldchain_fail_data(self):
        """Cold chain storage data that should FAIL (too many excursions)."""
        timestamps = pd.date_range(
            start="2024-01-15T00:00:00Z", periods=200, freq="5min", tz="UTC"
        )
        
        # Temperature profile: Frequent excursions outside 2-8°C range
        temp_profile = []
        for i in range(200):
            if i % 10 < 5:  # 50% of time outside range
                temp_profile.append(12.0 + np.random.normal(0, 2.0))
            else:
                temp_profile.append(5.0 + np.random.normal(0, 1.0))
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile]
        })
    
    def test_coldchain_pass_scenario(self, coldchain_pass_data, coldchain_spec):
        """Test cold chain validation with passing data."""
        result = validate_coldchain_storage(coldchain_pass_data, coldchain_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "vaccine_storage_001"
        assert result.target_temp_C == 5.0
        assert result.conservative_threshold_C == 2.0
        assert len(result.reasons) > 0
        assert any("cold chain" in reason.lower() for reason in result.reasons)
    
    def test_coldchain_fail_scenario(self, coldchain_fail_data, coldchain_spec):
        """Test cold chain validation with failing data."""
        result = validate_coldchain_storage(coldchain_fail_data, coldchain_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False
        assert len(result.reasons) > 0
        assert any("compliance" in reason.lower() or "excursion" in reason.lower() for reason in result.reasons)
    
    def test_coldchain_freezing_risk(self, coldchain_spec):
        """Test cold chain validation with freezing risk."""
        timestamps = pd.date_range(
            start="2024-01-15T00:00:00Z", periods=50, freq="5min", tz="UTC"
        )
        
        # Temperature drops below freezing
        temp_profile = [-5.0] * 50
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": temp_profile
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        assert result.pass_ is False
        assert any("Critical low temperature" in reason or "-5.0°C" in reason for reason in result.reasons)
    
    def test_coldchain_high_temperature_abuse(self, coldchain_spec):
        """Test cold chain validation with high temperature abuse."""
        timestamps = pd.date_range(
            start="2024-01-15T00:00:00Z", periods=50, freq="5min", tz="UTC"
        )
        
        # Temperature too high (>15°C)
        temp_profile = [20.0] * 50
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": temp_profile
        })
        
        result = validate_coldchain_storage(df, coldchain_spec)
        
        assert result.pass_ is False
        assert any("Critical high temperature" in reason or "20.0°C" in reason for reason in result.reasons)
    
    def test_coldchain_integration_with_main_decision(self, coldchain_pass_data, coldchain_spec):
        """Test cold chain integration with main decision algorithm."""
        result = make_decision(coldchain_pass_data, coldchain_spec)
        
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True
        assert result.job_id == "vaccine_storage_001"


class TestIndustryMetricsIntegration:
    """Test integration of industry metrics engines with main decision algorithm."""
    
    def test_invalid_industry_fallback_to_powder(self):
        """Test that invalid industry falls back to powder coat validation."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=25, freq="30s", tz="UTC"
        )
        
        # Standard powder coat data
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 20,
            "pmt_sensor_2": [164.0, 169.0, 174.0, 178.0, 180.0] + [182.5] * 20
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "invalid_industry",  # Invalid industry
            "job": {"job_id": "fallback_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        })
        
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
        # Should use default powder coat validation
        assert result.target_temp_C == 180.0
        assert result.conservative_threshold_C == 182.0
    
    def test_missing_industry_field_fallback(self):
        """Test that missing industry field falls back to powder coat validation."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=25, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "pmt_sensor_1": [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 20,
            "pmt_sensor_2": [164.0, 169.0, 174.0, 178.0, 180.0] + [182.5] * 20
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            # No industry field
            "job": {"job_id": "no_industry_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        })
        
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
        # Should use default powder coat validation
        assert result.target_temp_C == 180.0
        assert result.conservative_threshold_C == 182.0
    
    def test_all_industry_engines_return_decision_result(self):
        """Test that all industry engines return compatible DecisionResult objects."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=50, freq="30s", tz="UTC"
        )
        
        # Generic test data
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [20.0] * 50,
            "temp_2": [21.0] * 50,
            "humidity_1": [60.0] * 50,
            "pressure_1": [100.0] * 50,
            "eto_concentration": [100.0] * 50
        })
        
        industries = ["haccp", "autoclave", "sterile", "concrete", "coldchain"]
        
        for industry in industries:
            spec = SpecV1(**{
                "version": "1.0",
                "industry": industry,
                "job": {"job_id": f"{industry}_compatibility_test"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 50.0,
                    "hold_time_s": 3600,
                    "sensor_uncertainty_C": 1.0
                },
                "data_requirements": {
                    "max_sample_period_s": 60.0,
                    "allowed_gaps_s": 120.0
                }
            })
            
            result = make_decision(df, spec)
            
            # All engines should return valid DecisionResult objects
            assert isinstance(result, DecisionResult)
            assert hasattr(result, 'pass_')
            assert hasattr(result, 'job_id')
            assert hasattr(result, 'target_temp_C')
            assert hasattr(result, 'conservative_threshold_C')
            assert hasattr(result, 'actual_hold_time_s')
            assert hasattr(result, 'required_hold_time_s')
            assert hasattr(result, 'max_temp_C')
            assert hasattr(result, 'min_temp_C')
            assert hasattr(result, 'reasons')
            assert hasattr(result, 'warnings')
            
            assert isinstance(result.pass_, bool)
            assert isinstance(result.job_id, str)
            assert isinstance(result.reasons, list)
            assert isinstance(result.warnings, list)
            assert result.job_id == f"{industry}_compatibility_test"


class TestIndustryMetricsErrorHandling:
    """Test error handling in industry-specific metrics engines."""
    
    def test_invalid_industry_in_engine_spec(self):
        """Test that engines validate industry field correctly."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=10, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [20.0] * 10,
            "temp_2": [21.0] * 10
        })
        
        # Create spec with wrong industry for HACCP engine
        wrong_spec = SpecV1(**{
            "version": "1.0",
            "industry": "powder",  # Wrong industry for HACCP engine
            "job": {"job_id": "wrong_industry_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 50.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        })
        
        with pytest.raises(DecisionError):
            validate_haccp_cooling(df, wrong_spec)
    
    def test_empty_dataframe_error_handling(self):
        """Test that engines handle empty DataFrames appropriately."""
        df = pd.DataFrame()
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "haccp",
            "job": {"job_id": "empty_df_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 50.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        })
        
        with pytest.raises(DecisionError):
            validate_haccp_cooling(df, spec)
    
    def test_insufficient_data_points_error_handling(self):
        """Test that engines handle insufficient data points appropriately."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=1, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [20.0]
        })
        
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "autoclave",
            "job": {"job_id": "insufficient_data_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 121.0,
                "hold_time_s": 900,
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        })
        
        with pytest.raises(DecisionError):
            validate_autoclave_sterilization(df, spec)