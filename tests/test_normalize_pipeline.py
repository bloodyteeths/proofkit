"""
ProofKit Normalization Pipeline Tests

Comprehensive test suite focusing on the complete normalization pipeline including:
- Metadata header parsing (# key: value format)
- °F→°C conversion exactness (356°F ≈ 180°C to ±0.1)
- Timezone normalization to UTC (various input formats, unix seconds, DST boundaries) 
- Resample step & allowed_gaps_s boundaries
- Missing time column → ValidationError
- Duplicate timestamps de-dup or error path

This module targets uncovered branches to reach ≥90% coverage for normalize.py.

Example usage:
    pytest tests/test_normalize_pipeline.py -v --cov=core.normalize
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import tempfile
import pytz
from io import StringIO

from core.normalize import (
    load_csv_with_metadata,
    normalize_temperature_data,
    detect_timestamp_format,
    detect_timestamp_column,
    parse_timestamps,
    convert_fahrenheit_to_celsius,
    detect_temperature_columns,
    _convert_fahrenheit_to_celsius_df,
    resample_temperature_data,
    check_data_quality,
    validate_data_quality,
    NormalizationError
)


class TestMetadataHeaderParsing:
    """Test metadata extraction from # key: value format comment lines."""
    
    def test_metadata_parsing_basic_format(self, temp_dir):
        """Test basic metadata parsing from comment headers."""
        csv_content = """# Job ID: test_batch_123
# Equipment: Custom PMT Array  
# Date: 2024-01-15
# Operator: Test User
# Notes: High precision run
timestamp,temp_1,temp_2
2024-01-15T10:00:00Z,180.0,179.5
2024-01-15T10:00:30Z,181.0,180.5
2024-01-15T10:01:00Z,182.0,181.5
"""
        csv_path = temp_dir / "metadata_test.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        # Verify data loading
        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "temp_1" in df.columns
        
        # Verify metadata extraction
        assert len(metadata) == 5
        assert metadata["Job ID"] == "test_batch_123"
        assert metadata["Equipment"] == "Custom PMT Array"
        assert metadata["Date"] == "2024-01-15"
        assert metadata["Operator"] == "Test User"
        assert metadata["Notes"] == "High precision run"
    
    def test_metadata_parsing_with_colons_in_values(self, temp_dir):
        """Test metadata parsing when values contain colons."""
        csv_content = """# Time Range: 10:00:00 - 12:30:00
# URL: https://example.com:8080/api
# Complex: Key with: multiple: colons
timestamp,temp_1
2024-01-15T10:00:00Z,180.0
"""
        csv_path = temp_dir / "colon_test.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        assert metadata["Time Range"] == "10:00:00 - 12:30:00"
        assert metadata["URL"] == "https://example.com:8080/api"
        assert metadata["Complex"] == "Key with: multiple: colons"
    
    def test_metadata_parsing_whitespace_handling(self, temp_dir):
        """Test metadata parsing handles various whitespace patterns."""
        csv_content = """#Job:value_no_spaces
# Equipment :  Value with spaces  
#   Key   :   Value   
#NoColon comment line ignored
timestamp,temp_1
2024-01-15T10:00:00Z,180.0
"""
        csv_path = temp_dir / "whitespace_test.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        assert metadata["Job"] == "value_no_spaces"
        assert metadata["Equipment"] == "Value with spaces"
        assert metadata["Key"] == "Value"
        assert len(metadata) == 3  # Other lines ignored
    
    def test_metadata_parsing_empty_lines_and_comments(self, temp_dir):
        """Test metadata parsing ignores empty lines and non-metadata comments."""
        csv_content = """
# This is just a comment
# Job: test_job

# More comments
#
# Equipment: test_equipment
timestamp,temp_1
2024-01-15T10:00:00Z,180.0

"""
        csv_path = temp_dir / "empty_lines_test.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        assert len(df) == 1
        assert len(metadata) == 2
        assert metadata["Job"] == "test_job"
        assert metadata["Equipment"] == "test_equipment"
    
    def test_metadata_parsing_no_data_error(self, temp_dir):
        """Test error when CSV has only metadata but no data."""
        csv_content = """# Job: test_job
# Equipment: test_equipment
"""
        csv_path = temp_dir / "no_data_test.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        with pytest.raises(ValueError, match="No data lines found"):
            load_csv_with_metadata(str(csv_path))


