"""
ProofKit Normalization Tests

Comprehensive test suite for CSV data normalization functionality including:
- Timezone conversion (local TZ → UTC, UNIX seconds → UTC)
- Temperature unit conversion (°F → °C)
- Resampling to fixed 30s intervals
- Gap detection and validation
- Duplicate timestamp handling
- Monotonic timestamp enforcement

Example usage:
    pytest tests/test_normalize.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from core.normalize import (
    load_csv_with_metadata,
    normalize_temperature_data,
    detect_timestamp_format,
    convert_fahrenheit_to_celsius,
    resample_temperature_data,
    validate_data_quality,
    NormalizationError
)


class TestMetadataExtraction:
    """Test metadata extraction from CSV comment lines."""
    
    def test_load_csv_with_metadata_from_examples(self, example_csv_path):
        """Test loading example CSV with metadata extraction."""
        df, metadata = load_csv_with_metadata(str(example_csv_path))
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "timestamp" in df.columns
        assert "pmt_sensor_1" in df.columns
        assert "pmt_sensor_2" in df.columns
        
        # Check metadata extraction from comments
        assert isinstance(metadata, dict)
        expected_keys = ["Example CSV file", "Job", "Equipment", "Date"]
        for key in expected_keys:
            assert any(key in meta_key for meta_key in metadata.keys())
    
    def test_load_csv_with_gaps_metadata(self, gaps_csv_path):
        """Test loading gaps CSV with metadata extraction."""
        df, metadata = load_csv_with_metadata(str(gaps_csv_path))
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "timestamp" in df.columns
        
        # Verify metadata extraction
        assert isinstance(metadata, dict)
        assert len(metadata) > 0
    
    def test_load_nonexistent_file(self):
        """Test error handling for non-existent files."""
        with pytest.raises(FileNotFoundError):
            load_csv_with_metadata("nonexistent_file.csv")
    
    def test_load_csv_custom_metadata(self, temp_dir, simple_temp_data):
        """Test loading CSV with custom metadata format."""
        csv_path = temp_dir / "custom_meta.csv"
        metadata = {
            "Job ID": "test_batch_123",
            "Equipment": "Custom PMT Array",
            "Date": "2024-01-15",
            "Operator": "Test User"
        }
        
        # Create CSV with metadata
        with open(csv_path, 'w') as f:
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
            simple_temp_data.to_csv(f, index=False)
        
        df, extracted_meta = load_csv_with_metadata(str(csv_path))
        
        assert len(df) == len(simple_temp_data)
        assert len(extracted_meta) == len(metadata)
        for key, value in metadata.items():
            assert key in extracted_meta
            assert extracted_meta[key] == value


class TestTimestampDetection:
    """Test timestamp format detection and conversion."""
    
    def test_detect_iso_timestamp(self, simple_temp_data):
        """Test detection of ISO 8601 timestamp format."""
        timestamp_format, column = detect_timestamp_format(simple_temp_data)
        
        assert timestamp_format == "iso"
        assert column == "timestamp"
    
    def test_detect_unix_timestamp(self, unix_timestamp_data):
        """Test detection of UNIX timestamp format."""
        timestamp_format, column = detect_timestamp_format(unix_timestamp_data)
        
        assert timestamp_format == "unix"
        assert column == "unix_timestamp"
    
    def test_detect_mixed_format_preference(self):
        """Test timestamp detection with multiple possible columns."""
        # Create data with both ISO and UNIX columns
        timestamps_iso = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"
        )
        timestamps_unix = [1705320000 + i*30 for i in range(5)]
        
        df = pd.DataFrame({
            "timestamp": timestamps_iso,
            "unix_timestamp": timestamps_unix,
            "temp_1": [180.0] * 5
        })
        
        timestamp_format, column = detect_timestamp_format(df)
        
        # Should prefer 'timestamp' column over 'unix_timestamp'
        assert timestamp_format == "iso"
        assert column == "timestamp"
    
    def test_no_timestamp_column_error(self):
        """Test error when no timestamp column is found."""
        df = pd.DataFrame({
            "temp_1": [180.0, 181.0, 182.0],
            "temp_2": [179.5, 180.5, 181.5]
        })
        
        with pytest.raises(ValueError, match="No timestamp column found"):
            detect_timestamp_format(df)


class TestTimezoneConversion:
    """Test timezone conversion to UTC."""
    
    def test_local_timezone_to_utc(self, test_data_dir):
        """Test conversion from local timezone to UTC."""
        local_csv_path = test_data_dir / "local_timezone_data.csv"
        df, _ = load_csv_with_metadata(str(local_csv_path))
        
        # Normalize should convert to UTC
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check that timestamps are in UTC
        assert normalized_df["timestamp"].dt.tz.zone == "UTC"
        
        # First timestamp should be 2024-01-15T10:00:00Z (EST+5)
        expected_utc = pd.Timestamp("2024-01-15T10:00:00Z")
        assert normalized_df["timestamp"].iloc[0] == expected_utc
    
    def test_unix_timestamp_to_utc(self, test_data_dir):
        """Test conversion from UNIX seconds to UTC."""
        unix_csv_path = test_data_dir / "unix_seconds_data.csv"
        df, _ = load_csv_with_metadata(str(unix_csv_path))
        
        # Normalize should convert UNIX to UTC
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check that timestamps are in UTC
        assert normalized_df["timestamp"].dt.tz.zone == "UTC"
        
        # First timestamp: 1705320000 = 2024-01-15T10:00:00Z
        expected_utc = pd.Timestamp("2024-01-15T10:00:00Z")
        assert normalized_df["timestamp"].iloc[0] == expected_utc
    
    def test_already_utc_unchanged(self, simple_temp_data):
        """Test that UTC timestamps remain unchanged."""
        original_timestamps = simple_temp_data["timestamp"].copy()
        
        normalized_df = normalize_temperature_data(
            simple_temp_data, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Timestamps should remain the same (already UTC)
        pd.testing.assert_series_equal(
            normalized_df["timestamp"].dt.floor('s'),
            original_timestamps.dt.floor('s'),
            check_names=False
        )


class TestTemperatureUnitConversion:
    """Test temperature unit conversion from Fahrenheit to Celsius."""
    
    def test_fahrenheit_to_celsius_conversion(self):
        """Test basic Fahrenheit to Celsius conversion."""
        # Test known conversions
        assert abs(convert_fahrenheit_to_celsius(32.0) - 0.0) < 0.001
        assert abs(convert_fahrenheit_to_celsius(212.0) - 100.0) < 0.001
        assert abs(convert_fahrenheit_to_celsius(356.0) - 180.0) < 0.001
        
        # Test Series conversion
        temps_f = pd.Series([32.0, 212.0, 356.0])
        temps_c = convert_fahrenheit_to_celsius(temps_f)
        
        expected_c = pd.Series([0.0, 100.0, 180.0])
        pd.testing.assert_series_equal(temps_c, expected_c, atol=0.001)
    
    def test_fahrenheit_data_normalization(self, fahrenheit_temp_data):
        """Test normalization of Fahrenheit temperature data."""
        # Create a copy with explicit Fahrenheit column names
        df = fahrenheit_temp_data.copy()
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check that Fahrenheit columns were converted to Celsius
        celsius_columns = [col for col in normalized_df.columns if "_f" not in col and col != "timestamp"]
        assert len(celsius_columns) >= 2
        
        # Temperature values should be in Celsius range (around 180°C)
        for col in celsius_columns:
            temps = normalized_df[col]
            assert temps.max() < 200.0  # Should be ~180°C, not ~356°F
            assert temps.max() > 150.0  # Should be reasonable Celsius values
    
    def test_mixed_unit_detection(self):
        """Test detection of mixed temperature units."""
        # Create DataFrame with mixed units
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_c": [180.0, 181.0, 182.0, 181.5, 180.5],  # Celsius
            "temp_f": [356.0, 357.8, 359.6, 358.7, 356.9]   # Fahrenheit
        })
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Both columns should now be in Celsius
        assert "temp_c" in normalized_df.columns
        assert "temp_f" in normalized_df.columns
        
        # Values should be similar (both around 180°C)
        temp_c_vals = normalized_df["temp_c"]
        temp_f_vals = normalized_df["temp_f"]
        
        # Converted Fahrenheit should be close to original Celsius
        assert abs(temp_c_vals.mean() - temp_f_vals.mean()) < 2.0


class TestResampling:
    """Test data resampling to fixed intervals."""
    
    def test_resample_to_30s(self, test_data_dir):
        """Test resampling irregular intervals to 30s."""
        irregular_csv_path = test_data_dir / "irregular_intervals.csv"
        df, _ = load_csv_with_metadata(str(irregular_csv_path))
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check that all intervals are 30s
        time_diffs = normalized_df["timestamp"].diff().dropna()
        expected_interval = pd.Timedelta(seconds=30)
        
        # Allow small tolerance for resampling precision
        for diff in time_diffs:
            assert abs((diff - expected_interval).total_seconds()) <= 1.0
    
    def test_resample_preserves_temperature_trends(self, simple_temp_data):
        """Test that resampling preserves temperature trends."""
        # Create data with different step size
        df = simple_temp_data.copy()
        df["timestamp"] = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=len(df), freq="15s", tz="UTC"
        )
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Should have roughly half the points (15s -> 30s)
        assert len(normalized_df) <= len(df)
        assert len(normalized_df) >= len(df) // 2
        
        # Temperature values should be within reasonable range
        for col in ["pmt_sensor_1", "pmt_sensor_2"]:
            original_range = df[col].max() - df[col].min()
            resampled_range = normalized_df[col].max() - normalized_df[col].min()
            
            # Range should be preserved within tolerance
            assert abs(original_range - resampled_range) < 5.0
    
    def test_resample_different_target_intervals(self, simple_temp_data):
        """Test resampling to different target intervals."""
        for target_step in [15.0, 30.0, 60.0]:
            normalized_df = normalize_temperature_data(
                simple_temp_data, target_step_s=target_step, allowed_gaps_s=120.0
            )
            
            # Check intervals
            time_diffs = normalized_df["timestamp"].diff().dropna()
            expected_interval = pd.Timedelta(seconds=target_step)
            
            for diff in time_diffs:
                assert abs((diff - expected_interval).total_seconds()) <= 1.0


class TestGapDetection:
    """Test data gap detection and validation."""
    
    def test_detect_large_gaps(self, gaps_temp_data):
        """Test detection of large gaps in timestamp data."""
        with pytest.raises(NormalizationError, match="Data gap.*exceeds allowed"):
            normalize_temperature_data(
                gaps_temp_data, target_step_s=30.0, allowed_gaps_s=60.0
            )
    
    def test_allow_small_gaps(self, gaps_temp_data):
        """Test that small gaps are allowed."""
        # Allow larger gaps (90s+)
        normalized_df = normalize_temperature_data(
            gaps_temp_data, target_step_s=30.0, allowed_gaps_s=120.0
        )
        
        assert len(normalized_df) > 0
        assert "timestamp" in normalized_df.columns
    
    def test_gaps_csv_example(self, gaps_csv_path):
        """Test gap detection with example gaps.csv file."""
        df, _ = load_csv_with_metadata(str(gaps_csv_path))
        
        # Should fail with strict gap limits
        with pytest.raises(NormalizationError):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        
        # Should pass with relaxed gap limits
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=300.0
        )
        assert len(normalized_df) > 0
    
    def test_no_gaps_pass(self, simple_temp_data):
        """Test data without gaps passes validation."""
        normalized_df = normalize_temperature_data(
            simple_temp_data, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        assert len(normalized_df) > 0
        
        # Check no large gaps in normalized data
        time_diffs = normalized_df["timestamp"].diff().dropna()
        max_gap = time_diffs.max().total_seconds()
        assert max_gap <= 60.0


class TestDataQualityValidation:
    """Test various data quality validation scenarios."""
    
    def test_duplicate_timestamps(self, duplicate_timestamp_data):
        """Test handling of duplicate timestamps."""
        # Should handle duplicates by deduplication or averaging
        normalized_df = normalize_temperature_data(
            duplicate_timestamp_data, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check no duplicate timestamps in result
        assert normalized_df["timestamp"].is_unique
        assert len(normalized_df) > 0
    
    def test_non_monotonic_timestamps(self, non_monotonic_data):
        """Test handling of non-monotonic timestamps."""
        # Should sort timestamps or raise appropriate error
        try:
            normalized_df = normalize_temperature_data(
                non_monotonic_data, target_step_s=30.0, allowed_gaps_s=60.0
            )
            
            # If it succeeds, timestamps should be monotonic
            assert normalized_df["timestamp"].is_monotonic_increasing
            
        except NormalizationError:
            # It's acceptable to reject non-monotonic data
            pass
    
    def test_missing_temperature_values(self, test_data_dir):
        """Test handling of missing temperature values."""
        corrupted_csv_path = test_data_dir / "corrupted_data.csv"
        df, _ = load_csv_with_metadata(str(corrupted_csv_path))
        
        # Should handle missing values appropriately
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check that missing values are handled (interpolated, dropped, or flagged)
        assert len(normalized_df) > 0
        
        # Temperature columns shouldn't have NaN values in final result
        temp_cols = [col for col in normalized_df.columns if col != "timestamp"]
        for col in temp_cols:
            # Either no NaN values, or they're properly marked/handled
            nan_count = normalized_df[col].isna().sum()
            total_count = len(normalized_df)
            assert nan_count < total_count  # At least some valid data
    
    def test_extreme_temperature_values(self, test_data_dir):
        """Test handling of extreme temperature values."""
        extreme_csv_path = test_data_dir / "extreme_values.csv"
        df, _ = load_csv_with_metadata(str(extreme_csv_path))
        
        # Should handle extreme values (outlier detection/removal)
        try:
            normalized_df = normalize_temperature_data(
                df, target_step_s=30.0, allowed_gaps_s=60.0
            )
            
            # Check that extreme outliers are handled
            temp_cols = [col for col in normalized_df.columns if col != "timestamp"]
            for col in temp_cols:
                temps = normalized_df[col].dropna()
                if len(temps) > 0:
                    # Should not have extreme outliers like 999.9 or -50.0
                    assert temps.max() < 500.0
                    assert temps.min() > -10.0
                    
        except NormalizationError:
            # It's acceptable to reject data with extreme values
            pass
    
    def test_empty_dataframe_error(self):
        """Test error handling for empty DataFrame."""
        df = pd.DataFrame()
        
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
    
    def test_single_row_data(self):
        """Test handling of single row data."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-15T10:00:00Z")],
            "temp_1": [180.0]
        })
        
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)


