"""
Tests for edge cases in core/normalize.py.

Covers timestamp parsing issues, mixed timezones, gap detection accuracy,
and duplicate timestamp handling.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import pytz
from io import StringIO

from core.normalize import (
    parse_timestamps, 
    check_data_quality,
    normalize_temperature_data,
    detect_timestamp_column,
    NormalizationError
)


class TestTimestampParsing:
    """Test timestamp parsing with various formats and edge cases."""
    
    def test_parse_unix_seconds_basic(self):
        """Test parsing Unix timestamp in seconds."""
        df = pd.DataFrame({
            'timestamp': [1609459200, 1609459230, 1609459260],  # Jan 1, 2021
            'temp': [20.0, 21.0, 22.0]
        })
        
        result = parse_timestamps(df, 'timestamp')
        
        assert result.dt.tz == timezone.utc
        assert len(result) == 3
        # First timestamp should be Jan 1, 2021 00:00:00 UTC
        assert result.iloc[0] == pd.Timestamp('2021-01-01 00:00:00', tz='UTC')
    
    def test_parse_mixed_timezone_formats(self):
        """Test parsing mixed timezone formats."""
        df = pd.DataFrame({
            'time': ['2021-01-01 12:00:00-05:00', '2021-01-01 13:00:00-05:00'],
            'temp': [20.0, 21.0]
        })
        
        result = parse_timestamps(df, 'time')
        
        assert result.dt.tz == timezone.utc
        # Should be converted to UTC (17:00 and 18:00)
        assert result.iloc[0].hour == 17
        assert result.iloc[1].hour == 18
    
    def test_parse_with_source_timezone(self):
        """Test parsing naive timestamps with specified source timezone."""
        df = pd.DataFrame({
            'timestamp': ['2021-01-01 12:00:00', '2021-01-01 13:00:00'],
            'temp': [20.0, 21.0]
        })
        
        result = parse_timestamps(df, 'timestamp', source_tz='US/Eastern')
        
        assert result.dt.tz == timezone.utc
        # EST is UTC-5, so 12:00 EST = 17:00 UTC
        assert result.iloc[0].hour == 17
    
    def test_parse_invalid_timezone_fallback(self):
        """Test fallback when invalid timezone is provided."""
        df = pd.DataFrame({
            'timestamp': ['2021-01-01 12:00:00', '2021-01-01 13:00:00'],
            'temp': [20.0, 21.0]
        })
        
        # Should not raise exception, should fallback to UTC
        result = parse_timestamps(df, 'timestamp', source_tz='Invalid/Timezone')
        
        assert result.dt.tz == timezone.utc
        assert len(result) == 2
    
    def test_parse_mixed_formats_unix_iso(self):
        """Test that Unix timestamps are detected and parsed correctly."""
        # Create DataFrame with Unix timestamps
        df = pd.DataFrame({
            'ts': [1609459200, 1609459230, 1609459260],  # Valid Unix range
            'temp': [20.0, 21.0, 22.0]
        })
        
        result = parse_timestamps(df, 'ts')
        
        assert result.dt.tz == timezone.utc
        assert result.iloc[0] == pd.Timestamp('2021-01-01 00:00:00', tz='UTC')
    
    def test_parse_invalid_timestamps_raises_error(self):
        """Test that invalid timestamps raise appropriate error."""
        df = pd.DataFrame({
            'timestamp': ['invalid', 'also invalid'],
            'temp': [20.0, 21.0]
        })
        
        with pytest.raises(ValueError) as exc_info:
            parse_timestamps(df, 'timestamp')
        
        assert "Unable to parse timestamps" in str(exc_info.value)
        assert "ISO parsing failed" in str(exc_info.value)
        assert "Unix parsing failed" in str(exc_info.value)


class TestDataQualityChecking:
    """Test data quality checking with accurate gap detection messages."""
    
    def test_gap_detection_message_consistency(self):
        """Test that gap detection messages show consistent decimal places."""
        timestamps = pd.date_range('2021-01-01', periods=3, freq='60s', tz='UTC')
        # Add a large gap
        timestamps = timestamps.union([timestamps[-1] + pd.Timedelta(seconds=120)])
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp': [20.0, 21.0, 22.0, 23.0]
        })
        
        issues = check_data_quality(df, 'timestamp', max_sample_period_s=180, allowed_gaps_s=90)
        
        # Should find 1 gap > 90s
        gap_issues = [issue for issue in issues if 'gaps' in issue]
        assert len(gap_issues) == 1
        
        # Message should show consistent decimal formatting
        assert '90.0s' in gap_issues[0]
        assert '120.0s' in gap_issues[0]
    
    def test_duplicate_timestamp_detection_accurate(self):
        """Test accurate duplicate timestamp detection."""
        df = pd.DataFrame({
            'timestamp': pd.to_datetime([
                '2021-01-01 12:00:00', 
                '2021-01-01 12:00:00',  # duplicate
                '2021-01-01 12:01:00',
                '2021-01-01 12:01:00',  # duplicate
                '2021-01-01 12:02:00'
            ], utc=True),
            'temp': [20.0, 20.5, 21.0, 21.5, 22.0]
        })
        
        issues = check_data_quality(df, 'timestamp', max_sample_period_s=120, allowed_gaps_s=60)
        
        duplicate_issues = [issue for issue in issues if 'Duplicate timestamps detected' in issue]
        assert len(duplicate_issues) == 1
        assert '2 occurrences' in duplicate_issues[0]
    
    def test_non_monotonic_timestamp_detection(self):
        """Test detection of non-monotonic timestamps."""
        df = pd.DataFrame({
            'timestamp': pd.to_datetime([
                '2021-01-01 12:00:00',
                '2021-01-01 12:02:00', 
                '2021-01-01 12:01:00',  # goes backward
                '2021-01-01 12:03:00'
            ], utc=True),
            'temp': [20.0, 21.0, 20.5, 22.0]
        })
        
        issues = check_data_quality(df, 'timestamp', max_sample_period_s=300, allowed_gaps_s=120)
        
        monotonic_issues = [issue for issue in issues if 'Non-monotonic' in issue]
        assert len(monotonic_issues) == 1
        assert '1 occurrences' in monotonic_issues[0]
    
    def test_sampling_period_too_large(self):
        """Test detection when sampling period exceeds maximum."""
        df = pd.DataFrame({
            'timestamp': pd.to_datetime([
                '2021-01-01 12:00:00',
                '2021-01-01 12:10:00'  # 600s gap
            ], utc=True),
            'temp': [20.0, 21.0]
        })
        
        issues = check_data_quality(df, 'timestamp', max_sample_period_s=300, allowed_gaps_s=120)
        
        period_issues = [issue for issue in issues if 'Sampling period too large' in issue]
        assert len(period_issues) == 1
        assert '600.0s > 300s' in period_issues[0]


class TestNormalizationWithEdgeCases:
    """Test normalization function with edge cases."""
    
    def test_normalize_with_duplicate_timestamps_removed(self):
        """Test that normalization removes duplicates and logs warning."""
        df = pd.DataFrame({
            'timestamp': [1609459200, 1609459200, 1609459260],  # duplicate first two
            'temp_c': [20.0, 20.5, 22.0]
        })
        
        # This should not raise an exception despite duplicates
        # because we remove them during normalization
        result = normalize_temperature_data(
            df, 
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            max_sample_period_s=120.0
        )
        
        # Should have removed one duplicate, leaving 2 rows
        assert len(result) >= 2  # resampling may create additional points
        
        # Verify timestamps are unique
        timestamp_col = detect_timestamp_column(result)
        assert result[timestamp_col].duplicated().sum() == 0
    
    def test_normalize_mixed_timezone_unix_data(self):
        """Test normalization with mixed Unix and timezone data patterns."""
        df = pd.DataFrame({
            'ts': [1609459200, 1609459230, 1609459260],  # Unix timestamps
            'temperature': [180.0, 185.0, 190.0]  # Fahrenheit values
        })
        
        result = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=60.0,
            max_sample_period_s=120.0
        )
        
        # Should have converted F to C
        temp_cols = [col for col in result.columns if 'temp' in col.lower()]
        assert len(temp_cols) > 0
        
        # Values should be in Celsius range now (around 82-88°C)
        temp_values = result[temp_cols[0]].dropna()
        assert temp_values.min() > 50  # Should be > 50°C
        assert temp_values.max() < 100  # Should be < 100°C
    
    def test_normalize_fails_with_quality_issues(self):
        """Test that normalization fails when data quality issues are severe."""
        # Create data with large gaps that exceed limits
        timestamps = [1609459200, 1609459200 + 600]  # 600s gap
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temp': [20.0, 21.0]
        })
        
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=120.0,  # Gap of 600s exceeds this
                max_sample_period_s=300.0
            )
        
        assert "Data quality checks failed" in str(exc_info.value)
        assert "gaps" in str(exc_info.value)


class TestTimestampColumnDetection:
    """Test edge cases in timestamp column detection."""
    
    def test_detect_timestamp_column_numeric_unix(self):
        """Test detection of numeric Unix timestamp columns."""
        df = pd.DataFrame({
            'unix_time': [1609459200, 1609459230, 1609459260],
            'temp': [20.0, 21.0, 22.0]
        })
        
        col = detect_timestamp_column(df)
        assert col == 'unix_time'
    
    def test_detect_timestamp_first_column_fallback(self):
        """Test fallback to first column when it contains valid timestamps."""
        df = pd.DataFrame({
            'sample_data': ['2021-01-01 12:00:00', '2021-01-01 12:01:00'],
            'measurement': [20.0, 21.0]
        })
        
        col = detect_timestamp_column(df)
        assert col == 'sample_data'
    
    def test_detect_timestamp_no_valid_column_raises(self):
        """Test that detection raises error when no valid timestamp column found."""
        df = pd.DataFrame({
            'data': ['not_a_timestamp', 'also_not'],
            'values': [20.0, 21.0]
        })
        
        with pytest.raises(ValueError) as exc_info:
            detect_timestamp_column(df)
        
        assert "No timestamp column found" in str(exc_info.value)


# Example usage in comments:
"""
Example of running these edge case tests:

pytest tests/test_normalize_edgecases.py -v
pytest tests/test_normalize_edgecases.py::TestTimestampParsing::test_parse_unix_seconds_basic -v
pytest tests/test_normalize_edgecases.py::TestDataQualityChecking -v
"""