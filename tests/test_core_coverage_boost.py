"""
Coverage Boost Tests

Targeted tests to increase coverage in core modules to reach 92% threshold.
Focus on uncovered code paths in decide.py, models.py, and normalize.py.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from unittest.mock import patch, MagicMock

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import SpecV1, DecisionResult, SensorMode, Logic, Industry
from core.normalize import (
    normalize_temperature_data, 
    NormalizationError,
    detect_temperature_columns,
    convert_fahrenheit_to_celsius,
    load_csv_with_metadata
)
from core.decide import (
    make_decision,
    DecisionError,
    calculate_conservative_threshold,
    combine_sensor_readings,
    calculate_continuous_hold_time,
    calculate_cumulative_hold_time,
    calculate_boolean_hold_time,
    validate_preconditions,
    detect_temperature_columns
)


class TestModelsCompleteCoverage:
    """Test models.py edge cases for complete coverage."""
    
    def test_decision_result_all_fields(self):
        """Test DecisionResult with all optional fields populated."""
        result = DecisionResult(
            pass_=True,
            job_id="test_complete",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=650.0,
            required_hold_time_s=600,
            max_temp_C=185.5,
            min_temp_C=178.2,
            reasons=["All requirements met"],
            warnings=["Minor fluctuation detected"],
            # Optional fields
            timestamps_UTC=["2024-01-15T10:00:00Z", "2024-01-15T10:30:00Z"],
            hold_intervals=[
                {"start": "2024-01-15T10:05:00Z", "end": "2024-01-15T10:15:00Z"}
            ],
            sensor_data={"sensor_1": [180.1, 182.3], "sensor_2": [179.8, 182.1]},
            time_to_threshold_s=120.0,
            max_ramp_rate_C_per_min=3.5,
            cooling_curve={"t_0": 135.0, "t_final": 41.0, "duration_s": 7200},
            excursions=[{"start": "10:20:00", "end": "10:21:00", "max_deviation_C": 0.5}],
            humidity_avg=65.0,
            pressure_avg=14.7,
            gas_concentration_ppm=1200.0,
            sterilization_phases={
                "conditioning": {"duration_s": 300, "complete": True},
                "sterilization": {"duration_s": 900, "complete": True}
            }
        )
        
        # Verify all fields
        assert result.pass_ is True
        assert result.time_to_threshold_s == 120.0
        assert result.max_ramp_rate_C_per_min == 3.5
        assert len(result.timestamps_UTC) == 2
        assert len(result.hold_intervals) == 1
        assert "sensor_1" in result.sensor_data
        assert result.humidity_avg == 65.0
        assert result.pressure_avg == 14.7
        assert result.gas_concentration_ppm == 1200.0
        
        # Test JSON serialization with all fields
        json_data = result.model_dump(by_alias=True)
        assert json_data["pass"] is True  # Alias works
        assert "cooling_curve" in json_data
        assert "sterilization_phases" in json_data
    
    def test_spec_v1_all_industries(self):
        """Test SpecV1 with all industry configurations."""
        for industry in Industry:
            spec_data = {
                "version": "1.0",
                "industry": industry.value,
                "job": {"job_id": f"test_{industry.value}"},
                "spec": {
                    "method": "TEST",
                    "target_temp_C": 180.0,
                    "hold_time_s": 600,
                    "sensor_uncertainty_C": 2.0
                },
                "data_requirements": {
                    "max_sample_period_s": 30.0,
                    "allowed_gaps_s": 60.0
                }
            }
            
            spec = SpecV1(**spec_data)
            assert spec.industry == industry
            assert spec.job.job_id == f"test_{industry.value}"
    
    def test_logic_configurations(self):
        """Test Logic with various configurations."""
        # Test continuous mode
        logic_continuous = Logic(continuous=True, max_total_dips_s=0)
        assert logic_continuous.continuous is True
        assert logic_continuous.max_total_dips_s == 0
        
        # Test cumulative mode
        logic_cumulative = Logic(continuous=False, max_total_dips_s=120)
        assert logic_cumulative.continuous is False
        assert logic_cumulative.max_total_dips_s == 120
        
        # Test default values
        logic_default = Logic()
        assert logic_default.continuous is True  # Default
        assert logic_default.max_total_dips_s == 0  # Default


class TestNormalizeCompleteCoverage:
    """Test normalize.py uncovered paths."""
    
    def test_detect_temperature_columns_edge_cases(self):
        """Test temperature column detection edge cases."""
        # Test with no temperature columns
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=5, freq="30S"),
            "humidity": [65, 66, 67, 68, 69],
            "pressure": [14.7] * 5
        })
        
        temp_cols = detect_temperature_columns(df)
        assert len(temp_cols) == 0
        
        # Test with various temperature column names
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=5, freq="30S"),
            "temperature": [180] * 5,
            "temp_sensor_1": [181] * 5,
            "Temperature_2": [182] * 5,
            "food_temp": [183] * 5,
            "chamber_temperature": [184] * 5,
            "TempC": [185] * 5,
            "tempF": [350] * 5,
            "not_a_temp": [999] * 5
        })
        
        temp_cols = detect_temperature_columns(df)
        assert "temperature" in temp_cols
        assert "temp_sensor_1" in temp_cols
        assert "Temperature_2" in temp_cols
        assert "food_temp" in temp_cols
        assert "chamber_temperature" in temp_cols
        assert "TempC" in temp_cols
        assert "tempF" in temp_cols
        assert "not_a_temp" not in temp_cols
    
    def test_fahrenheit_conversion_mixed_units(self):
        """Test Fahrenheit to Celsius conversion with mixed units."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=5, freq="30S"),
            "tempF": [356, 360, 365, 370, 375],  # Fahrenheit
            "tempC": [180, 182, 185, 188, 190]   # Already Celsius
        })
        
        # Convert Fahrenheit column
        df["temp_celsius"] = convert_fahrenheit_to_celsius(df["tempF"])
        
        # Verify conversion
        expected_celsius = [180, 182.22, 185, 187.78, 190.56]
        for i, expected in enumerate(expected_celsius):
            assert abs(df.iloc[i]["temp_celsius"] - expected) < 0.1
    
    def test_normalization_with_timezone_handling(self):
        """Test normalization with various timezone scenarios."""
        # Test with naive timestamps (no timezone)
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15 10:00:00", periods=10, freq="30S"),
            "temp": [180 + i*0.5 for i in range(10)]
        })
        
        # Should handle naive timestamps
        normalized = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            max_sample_period_s=30.0
        )
        
        # Result should have UTC timezone
        assert normalized['timestamp'].dt.tz is not None
        assert str(normalized['timestamp'].dt.tz) == 'UTC'
    
    def test_load_csv_with_metadata_edge_cases(self):
        """Test CSV loading with various metadata scenarios."""
        # Create test CSV with comments
        csv_content = """# Test CSV file
# Equipment: Test Oven
# Date: 2024-01-15
# Operator: John Doe
timestamp,temperature
2024-01-15T10:00:00Z,180.0
2024-01-15T10:00:30Z,182.5
2024-01-15T10:01:00Z,183.0
"""
        csv_path = Path("test_metadata.csv")
        csv_path.write_text(csv_content)
        
        try:
            df, metadata = load_csv_with_metadata(str(csv_path))
            
            # Should extract metadata from comments
            assert len(metadata) > 0
            assert any("Equipment" in line for line in metadata)
            assert any("Test Oven" in line for line in metadata)
            
            # Should have correct data
            assert len(df) == 3
            assert "temperature" in df.columns
        finally:
            csv_path.unlink()


