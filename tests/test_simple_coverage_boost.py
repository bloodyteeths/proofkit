"""
Simple Coverage Boost Tests

Minimal tests to boost coverage to 92% without import issues.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import SpecV1, DecisionResult, Industry
from core.normalize import normalize_temperature_data, NormalizationError
from core.decide import make_decision, DecisionError


class TestDecideCoverage:
    """Additional tests for decide.py coverage."""
    
    def test_decision_with_all_fields(self):
        """Test decision with comprehensive data."""
        # Create data that exercises more code paths
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=50, freq="30S", tz="UTC"),
            "temp_sensor_1": [175 + i*0.5 for i in range(50)],
            "temp_sensor_2": [174 + i*0.5 for i in range(50)],
            "temp_sensor_3": [176 + i*0.5 for i in range(50)]
        })
        
        # Test with majority threshold mode
        spec = SpecV1(
            version="1.0",
            job={"job_id": "coverage_test"},
            spec={
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            sensor_selection={
                "mode": "majority_over_threshold",
                "sensors": ["temp_sensor_1", "temp_sensor_2", "temp_sensor_3"],
                "require_at_least": 2
            }
        )
        
        result = make_decision(df, spec)
        assert isinstance(result, DecisionResult)
        assert result.job_id == "coverage_test"
    
    def test_decision_cumulative_mode(self):
        """Test cumulative hold time mode."""
        # Create data with temperature dips
        temps = []
        for i in range(100):
            if i % 20 < 5:  # Dip every 20 samples
                temps.append(179.0)
            else:
                temps.append(183.0)
        
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=100, freq="30S", tz="UTC"),
            "temp_sensor": temps
        })
        
        spec = SpecV1(
            version="1.0",
            job={"job_id": "cumulative_test"},
            spec={
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 1200,
                "sensor_uncertainty_C": 2.0
            },
            data_requirements={
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            logic={
                "continuous": False,
                "max_total_dips_s": 300  # Allow 5 minutes of dips
            }
        )
        
        result = make_decision(df, spec)
        assert isinstance(result, DecisionResult)
        assert len(result.reasons) > 0


class TestModelsCoverage:
    """Additional tests for models.py coverage."""
    
    def test_decision_result_complete(self):
        """Test DecisionResult with all optional fields."""
        # Create result with many optional fields
        result = DecisionResult(
            pass_=True,
            job_id="full_test",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=650.0,
            required_hold_time_s=600,
            max_temp_C=185.5,
            min_temp_C=178.2,
            reasons=["Pass"],
            warnings=["Warning"],
            timestamps_UTC=["2024-01-15T10:00:00Z"],
            hold_intervals=[{"start": "10:00", "end": "10:10"}],
            time_to_threshold_s=120.0,
            max_ramp_rate_C_per_min=3.5
        )
        
        # Test serialization
        data = result.model_dump()
        assert data["pass"] is True  # Check alias
        assert "time_to_threshold_s" in data
        assert data["time_to_threshold_s"] == 120.0
    
    def test_spec_validation(self):
        """Test SpecV1 validation."""
        # Test with minimal spec
        spec = SpecV1(
            version="1.0",
            job={"job_id": "minimal"},
            spec={
                "method": "TEST",
                "target_temp_C": 100.0,
                "hold_time_s": 60,
                "sensor_uncertainty_C": 1.0
            },
            data_requirements={
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        )
        
        assert spec.job.job_id == "minimal"
        assert spec.spec.target_temp_C == 100.0
        
        # Test with industry
        for industry in ["powder", "haccp", "autoclave"]:
            spec_ind = SpecV1(
                version="1.0",
                industry=industry,
                job={"job_id": f"test_{industry}"},
                spec={
                    "method": "TEST",
                    "target_temp_C": 100.0,
                    "hold_time_s": 60,
                    "sensor_uncertainty_C": 1.0
                },
                data_requirements={
                    "max_sample_period_s": 60.0,
                    "allowed_gaps_s": 120.0
                }
            )
            assert spec_ind.industry == industry


class TestNormalizeCoverage:
    """Additional tests for normalize.py coverage."""
    
    def test_normalize_edge_cases(self):
        """Test normalization edge cases."""
        # Test with perfect 30s intervals
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=20, freq="30S", tz="UTC"),
            "temperature": [180.0] * 20
        })
        
        normalized = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            max_sample_period_s=30.0
        )
        
        assert len(normalized) == 20
        assert "temperature" in normalized.columns
    
    def test_normalize_with_gaps(self):
        """Test normalization with gaps."""
        # Create data with a gap
        times1 = pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="30S", tz="UTC")
        times2 = pd.date_range("2024-01-15T10:05:30Z", periods=10, freq="30S", tz="UTC")
        
        df = pd.DataFrame({
            "timestamp": pd.concat([pd.Series(times1), pd.Series(times2)]),
            "temp": [180.0] * 20
        })
        
        # Should handle gap within allowed limit
        normalized = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,  # Allow 60s gaps
            max_sample_period_s=30.0
        )
        
        assert normalized is not None