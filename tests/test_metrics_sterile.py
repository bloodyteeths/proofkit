"""
Comprehensive tests for sterile environment metrics validation.

Tests focus on sterile processing validation including:
- ISO 14644 cleanroom temperature windows (50-60°C operating range)
- Relative humidity control (45-85% RH range) 
- Temperature/humidity boundary condition validation
- Multi-sensor consensus validation
- Environmental stability requirements

Example usage:
    pytest tests/test_metrics_sterile.py -v --cov=core.metrics_sterile
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from core.models import SpecV1, DecisionResult, SensorMode
from core.metrics_sterile import (
    validate_eto_sterilization,
    validate_sterile_environment,
    check_humidity_control,
    validate_environmental_stability,
    calculate_process_deviation
)
from core.decide import make_decision, DecisionError


class TestSterileEnvironmentValidation:
    """Test sterile environment validation with ISO requirements."""
    
    @pytest.fixture
    def sterile_spec(self):
        """Standard sterile environment specification."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "sterile_validation_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 55.0,  # Mid-range of 50-60°C window
                "hold_time_s": 3600,    # 1 hour process
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 180.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 3
            }
        })
    
    @pytest.fixture
    def iso_compliant_data(self):
        """Data that meets ISO 14644 sterile environment requirements."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=120, freq="1min", tz="UTC"
        )
        
        # Temperature profile: Stable within 50-60°C window
        base_temp = 55.0
        temp_profile = [base_temp + np.random.normal(0, 1.0) for _ in range(120)]
        # Ensure all temperatures are in valid ISO window
        temp_profile = [max(50.5, min(59.5, t)) for t in temp_profile]
        
        # Humidity profile: Stable within 45-85% RH range
        base_humidity = 65.0
        humidity_profile = [base_humidity + np.random.normal(0, 5.0) for _ in range(120)]
        # Ensure humidity is in valid range with occasional brief excursions
        humidity_profile = [max(46.0, min(84.0, h)) for h in humidity_profile]
        
        # Pressure profile: Slight positive pressure
        pressure_profile = [102.0 + np.random.normal(0, 0.5) for _ in range(120)]
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.4) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 2.0) for h in humidity_profile],
            "pressure_1": pressure_profile
        })
    
    @pytest.fixture
    def iso_violation_data(self):
        """Data that violates ISO 14644 requirements."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=80, freq="1min", tz="UTC"
        )
        
        # Temperature profile: Frequent excursions outside 50-60°C window
        temp_profile = []
        for i in range(80):
            if i % 10 < 3:  # 30% of time outside window
                temp_profile.append(45.0 + np.random.normal(0, 2.0))  # Too low
            elif i % 10 < 6:  # Another 30% too high
                temp_profile.append(65.0 + np.random.normal(0, 2.0))  # Too high
            else:
                temp_profile.append(55.0 + np.random.normal(0, 1.0))  # Acceptable
        
        # Humidity profile: Poor control, frequent violations
        humidity_profile = []
        for i in range(80):
            if i % 8 < 3:  # ~40% of time outside range
                humidity_profile.append(30.0 + np.random.normal(0, 5.0))  # Too low
            elif i % 8 < 5:
                humidity_profile.append(90.0 + np.random.normal(0, 5.0))  # Too high
            else:
                humidity_profile.append(65.0 + np.random.normal(0, 3.0))  # Acceptable
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_profile,
            "temp_2": [t + np.random.normal(0, 0.5) for t in temp_profile],
            "temp_3": [t + np.random.normal(0, 0.3) for t in temp_profile],
            "humidity_1": humidity_profile,
            "humidity_2": [h + np.random.normal(0, 2.0) for h in humidity_profile]
        })
    
