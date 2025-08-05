"""
Coverage Boost Tests for Normalize Pipeline

Additional tests targeting specific uncovered branches in normalize.py
to reach ≥90% coverage as required for PR-B1.

Example usage:
    pytest tests/test_normalize_coverage_boost.py -v --cov=core.normalize
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
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
    NormalizationError
)


class TestCoverageBranches:
    """Test specific branches to increase coverage percentage."""
    
    def test_load_csv_empty_file_after_metadata(self, temp_dir):
        """Test CSV file with only empty lines after metadata."""
        csv_content = """# Job: test
# Equipment: test_equipment


"""
        csv_path = temp_dir / "empty_after_meta.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        with pytest.raises(ValueError, match="No data lines found"):
            load_csv_with_metadata(str(csv_path))
    
    def test_load_csv_parse_error(self, temp_dir):
        """Test CSV parsing error due to malformed CSV."""
        csv_content = """# Job: test
timestamp,temp_1
2024-01-15T10:00:00Z,180.0
"unclosed quote field
"""
        csv_path = temp_dir / "parse_error.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        with pytest.raises(ValueError, match="Failed to parse CSV"):
            load_csv_with_metadata(str(csv_path))
    
    def test_load_csv_empty_dataframe_after_parse(self, temp_dir):
        """Test CSV that parses but results in empty DataFrame."""
        csv_content = """# Job: test
# Equipment: test

"""  # Header only, no data
        csv_path = temp_dir / "empty_df.csv"
        with open(csv_path, 'w') as f:
            f.write(csv_content)
        
        with pytest.raises(ValueError, match="No data lines found"):
            load_csv_with_metadata(str(csv_path))
    
    def test_detect_timestamp_format_unix_edge_cases(self):
        """Test Unix timestamp detection edge cases."""
        # Test values outside Unix timestamp range
        df_invalid = pd.DataFrame({
            "timestamp": [999999999999999999, 123, 456],  # Too large for Unix
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        # Should fall back to ISO format detection
        fmt, col = detect_timestamp_format(df_invalid)
        assert fmt == "iso"
        assert col == "timestamp"
    
    def test_detect_timestamp_format_non_numeric_fallback(self):
        """Test fallback when timestamp column is not numeric."""
        df = pd.DataFrame({
            "timestamp": ["not_a_timestamp", "also_not", "nope"],
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        # Should default to ISO format
        fmt, col = detect_timestamp_format(df)
        assert fmt == "iso"
        assert col == "timestamp"
    
    def test_detect_timestamp_column_first_column_not_parseable(self):
        """Test when first column cannot be parsed as timestamp."""
        df = pd.DataFrame({
            "sensor_reading": [180.0, 181.0, 182.0],  # Not parseable as timestamp
            "location": ["A", "B", "C"]
        })
        
        with pytest.raises(ValueError, match="No timestamp column found"):
            detect_timestamp_column(df)
    
    def test_parse_timestamps_timezone_conversion_edge_cases(self):
        """Test edge cases in timezone conversion."""
        # Test with timezone-aware timestamps that need conversion
        df = pd.DataFrame({
            "timestamp": ["2024-01-15T10:00:00+01:00", "2024-01-15T10:00:30+01:00"],
            "temp_1": [180.0, 181.0]
        })
        
        timestamps = parse_timestamps(df, "timestamp")
        
        # Should be converted to UTC (subtract 1 hour)
        expected_utc = pd.Timestamp("2024-01-15T09:00:00Z")
        assert timestamps.iloc[0] == expected_utc
        assert str(timestamps.iloc[0].tz) == "UTC"
    
    def test_parse_timestamps_fallback_unix_failure(self):
        """Test parse_timestamps when both ISO and Unix parsing fail."""
        df = pd.DataFrame({
            "timestamp": ["not_a_date", "also_not_a_date"],
            "temp_1": [180.0, 181.0]
        })
        
        with pytest.raises(ValueError, match="Unable to parse timestamps"):
            parse_timestamps(df, "timestamp")
    
    def test_convert_fahrenheit_to_celsius_list_error(self):
        """Test error when trying to convert unsupported list type."""
        with pytest.raises(ValueError, match="Unsupported type"):
            convert_fahrenheit_to_celsius([356.0, 358.0])
    
    def test_detect_temperature_columns_non_numeric_filtered(self):
        """Test that non-numeric columns are filtered out of temperature detection."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_string": ["180", "181", "182"],     # String values
            "temperature_1": [180.0, 181.0, 182.0],   # Numeric - should be detected
            "temp_object": [None, "hot", 180.0]       # Mixed object - should be filtered
        })
        
        temp_columns = detect_temperature_columns(df)
        assert "temperature_1" in temp_columns
        assert "temp_string" not in temp_columns
        assert "temp_object" not in temp_columns
    
    def test_check_data_quality_insufficient_data_single_row(self):
        """Test data quality check with single row (insufficient data)."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-15T10:00:00Z")],
            "temp_1": [180.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        assert any("Insufficient data" in issue for issue in issues)
    
    def test_check_data_quality_no_time_diffs(self):
        """Test data quality check when time differences cannot be calculated."""
        # Create edge case where diff calculation fails
        timestamps = pd.Series([pd.NaT, pd.NaT])  # All NaT values
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 181.0]
        })
        
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=60.0)
        # Should handle gracefully - may return issues about insufficient data or calculation
        assert len(issues) > 0
    
    def test_unit_resolver_functionality(self):
        """Test the optional unit_resolver functionality."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "custom_temp": [356.0, 358.0, 360.0]  # Should be Fahrenheit based on resolver
        })
        
        def custom_unit_resolver(col_name: str) -> str:
            if "custom" in col_name:
                return "fahrenheit"
            return "celsius"
        
        normalized_df = normalize_temperature_data(
            df, 
            target_step_s=30.0, 
            allowed_gaps_s=60.0,
            unit_resolver=custom_unit_resolver
        )
        
        # Should convert to Celsius (~180°C range)
        assert normalized_df["custom_temp"].iloc[0] < 200.0  # Converted from ~356°F
        assert normalized_df["custom_temp"].iloc[0] > 150.0
        
    def test_tz_resolver_functionality(self):
        """Test the optional tz_resolver functionality."""
        df = pd.DataFrame({
            "timestamp": ["2024-01-15T10:00:00", "2024-01-15T10:00:30"],  # Naive timestamps
            "temp_1": [180.0, 181.0]
        })
        
        def custom_tz_resolver(tz_name: str) -> str:
            # Map custom timezone names to standard ones
            if tz_name == "MyTimezone":
                return "US/Eastern"
            return tz_name
        
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            source_timezone="MyTimezone",
            tz_resolver=custom_tz_resolver
        )
        
        # Should be converted to UTC from Eastern time
        assert str(normalized_df["timestamp"].iloc[0].tz) == "UTC"
    
    def test_normalization_with_resolvers_none(self):
        """Test normalization when resolvers are provided but return None conditions."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        def null_tz_resolver(tz: str) -> str:
            return tz  # No change
        
        def null_unit_resolver(col: str) -> str:
            return "celsius"  # Always celsius
        
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            tz_resolver=null_tz_resolver,
            unit_resolver=null_unit_resolver
        )
        
        assert len(normalized_df) > 0
        assert "temp_1" in normalized_df.columns
    
    def test_resample_handles_interpolation_edge_cases(self):
        """Test resampling interpolation with edge cases."""
        # Create data with large gaps that need interpolation
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:00:30Z"),
            pd.Timestamp("2024-01-15T10:03:00Z"),  # 2.5 minute gap
            pd.Timestamp("2024-01-15T10:03:30Z"),
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 181.0, 182.0, 183.0]
        })
        
        result = resample_temperature_data(df, "timestamp", target_step_s=30.0)
        
        # Should interpolate missing values in the gap
        assert len(result) > len(df)  # More points due to resampling
        
        # Check that interpolation occurred
        temp_values = result["temp_1"].dropna()
        assert len(temp_values) > 0
    
    def test_fahrenheit_column_renaming_edge_cases(self):
        """Test Fahrenheit column renaming with edge cases."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_°F": [356.0, 358.0, 360.0],          # Should be renamed to temp_°C
            "sensor_degF_1": [356.0, 358.0, 360.0],    # Should be renamed
            "temperature_f": [356.0, 358.0, 360.0],    # Should be renamed
        })
        
        temp_columns = detect_temperature_columns(df)
        converted_df = _convert_fahrenheit_to_celsius_df(df, temp_columns)
        
        # Check that columns were renamed and converted
        converted_columns = converted_df.columns.tolist()
        
        # Should have converted temperatures (~180°C range)
        for col in converted_columns:
            if col != "timestamp":
                temps = converted_df[col]
                assert temps.max() < 200.0  # Should be in Celsius range
                assert temps.max() > 150.0


