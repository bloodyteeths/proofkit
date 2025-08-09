"""
Test temperature column detection for coldchain metrics.

Tests the robust temperature column detection with various aliases and patterns.
"""

import pandas as pd
import pytest
from core.metrics_coldchain import detect_temperature_columns, validate_coldchain_storage
from core.models import SpecV1
from core.errors import RequiredSignalMissingError


class TestTemperatureColumnDetection:
    """Test temperature column detection with various patterns."""
    
    def test_basic_temp_patterns(self):
        """Test basic temperature pattern detection."""
        # Test temp_1, temp_2 (from actual CSV files)
        df1 = pd.DataFrame({"timestamp": [], "temp_1": [], "temp_2": []})
        columns1 = detect_temperature_columns(df1)
        assert "temp_1" in columns1
        assert "temp_2" in columns1
        assert len(columns1) == 2
        
        # Test temperature
        df2 = pd.DataFrame({"timestamp": [], "temperature": [], "humidity": []})
        columns2 = detect_temperature_columns(df2)
        assert "temperature" in columns2
        assert len(columns2) == 1
    
    def test_numbered_sensor_patterns(self):
        """Test numbered sensor patterns (t1, t2, etc.)."""
        df = pd.DataFrame({
            "timestamp": [],
            "t1": [],
            "t2": [],
            "t10": [],
            "humidity": []
        })
        columns = detect_temperature_columns(df)
        assert "t1" in columns
        assert "t2" in columns  
        assert "t10" in columns
        assert "humidity" not in columns
        assert len(columns) == 3
    
    def test_probe_patterns(self):
        """Test probe sensor patterns (probe1, probe2, etc.)."""
        df = pd.DataFrame({
            "timestamp": [],
            "probe1": [],
            "probe2": [],
            "probe99": [],
            "pressure": []
        })
        columns = detect_temperature_columns(df)
        assert "probe1" in columns
        assert "probe2" in columns
        assert "probe99" in columns
        assert "pressure" not in columns
        assert len(columns) == 3
    
    def test_channel_patterns(self):
        """Test channel patterns (ch1_temp, ch2temp, etc.)."""
        df = pd.DataFrame({
            "timestamp": [],
            "ch1_temp": [],
            "ch2temp": [],
            "ch10_temperature": [],
            "ch1_humidity": []
        })
        columns = detect_temperature_columns(df)
        assert "ch1_temp" in columns
        assert "ch2temp" in columns
        assert "ch10_temperature" in columns
        assert "ch1_humidity" not in columns  # Should not match - no 'temp' suffix
        assert len(columns) == 3
    
    def test_celsius_patterns(self):
        """Test celsius and degree patterns."""
        df = pd.DataFrame({
            "timestamp": [],
            "sensor_°c": [],
            "temp_celsius": [],
            "reading_°c": [],
            "pressure_bar": []
        })
        columns = detect_temperature_columns(df)
        assert "sensor_°c" in columns
        assert "temp_celsius" in columns
        assert "reading_°c" in columns
        assert "pressure_bar" not in columns
        assert len(columns) == 3
    
    def test_generic_patterns(self):
        """Test generic value/reading patterns."""
        df = pd.DataFrame({
            "timestamp": [],
            "value": [],
            "reading": [],
            "sensor_value": [],
            "temp_reading": [],
            "status": []
        })
        columns = detect_temperature_columns(df)
        assert "value" in columns
        assert "reading" in columns
        assert "sensor_value" in columns  
        assert "temp_reading" in columns
        assert "status" not in columns
        assert len(columns) == 4
    
    def test_case_insensitive_matching(self):
        """Test case-insensitive pattern matching."""
        df = pd.DataFrame({
            "timestamp": [],
            "TEMP_1": [],
            "Temperature": [],
            "T1": [],
            "PROBE1": [],
            "CH1_TEMP": [],
            "SENSOR_°C": [],
            "VALUE": [],
            "Reading": []
        })
        columns = detect_temperature_columns(df)
        assert "TEMP_1" in columns
        assert "Temperature" in columns
        assert "T1" in columns
        assert "PROBE1" in columns
        assert "CH1_TEMP" in columns
        assert "SENSOR_°C" in columns
        assert "VALUE" in columns
        assert "Reading" in columns
        assert len(columns) == 8
    
    def test_mixed_patterns(self):
        """Test mixed temperature and non-temperature columns."""
        df = pd.DataFrame({
            "timestamp": [],
            "temp_1": [],
            "humidity_1": [],
            "t2": [],
            "pressure_bar": [],
            "probe3": [],
            "flow_rate": [],
            "ch4_temp": [],
            "status": [],
            "reading": [],
            "alarm": []
        })
        columns = detect_temperature_columns(df)
        temp_cols = {"temp_1", "t2", "probe3", "ch4_temp", "reading"}
        non_temp_cols = {"humidity_1", "pressure_bar", "flow_rate", "status", "alarm"}
        
        for col in temp_cols:
            assert col in columns, f"Expected temperature column '{col}' not detected"
        
        for col in non_temp_cols:
            assert col not in columns, f"Non-temperature column '{col}' incorrectly detected"
        
        assert len(columns) == len(temp_cols)
    
    def test_no_temperature_columns(self):
        """Test behavior with no temperature columns."""
        df = pd.DataFrame({
            "timestamp": [],
            "humidity": [],
            "pressure": [],
            "flow_rate": [],
            "status": []
        })
        columns = detect_temperature_columns(df)
        assert len(columns) == 0
    
    def test_error_on_missing_temp_columns(self):
        """Test that missing temperature columns raises RequiredSignalMissingError."""
        # Create coldchain spec
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "test_missing_temp"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        # Create data without temperature columns
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        data = pd.DataFrame({
            "timestamp": timestamps,
            "humidity_1": [60.0] * 100,
            "pressure_1": [101.3] * 100,
            "flow_rate": [2.5] * 100
        })
        
        # Should raise RequiredSignalMissingError (not DecisionError)
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_coldchain_storage(data, spec)
        
        # Check error details
        error = exc_info.value
        assert "temperature" in error.missing_signals
        assert "humidity_1" in error.available_signals
        assert "pressure_1" in error.available_signals
        assert "flow_rate" in error.available_signals
        assert "timestamp" not in error.available_signals  # Should exclude timestamp
    
    def test_actual_csv_structure(self):
        """Test with actual CSV file structure from fixtures."""
        # Simulate the structure from coldchain_storage_pass.csv
        timestamps = pd.date_range(
            start="2024-01-15T00:00:00+00:00", periods=10, freq="5min", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [5.1] * 10,
            "temp_2": [4.9] * 10
        })
        
        columns = detect_temperature_columns(df)
        assert "temp_1" in columns
        assert "temp_2" in columns
        assert len(columns) == 2
        
        # Now test that validation works
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "test_actual_csv"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            }
        })
        
        # Should not raise an error now
        result = validate_coldchain_storage(df, spec)
        assert result is not None


if __name__ == "__main__":
    # Run tests manually
    test_class = TestTemperatureColumnDetection()
    
    print("Testing basic temp patterns...")
    test_class.test_basic_temp_patterns()
    print("✓ PASS")
    
    print("Testing numbered sensor patterns...")
    test_class.test_numbered_sensor_patterns()
    print("✓ PASS")
    
    print("Testing probe patterns...")
    test_class.test_probe_patterns()
    print("✓ PASS")
    
    print("Testing channel patterns...")
    test_class.test_channel_patterns()
    print("✓ PASS")
    
    print("Testing celsius patterns...")
    test_class.test_celsius_patterns()
    print("✓ PASS")
    
    print("Testing generic patterns...")
    test_class.test_generic_patterns()
    print("✓ PASS")
    
    print("Testing case insensitive matching...")
    test_class.test_case_insensitive_matching()
    print("✓ PASS")
    
    print("Testing mixed patterns...")
    test_class.test_mixed_patterns()
    print("✓ PASS")
    
    print("Testing no temperature columns...")
    test_class.test_no_temperature_columns()
    print("✓ PASS")
    
    print("Testing actual CSV structure...")
    test_class.test_actual_csv_structure()
    print("✓ PASS")
    
    print("All temperature detection tests passed!")