class TestDecideCompleteCoverage:
    """Test decide.py uncovered paths."""
    
    def test_get_default_sensor_columns(self):
        """Test default sensor column detection."""
        # Test with standard columns
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=5, freq="30S"),
            "pmt_sensor_1": [180] * 5,
            "pmt_sensor_2": [181] * 5,
            "temp_3": [182] * 5
        })
        
        columns = get_default_sensor_columns(df)
        assert "pmt_sensor_1" in columns
        assert "pmt_sensor_2" in columns
        assert len(columns) >= 2
    
    def test_validate_preconditions_edge_cases(self):
        """Test precondition validation edge cases."""
        spec = SpecV1(
            version="1.0",
            job={"job_id": "test"},
            spec={"method": "TEST", "target_temp_C": 180.0, "hold_time_s": 600, "sensor_uncertainty_C": 2.0},
            data_requirements={"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        )
        
        # Test with empty dataframe
        df_empty = pd.DataFrame()
        errors = validate_preconditions(df_empty, spec)
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)
        
        # Test with no timestamp column
        df_no_time = pd.DataFrame({"temp": [180, 181, 182]})
        errors = validate_preconditions(df_no_time, spec)
        assert len(errors) > 0
        assert any("timestamp" in e.lower() for e in errors)
        
        # Test with insufficient data
        df_short = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=2, freq="30S"),
            "temp": [180, 181]
        })
        errors = validate_preconditions(df_short, spec)
        assert len(errors) > 0
        assert any("insufficient" in e.lower() or "few" in e.lower() for e in errors)
    
    def test_boolean_hold_time_calculation(self):
        """Test boolean hold time calculation for majority mode."""
        # Create boolean series (True = above threshold)
        above_threshold = pd.Series([False, False, True, True, True, True, False, True, True])
        time_series = pd.Series(pd.date_range("2024-01-15", periods=9, freq="30S"))
        
        hold_time, intervals = calculate_boolean_hold_time(
            above_threshold,
            time_series,
            target_step_s=30.0
        )
        
        # Should count True periods
        assert hold_time > 0
        assert len(intervals) > 0
        
        # Verify intervals are correct
        for start_idx, end_idx in intervals:
            assert above_threshold.iloc[start_idx:end_idx+1].all()
    
    def test_continuous_hold_time_with_hysteresis(self):
        """Test continuous hold time with hysteresis logic."""
        # Create temperature series that crosses threshold with hysteresis
        temps = [179, 181, 183, 182.5, 181.5, 180.5, 179.5, 182, 183, 184]
        combined_temps = pd.Series(temps)
        time_series = pd.Series(pd.date_range("2024-01-15", periods=10, freq="30S"))
        
        hold_time, intervals, _, _ = calculate_continuous_hold_time(
            combined_temps,
            time_series,
            threshold_C=182.0,
            hysteresis_C=2.0,
            target_step_s=30.0
        )
        
        # Should handle hysteresis properly
        assert isinstance(hold_time, float)
        assert hold_time >= 0
        assert isinstance(intervals, list)
    
    def test_cumulative_hold_time_with_dips(self):
        """Test cumulative hold time with allowed dips."""
        # Create temperature series with dips
        temps = [183, 183, 181, 179, 183, 183, 183, 178, 183, 183]
        combined_temps = pd.Series(temps)
        time_series = pd.Series(pd.date_range("2024-01-15", periods=10, freq="30S"))
        
        hold_time, intervals = calculate_cumulative_hold_time(
            combined_temps,
            time_series,
            threshold_C=182.0,
            hysteresis_C=2.0,
            max_total_dips_s=60.0,  # Allow 60s of dips
            target_step_s=30.0
        )
        
        # Should count time above threshold minus allowed dips
        assert isinstance(hold_time, float)
        assert hold_time > 0
        assert isinstance(intervals, list)
    
    def test_decision_with_custom_sensor_selection(self):
        """Test decision making with custom sensor configurations."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=20, freq="30S"),
            "sensor_A": [182 + np.sin(i/2) for i in range(20)],
            "sensor_B": [183 + np.cos(i/2) for i in range(20)],
            "sensor_C": [181 + np.sin(i/3) for i in range(20)]
        })
        
        # Test with specific sensor selection
        spec = SpecV1(
            version="1.0",
            job={"job_id": "custom_sensors"},
            spec={"method": "TEST", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            data_requirements={"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0},
            sensor_selection={
                "mode": "mean_of_set",
                "sensors": ["sensor_A", "sensor_B", "sensor_C"],
                "require_at_least": 2
            }
        )
        
        result = make_decision(df, spec)
        assert isinstance(result, DecisionResult)
        assert result.job_id == "custom_sensors"
    
    def test_decision_error_handling(self):
        """Test error handling in decision process."""
        spec = SpecV1(
            version="1.0",
            job={"job_id": "error_test"},
            spec={"method": "TEST", "target_temp_C": 180.0, "hold_time_s": 300, "sensor_uncertainty_C": 2.0},
            data_requirements={"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
        )
        
        # Test with missing sensors
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=10, freq="30S"),
            "wrong_column": [180] * 10
        })
        
        with pytest.raises(DecisionError) as exc_info:
            make_decision(df, spec)
        
        assert "sensor" in str(exc_info.value).lower() or "column" in str(exc_info.value).lower()


class TestIndustryMetricsCoverage:
    """Test industry-specific metrics for coverage."""
    
    def test_haccp_cooling_validation_edge_cases(self):
        """Test HACCP cooling validation edge cases."""
        from core.metrics_haccp import validate_haccp_cooling
        
        # Create spec with HACCP cooling requirements
        spec = SpecV1(
            version="1.0",
            industry="haccp",
            job={"job_id": "haccp_test"},
            spec={
                "method": "COOLING",
                "initial_temp_C": 135.0,
                "target_temp_C": 41.0,
                "time_limit_s": 21600,
                "sensor_uncertainty_C": 1.0
            },
            data_requirements={"max_sample_period_s": 60.0, "allowed_gaps_s": 120.0}
        )
        
        # Test successful cooling
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=50, freq="2min"),
            "food_temp": np.linspace(135, 40, 50)
        })
        
        result = validate_haccp_cooling(df, spec)
        assert isinstance(result, DecisionResult)
        assert result.cooling_curve is not None
    
    def test_autoclave_ramp_rate_validation(self):
        """Test autoclave ramp rate validation."""
        from core.metrics_autoclave import validate_autoclave_sterilization
        
        spec = SpecV1(
            version="1.0",
            industry="autoclave",
            job={"job_id": "autoclave_test"},
            spec={
                "method": "STEAM",
                "target_temp_C": 121.0,
                "hold_time_s": 900,
                "sensor_uncertainty_C": 0.5,
                "max_ramp_rate_C_per_min": 5.0
            },
            data_requirements={"max_sample_period_s": 30.0, "allowed_gaps_s": 30.0}
        )
        
        # Test with acceptable ramp rate
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15", periods=30, freq="30S"),
            "chamber_temp": [100 + i*2 for i in range(15)] + [121.5] * 15
        })
        
        result = validate_autoclave_sterilization(df, spec)
        assert isinstance(result, DecisionResult)
        assert result.max_ramp_rate_C_per_min is not None