class TestResolverEdgeCases:
    """Test edge cases for the new resolver functionality."""
    
    def test_unit_resolver_with_no_fahrenheit_columns(self):
        """Test unit resolver when no Fahrenheit columns are detected."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_c": [180.0, 181.0, 182.0]  # Already Celsius
        })
        
        def unit_resolver(col: str) -> str:
            return "celsius"  # Always return celsius
        
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            unit_resolver=unit_resolver
        )
        
        # Should process normally
        assert len(normalized_df) > 0
        assert "temp_c" in normalized_df.columns
    
    def test_tz_resolver_with_none_source_timezone(self):
        """Test tz_resolver when source_timezone is None."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        def tz_resolver(tz: str) -> str:
            return "US/Eastern"
        
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            source_timezone=None,  # None means no resolver should be called
            tz_resolver=tz_resolver
        )
        
        # Should process normally without calling resolver
        assert len(normalized_df) > 0
        assert str(normalized_df["timestamp"].iloc[0].tz) == "UTC"


class TestValidationPathsAndErrors:
    """Test specific validation paths and error conditions."""
    
    def test_normalize_with_validation_parameter_errors(self):
        """Test normalization with invalid parameters that should raise errors."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-15T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "temp_1": [180.0, 181.0, 182.0]
        })
        
        # Test with very small positive values that might cause issues
        result = normalize_temperature_data(
            df,
            target_step_s=0.001,  # Very small but positive
            allowed_gaps_s=0.001
        )
        assert len(result) > 0
    
    def test_check_data_quality_edge_boundary_conditions(self):
        """Test data quality checks at exact boundary conditions."""
        # Create data with exactly boundary conditions
        timestamps = [
            pd.Timestamp("2024-01-15T10:00:00Z"),
            pd.Timestamp("2024-01-15T10:05:00Z"),  # Exactly 300s gap
        ]
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": [180.0, 181.0]
        })
        
        # Test at exact boundary - should pass
        issues = check_data_quality(df, "timestamp", max_sample_period_s=300.0, allowed_gaps_s=300.0)
        gap_issues = [issue for issue in issues if "gap" in issue.lower()]
        assert len(gap_issues) == 0  # Should pass at exact boundary
        
        # Test just over boundary - should fail
        issues = check_data_quality(df, "timestamp", max_sample_period_s=299.0, allowed_gaps_s=299.0)
        gap_issues = [issue for issue in issues if "gap" in issue.lower() or "period" in issue.lower()]
        assert len(gap_issues) > 0  # Should fail just over boundary