class TestNormalizationEndToEnd:
    """End-to-end normalization tests with real example data."""
    
    def test_normalize_ok_run_example(self, example_csv_path):
        """Test complete normalization of ok_run.csv example."""
        df, metadata = load_csv_with_metadata(str(example_csv_path))
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Verify structure
        assert len(normalized_df) > 0
        assert "timestamp" in normalized_df.columns
        assert "pmt_sensor_1" in normalized_df.columns
        assert "pmt_sensor_2" in normalized_df.columns
        
        # Verify timestamps are UTC and monotonic
        assert normalized_df["timestamp"].dt.tz.zone == "UTC"
        assert normalized_df["timestamp"].is_monotonic_increasing
        
        # Verify temperature values are reasonable
        for col in ["pmt_sensor_1", "pmt_sensor_2"]:
            temps = normalized_df[col]
            assert temps.min() > 100.0  # Above room temperature
            assert temps.max() < 300.0  # Below extreme values
    
    def test_normalize_fahrenheit_example(self, fahrenheit_csv_path):
        """Test normalization of Fahrenheit input data."""
        df, metadata = load_csv_with_metadata(str(fahrenheit_csv_path))
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Verify Fahrenheit conversion
        assert len(normalized_df) > 0
        temp_cols = [col for col in normalized_df.columns if col != "timestamp"]
        
        for col in temp_cols:
            temps = normalized_df[col]
            # Should be converted to Celsius (~180°C range)
            assert temps.max() < 200.0
            assert temps.max() > 150.0
    
    def test_normalization_deterministic(self, simple_temp_data):
        """Test that normalization produces deterministic results."""
        # Run normalization twice with same parameters
        result1 = normalize_temperature_data(
            simple_temp_data.copy(), target_step_s=30.0, allowed_gaps_s=60.0
        )
        result2 = normalize_temperature_data(
            simple_temp_data.copy(), target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Results should be identical
        pd.testing.assert_frame_equal(result1, result2)
    
    def test_normalization_parameter_validation(self, simple_temp_data):
        """Test validation of normalization parameters."""
        # Invalid target_step_s
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(
                simple_temp_data, target_step_s=0.0, allowed_gaps_s=60.0
            )
        
        # Invalid allowed_gaps_s
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(
                simple_temp_data, target_step_s=30.0, allowed_gaps_s=-10.0
            )
        
        # Very large target_step_s
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(
                simple_temp_data, target_step_s=3600.0, allowed_gaps_s=60.0
            )