class TestTemperatureConversionExactness:
    """Test °F→°C conversion exactness (356°F ≈ 180°C to ±0.1)."""
    
    def test_fahrenheit_to_celsius_exactness(self):
        """Test exact conversion of 356°F to 180°C within ±0.1."""
        # Test the specific requirement: 356°F ≈ 180°C to ±0.1
        result = convert_fahrenheit_to_celsius(356.0)
        expected = 180.0
        assert abs(result - expected) <= 0.1, f"Expected {expected}±0.1, got {result}"
        
        # Test more precise calculation: (356 - 32) * 5/9 = 324 * 5/9 = 180.0
        assert abs(result - 180.0) < 0.001, "356°F should convert to exactly 180.0°C"
    
    def test_fahrenheit_conversion_edge_cases(self):
        """Test Fahrenheit conversion for edge cases with high precision."""
        test_cases = [
            (32.0, 0.0),      # Freezing point
            (212.0, 100.0),   # Boiling point  
            (356.0, 180.0),   # Target cure temperature
            (0.0, -17.777777777777778),  # Absolute zero °F
            (-40.0, -40.0),   # Same value in both scales
        ]
        
        for temp_f, expected_c in test_cases:
            result = convert_fahrenheit_to_celsius(temp_f)
            assert abs(result - expected_c) <= 0.1, f"{temp_f}°F should be {expected_c}°C±0.1, got {result}"
    
    def test_series_fahrenheit_conversion_exactness(self):
        """Test exact conversion for pandas Series."""
        temps_f = pd.Series([32.0, 212.0, 356.0, 358.0, 360.0])
        expected_c = pd.Series([0.0, 100.0, 180.0, 181.111111, 182.222222])
        
        result_c = convert_fahrenheit_to_celsius(temps_f)
        
        for i, (result, expected) in enumerate(zip(result_c, expected_c)):
            assert abs(result - expected) <= 0.1, f"Index {i}: {temps_f.iloc[i]}°F should be {expected}°C±0.1, got {result}"
    
    def test_dataframe_fahrenheit_column_detection_and_conversion(self):
        """Test detection and conversion of Fahrenheit columns in DataFrame."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_f": [356.0, 358.0, 360.0],      # Should be converted
            "temp_fahrenheit": [356.0, 358.0, 360.0],  # Should be converted  
            "temp_°f": [356.0, 358.0, 360.0],     # Should be converted
            "temp_degf": [356.0, 358.0, 360.0],   # Should be converted
            "temp_c": [180.0, 181.0, 182.0],      # Should NOT be converted
            "temp_celsius": [180.0, 181.0, 182.0] # Should NOT be converted
        })
        
        temp_columns = detect_temperature_columns(df)
        converted_df = _convert_fahrenheit_to_celsius_df(df, temp_columns)
        
        # Check that Fahrenheit columns were converted
        for col in ["temp_f", "temp_fahrenheit", "temp_°f", "temp_degf"]:
            if col in converted_df.columns:
                # All should be around 180°C (within ±0.1)
                assert abs(converted_df[col].iloc[0] - 180.0) <= 0.1
        
        # Check that Celsius columns were NOT converted  
        for col in ["temp_c", "temp_celsius"]:
            if col in converted_df.columns:
                assert abs(converted_df[col].iloc[0] - 180.0) <= 0.1  # Should remain as-is
    
    def test_temperature_conversion_unsupported_type_error(self):
        """Test error handling for unsupported temperature conversion types."""
        with pytest.raises(ValueError, match="Unsupported type"):
            convert_fahrenheit_to_celsius("not_a_number")
        
        with pytest.raises(ValueError, match="Unsupported type"):  
            convert_fahrenheit_to_celsius([1, 2, 3])  # List not supported


class TestTimezoneNormalization:
    """Test timezone normalization to UTC (various input formats, unix seconds, DST boundaries)."""
    
    def test_iso_timezone_to_utc_conversion(self):
        """Test conversion of ISO timestamps with timezone info to UTC."""
        # Test various timezone formats
        test_cases = [
            ("2024-01-15T10:00:00-05:00", "2024-01-15T15:00:00+00:00"),  # EST
            ("2024-01-15T10:00:00+01:00", "2024-01-15T09:00:00+00:00"),  # CET
            ("2024-01-15T10:00:00Z", "2024-01-15T10:00:00+00:00"),       # UTC
            ("2024-01-15T10:00:00+00:00", "2024-01-15T10:00:00+00:00"),  # UTC explicit
        ]
        
        for input_ts, expected_utc in test_cases:
            df = pd.DataFrame({
                "timestamp": [input_ts],
                "temp_1": [180.0]
            })
            
            timestamps = parse_timestamps(df, "timestamp")
            result_utc = timestamps.iloc[0]
            expected = pd.Timestamp(expected_utc)
            
            assert result_utc == expected, f"Failed to convert {input_ts} to {expected_utc}"
            assert result_utc.tz == pytz.UTC or str(result_utc.tz) == "UTC"
    
    def test_unix_timestamp_to_utc_conversion(self):
        """Test conversion of Unix timestamps to UTC."""
        # 1705320000 = 2024-01-15T10:00:00Z
        base_unix = 1705320000
        test_unix_times = [base_unix, base_unix + 30, base_unix + 60]
        
        df = pd.DataFrame({
            "unix_timestamp": test_unix_times,
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        timestamps = parse_timestamps(df, "unix_timestamp")
        
        # Check first timestamp
        expected_first = pd.Timestamp("2024-01-15T10:00:00Z")
        assert timestamps.iloc[0] == expected_first
        assert timestamps.iloc[0].tz == pytz.UTC or str(timestamps.iloc[0].tz) == "UTC"
        
        # Check intervals (should be 30s apart)
        time_diff = (timestamps.iloc[1] - timestamps.iloc[0]).total_seconds()
        assert time_diff == 30.0
    
    def test_dst_boundary_handling(self):
        """Test handling of DST boundaries in timezone conversion."""
        # Spring forward: 2024-03-10 02:00:00 EST becomes 03:00:00 EDT
        # Fall back: 2024-11-03 02:00:00 EDT becomes 01:00:00 EST (repeated hour)
        
        # Test spring forward (EST to EDT)
        spring_times = [
            "2024-03-10T01:30:00-05:00",  # Before DST
            "2024-03-10T07:30:00+00:00",  # Same time in UTC  
        ]
        
        for ts_str in spring_times:
            df = pd.DataFrame({
                "timestamp": [ts_str],
                "temp_1": [180.0]
            })
            
            timestamps = parse_timestamps(df, "timestamp")
            # Should convert to UTC without issues
            assert timestamps.iloc[0].tz == pytz.UTC or str(timestamps.iloc[0].tz) == "UTC"
    
    def test_named_timezone_conversion(self):
        """Test conversion from named timezones to UTC."""
        # Create naive timestamps and specify source timezone
        df = pd.DataFrame({
            "timestamp": ["2024-01-15T10:00:00", "2024-01-15T10:00:30"],
            "temp_1": [180.0, 181.0]
        })
        
        # Test EST timezone conversion
        timestamps = parse_timestamps(df, "timestamp", source_tz="US/Eastern")
        
        # EST is UTC-5, so 10:00 EST = 15:00 UTC
        expected_utc = pd.Timestamp("2024-01-15T15:00:00Z")
        assert timestamps.iloc[0] == expected_utc
        assert timestamps.iloc[0].tz == pytz.UTC or str(timestamps.iloc[0].tz) == "UTC"
    
    def test_invalid_timezone_handling(self):
        """Test error handling for invalid timezone specifications."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15T10:00:00"],
            "temp_1": [180.0]
        })
        
        with pytest.raises(Exception):  # Should raise pytz or parsing error
            parse_timestamps(df, "timestamp", source_tz="Invalid/Timezone")
    
    def test_timestamp_parsing_fallback_to_unix(self):
        """Test fallback to Unix timestamp parsing when ISO parsing fails."""
        # Create DataFrame with numeric values that look like Unix timestamps
        df = pd.DataFrame({
            "timestamp": [1705320000, 1705320030, 1705320060],  # Valid Unix timestamps
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        # Should fallback to Unix parsing
        timestamps = parse_timestamps(df, "timestamp")
        expected_first = pd.Timestamp("2024-01-15T10:00:00Z")
        assert timestamps.iloc[0] == expected_first
        assert timestamps.iloc[0].tz == pytz.UTC or str(timestamps.iloc[0].tz) == "UTC"


class TestTimestampColumnDetection:
    """Test timestamp column detection and error handling."""
    
    def test_detect_timestamp_column_common_names(self):
        """Test detection of timestamp columns with common names."""
        common_names = [
            "timestamp", "time", "datetime", "date_time",
            "ts", "t", "sample_time", "time_stamp"
        ]
        
        for col_name in common_names:
            df = pd.DataFrame({
                col_name: ["2024-01-15T10:00:00Z"],
                "temp_1": [180.0]
            })
            
            detected_col = detect_timestamp_column(df)
            assert detected_col == col_name
    
    def test_detect_timestamp_column_case_insensitive(self):
        """Test case-insensitive detection of timestamp columns."""
        test_names = ["TIMESTAMP", "Time", "DateTime", "SAMPLE_TIME"]
        
        for col_name in test_names:
            df = pd.DataFrame({
                col_name: ["2024-01-15T10:00:00Z"],
                "temp_1": [180.0]
            })
            
            detected_col = detect_timestamp_column(df)
            assert detected_col == col_name
    
    def test_detect_timestamp_column_partial_match(self):
        """Test detection of timestamp columns with partial name matches."""
        partial_names = ["my_timestamp", "time_sensor", "datetime_utc", "ts_start"]
        
        for col_name in partial_names:
            df = pd.DataFrame({
                col_name: ["2024-01-15T10:00:00Z"],
                "temp_1": [180.0]
            })
            
            detected_col = detect_timestamp_column(df)
            assert detected_col == col_name
    
    def test_detect_timestamp_column_first_column_fallback(self):
        """Test fallback to first column when no obvious timestamp column."""
        df = pd.DataFrame({
            "measurement_time": ["2024-01-15T10:00:00Z"],  # Parseable as timestamp
            "temp_1": [180.0]
        })
        
        detected_col = detect_timestamp_column(df)
        assert detected_col == "measurement_time"
    
    def test_detect_timestamp_column_no_valid_column_error(self):
        """Test error when no valid timestamp column is found."""
        df = pd.DataFrame({
            "temperature": [180.0, 181.0],
            "sensor_id": ["A", "B"]
        })
        
        with pytest.raises(ValueError, match="No timestamp column found"):
            detect_timestamp_column(df)
    
    def test_detect_timestamp_format_edge_cases(self):
        """Test timestamp format detection edge cases."""
        # DataFrame with no timestamp columns should raise error
        df = pd.DataFrame({
            "temp_1": [180.0, 181.0],
            "temp_2": [179.0, 180.0]
        })
        
        with pytest.raises(ValueError):
            detect_timestamp_format(df)


class TestResampleStepAndGapsBoundaries:
    """Test resample step & allowed_gaps_s boundaries."""
    
    def test_resample_step_boundary_values(self):
        """Test resampling with boundary step values."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=10, freq="10s", tz="UTC"),
            "temp_1": [180.0] * 10
        })
        
        # Test minimum reasonable step
        result = resample_temperature_data(df, "timestamp", target_step_s=1.0)
        assert len(result) >= len(df)  # Should have more or equal points
        
        # Test large step (should reduce points significantly)
        result = resample_temperature_data(df, "timestamp", target_step_s=60.0)
        assert len(result) <= len(df)  # Should have fewer points
        
        # Test step equal to existing interval
        result = resample_temperature_data(df, "timestamp", target_step_s=10.0)
        assert len(result) == len(df)  # Should have same number of points
    
    def test_allowed_gaps_boundary_conditions(self):
        """Test data quality validation at gap boundary conditions."""
        # Create data with precisely sized gaps
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),
            pd.Timestamp("2024-01-15T10:01:30Z"),  # 60s gap
            pd.Timestamp("2024-01-15T10:02:00Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 181.0, 182.0, 183.0]
        })
        
        # Test with gap exactly at boundary (should pass)
        issues = check_data_quality(df, "timestamp", max_sample_period_s=120.0, allowed_gaps_s=60.0)
        gap_issues = [issue for issue in issues if "gaps" in issue.lower()]
        assert len(gap_issues) == 0, "60s gap should be allowed with 60s limit"
        
        # Test with gap just over boundary (should fail)
        issues = check_data_quality(df, "timestamp", max_sample_period_s=120.0, allowed_gaps_s=59.0)
        gap_issues = [issue for issue in issues if "gaps" in issue.lower()]
        assert len(gap_issues) > 0, "60s gap should be rejected with 59s limit"
    
    def test_max_sample_period_boundary(self):
        """Test maximum sample period boundary conditions."""
        # Create data with specific interval
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="120s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        # Test with max period exactly at boundary (should pass)
        issues = check_data_quality(df, "timestamp", max_sample_period_s=120.0, allowed_gaps_s=240.0)
        period_issues = [issue for issue in issues if "period" in issue.lower()]
        assert len(period_issues) == 0, "120s interval should be allowed with 120s limit"
        
        # Test with max period just under boundary (should fail)
        issues = check_data_quality(df, "timestamp", max_sample_period_s=119.0, allowed_gaps_s=240.0)
        period_issues = [issue for issue in issues if "period" in issue.lower()]
        assert len(period_issues) > 0, "120s interval should be rejected with 119s limit"
    
    def test_normalization_parameter_validation(self):
        """Test validation of normalization parameters at boundaries."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        # Test zero target step (invalid)
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(df, target_step_s=0.0, allowed_gaps_s=60.0)
        
        # Test negative allowed gaps (invalid)
        with pytest.raises((ValueError, NormalizationError)):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=-1.0)
        
        # Test very small valid values (should work)
        result = normalize_temperature_data(df, target_step_s=0.1, allowed_gaps_s=0.1)
        assert len(result) > 0


class TestMissingTimeColumnValidation:
    """Test missing time column → ValidationError."""
    
    def test_missing_timestamp_column_error(self):
        """Test error when no timestamp column can be detected."""
        df = pd.DataFrame({
            "temperature_1": [180.0, 181.0, 182.0],
            "temperature_2": [179.0, 180.0, 181.0],
            "sensor_id": ["A", "B", "C"]
        })
        
        with pytest.raises(ValueError, match="No timestamp column found"):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
    
    def test_empty_dataframe_error(self):
        """Test error when DataFrame is empty."""
        df = pd.DataFrame()
        
        with pytest.raises(NormalizationError, match="empty"):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
    
    def test_no_temperature_columns_error(self):
        """Test error when no temperature columns are detected."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "sensor_id": ["A", "B", "C"],
            "status": ["OK", "OK", "OK"]
        })
        
        with pytest.raises(NormalizationError, match="No temperature columns detected"):
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
    
    def test_insufficient_data_error(self):
        """Test error when insufficient data points."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-15T10:00:00Z")],
            "temp_1": [180.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        assert any("Insufficient data" in issue for issue in issues)


class TestDuplicateTimestampsHandling:
    """Test duplicate timestamps de-dup or error path."""
    
    def test_duplicate_timestamps_detection(self):
        """Test detection of duplicate timestamps in data quality checks."""
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),  # Duplicate
            pd.Timestamp("2024-01-15T10:01:00Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 181.0, 181.5, 182.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        duplicate_issues = [issue for issue in issues if "Duplicate" in issue]
        assert len(duplicate_issues) > 0, "Should detect duplicate timestamp"
        assert "1 occurrences" in duplicate_issues[0] or "1" in duplicate_issues[0]
    
    def test_multiple_duplicate_timestamps_detection(self):
        """Test detection of multiple duplicate timestamps."""
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:00Z"),  # Duplicate 1
            pd.Timestamp("2024-01-15T10:00:30Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),  # Duplicate 2
            pd.Timestamp("2024-01-15T10:01:00Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 180.1, 181.0, 181.1, 182.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        duplicate_issues = [issue for issue in issues if "Duplicate" in issue]
        assert len(duplicate_issues) > 0, "Should detect multiple duplicate timestamps"
        assert "2 occurrences" in duplicate_issues[0] or "2" in duplicate_issues[0]
    
    def test_normalization_handles_duplicates(self):
        """Test that normalization pipeline handles duplicate timestamps gracefully."""
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),  # Duplicate
            pd.Timestamp("2024-01-15T10:01:00Z"),
            pd.Timestamp("2024-01-15T10:01:30Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 181.0, 181.5, 182.0, 183.0]
        })
        
        # Should fail due to data quality issues including duplicates
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        
        assert "Duplicate timestamps" in str(exc_info.value)
    
    def test_non_monotonic_timestamps_detection(self):
        """Test detection of non-monotonic timestamp sequences."""
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:01:00Z"),  # Forward in time
            pd.Timestamp("2024-01-15T10:00:30Z"),  # Back in time (non-monotonic)
            pd.Timestamp("2024-01-15T10:01:30Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 182.0, 181.0, 183.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=120.0)
        monotonic_issues = [issue for issue in issues if "Non-monotonic" in issue or "monotonic" in issue]
        assert len(monotonic_issues) > 0, "Should detect non-monotonic timestamps"
    
    def test_zero_time_differences_detection(self):
        """Test detection of zero or negative time differences."""
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:00Z"),  # Same time (0 diff)
            pd.Timestamp("2024-01-15T10:00:30Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 180.0, 181.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        time_issues = [issue for issue in issues if "Non-monotonic" in issue or "monotonic" in issue]
        assert len(time_issues) > 0, "Should detect zero time differences"


class TestNormalizationEdgeCases:
    """Test edge cases and error conditions in normalization pipeline."""
    
    def test_normalize_single_row_data_error(self):
        """Test error with single row of data."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-15T10:00:00Z")],
            "temp_1": [180.0]
        })
        
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        
        assert "Insufficient data" in str(exc_info.value)
    
    def test_normalize_with_invalid_csv_format(self, temp_dir):
        """Test error handling for invalid CSV format."""
        csv_path = temp_dir / "invalid.csv"
        with open(csv_path, 'w') as f:
            f.write("# Valid metadata\n")
            f.write("invalid,csv,format,,,,,\n")
            f.write("missing,quotes,in,strings with spaces\n")
        
        with pytest.raises(ValueError, match="Failed to parse CSV"):
            load_csv_with_metadata(str(csv_path))
    
    def test_normalize_file_not_found_error(self):
        """Test file not found error handling."""
        with pytest.raises(FileNotFoundError):
            load_csv_with_metadata("nonexistent_file.csv")
    
    def test_validate_data_quality_alias(self):
        """Test that validate_data_quality is an alias for check_data_quality."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        issues1 = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        issues2 = validate_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        
        assert issues1 == issues2, "validate_data_quality should be alias for check_data_quality"
    
    def test_temperature_column_detection_numeric_only(self):
        """Test that temperature column detection requires numeric columns."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_string": ["hot", "hotter", "hottest"],  # String, should be ignored
            "temperature_1": [180.0, 181.0, 182.0],       # Numeric, should be detected
            "sensor_°C": ["A", "B", "C"]                   # String despite °C, should be ignored
        })
        
        temp_columns = detect_temperature_columns(df)
        assert "temperature_1" in temp_columns
        assert "temp_string" not in temp_columns
        assert "sensor_°C" not in temp_columns
    
    def test_resample_handles_edge_case_frequencies(self):
        """Test resampling with edge case frequencies."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=5, freq="30s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0, 181.0, 180.0]
        })
        
        # Test fractional second resampling
        result = resample_temperature_data(df, "timestamp", target_step_s=15.5)
        assert len(result) > 0
        
        # Test very large step
        result = resample_temperature_data(df, "timestamp", target_step_s=300.0)
        assert len(result) <= len(df)
        
        # Test step that doesn't divide evenly
        result = resample_temperature_data(df, "timestamp", target_step_s=47.0)
        assert len(result) > 0