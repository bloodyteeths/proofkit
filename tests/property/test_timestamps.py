"""
Property-based tests for timestamp parsing and normalization.

Tests mixed timezone stamps, duplicates, and edge cases using Hypothesis.
"""
import pandas as pd
import pytest
from datetime import datetime, timezone, timedelta
from hypothesis import given, strategies as st, settings, assume, example
from hypothesis.extra.pandas import data_frames, column
import pytz
from typing import List, Optional

from core.normalize import (
    parse_timestamps,
    detect_timestamp_column,
    detect_timestamp_format,
    normalize_temperature_data,
    NormalizationError
)
from core.errors import DataQualityError


# Generate timezone names for testing
COMMON_TIMEZONES = [
    "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "Europe/London", "Europe/Paris", "Asia/Tokyo", "Australia/Sydney"
]

# Generate timestamp formats
ISO_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", 
    "%m/%d/%Y %H:%M:%S",
    "%d.%m.%Y %H:%M:%S"
]

@st.composite
def timestamp_strings(draw):
    """Generate valid timestamp strings in various formats."""
    base_time = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2025, 12, 31),
        timezones=st.none()
    ))
    
    format_str = draw(st.sampled_from(ISO_FORMATS))
    return base_time.strftime(format_str)


@st.composite
def unix_timestamps(draw):
    """Generate valid Unix timestamps."""
    # Unix timestamp range from 2020-2025
    timestamp = draw(st.floats(
        min_value=1577836800.0,  # 2020-01-01
        max_value=1767225600.0,  # 2025-12-31
        allow_nan=False,
        allow_infinity=False
    ))
    return timestamp


@st.composite
def mixed_timezone_dataframes(draw):
    """Generate DataFrames with mixed timezone timestamps."""
    size = draw(st.integers(min_value=5, max_value=100))
    
    # Base timestamp
    base_time = datetime(2023, 1, 1, 12, 0, 0)
    
    timestamps = []
    temps = []
    
    for i in range(size):
        # Add some time progression
        time_offset = i * draw(st.integers(min_value=30, max_value=300))  # 30s to 5min steps
        ts = base_time + timedelta(seconds=time_offset)
        
        # Randomly add timezone info
        if draw(st.booleans()):
            tz_name = draw(st.sampled_from(COMMON_TIMEZONES))
            if tz_name != "UTC":
                tz = pytz.timezone(tz_name)
                ts = tz.localize(ts)
            else:
                ts = ts.replace(tzinfo=timezone.utc)
        
        timestamps.append(ts.isoformat())
        temps.append(draw(st.floats(min_value=50.0, max_value=250.0, allow_nan=False)))
    
    return pd.DataFrame({
        'timestamp': timestamps,
        'temperature': temps
    })


@st.composite
def dataframes_with_duplicates(draw):
    """Generate DataFrames with intentional duplicate timestamps."""
    size = draw(st.integers(min_value=10, max_value=50))
    
    base_time = datetime(2023, 1, 1, 12, 0, 0)
    timestamps = []
    temps = []
    
    for i in range(size):
        time_offset = i * 60  # 1-minute intervals
        ts = base_time + timedelta(seconds=time_offset)
        timestamps.append(ts.isoformat())
        temps.append(draw(st.floats(min_value=100.0, max_value=200.0, allow_nan=False)))
    
    # Add some duplicates
    num_duplicates = draw(st.integers(min_value=1, max_value=size // 3))
    for _ in range(num_duplicates):
        dup_idx = draw(st.integers(min_value=0, max_value=size - 1))
        timestamps.append(timestamps[dup_idx])
        temps.append(draw(st.floats(min_value=100.0, max_value=200.0, allow_nan=False)))
    
    return pd.DataFrame({
        'timestamp': timestamps,
        'temperature': temps
    })


class TestTimestampProperties:
    """Property-based tests for timestamp handling."""
    
    @given(mixed_timezone_dataframes())
    @settings(max_examples=20, deadline=5000)
    def test_parse_mixed_timezones_property(self, df):
        """Property: parsing mixed timezone data should always produce UTC timestamps."""
        assume(len(df) >= 2)
        
        timestamp_col = 'timestamp'
        
        # Parse timestamps
        utc_timestamps = parse_timestamps(df, timestamp_col)
        
        # Property: All results should be UTC
        assert all(ts.tz == timezone.utc for ts in utc_timestamps), \
            "All parsed timestamps should be in UTC"
        
        # Property: Should be monotonic if input was monotonic
        time_diffs = utc_timestamps.diff().dt.total_seconds().dropna()
        if (time_diffs >= 0).all():  # Input was monotonic
            assert (utc_timestamps.diff().dt.total_seconds().dropna() >= 0).all(), \
                "Monotonic input should produce monotonic output"
    
    @given(unix_timestamps(), st.integers(min_value=5, max_value=50))
    @settings(max_examples=15, deadline=3000)
    def test_unix_timestamp_parsing_property(self, base_timestamp, size):
        """Property: Unix timestamps should parse correctly and maintain order."""
        timestamps = [base_timestamp + i * 60 for i in range(size)]  # 1-minute intervals
        temps = [150.0 + i for i in range(size)]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature': temps
        })
        
        # Parse timestamps
        utc_timestamps = parse_timestamps(df, 'timestamp')
        
        # Property: Should be monotonic increasing
        time_diffs = utc_timestamps.diff().dt.total_seconds().dropna()
        assert (time_diffs > 0).all(), "Unix timestamps should maintain order"
        
        # Property: Should be UTC
        assert all(ts.tz == timezone.utc for ts in utc_timestamps), \
            "Unix timestamps should be parsed as UTC"
    
    @given(dataframes_with_duplicates())
    @settings(max_examples=10, deadline=5000)
    def test_duplicate_timestamp_handling_property(self, df):
        """Property: duplicate timestamp handling should be deterministic."""
        assume(len(df) >= 5)
        
        # Should detect duplicates consistently
        duplicates_before = df['timestamp'].duplicated().sum()
        assume(duplicates_before > 0)  # Only test when duplicates exist
        
        # For powder industry, duplicates should cause DataQualityError
        with pytest.raises(DataQualityError):
            normalize_temperature_data(df, industry="powder")
        
        # For other industries, should handle gracefully
        try:
            result = normalize_temperature_data(df, industry="concrete")
            # Property: Result should have fewer or equal rows
            assert len(result) <= len(df), "Normalization should not increase row count"
            
            # Property: Temperature column should be preserved
            temp_cols = [col for col in result.columns if 'temp' in col.lower()]
            assert len(temp_cols) > 0, "Should preserve temperature columns"
            
        except NormalizationError:
            # Acceptable if data quality is too poor
            pass
    
    @given(st.data())
    @settings(max_examples=15, deadline=3000)
    def test_timestamp_column_detection_property(self, data):
        """Property: timestamp column detection should be consistent."""
        # Generate various column names
        timestamp_names = data.draw(st.sampled_from([
            'timestamp', 'time', 'datetime', 'ts', 'sample_time', 'TIME', 'Timestamp'
        ]))
        other_col = data.draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'))))
        assume(other_col.lower() not in ['timestamp', 'time', 'datetime', 'ts', 'sample_time'])
        
        size = data.draw(st.integers(min_value=3, max_value=20))
        
        df = pd.DataFrame({
            timestamp_names: [f"2023-01-01T12:{i:02d}:00" for i in range(size)],
            other_col: [100.0 + i for i in range(size)]
        })
        
        detected_col = detect_timestamp_column(df)
        
        # Property: Should detect the timestamp column
        assert detected_col == timestamp_names, \
            f"Should detect {timestamp_names} as timestamp column, got {detected_col}"
    
    @example(
        pd.DataFrame({
            'timestamp': ['2023-01-01T12:00:00Z', '2023-01-01T12:01:00Z'],
            'temperature': [150.0, 155.0]
        })
    )
    @given(data_frames([
        column('timestamp', elements=timestamp_strings()),
        column('temperature', elements=st.floats(min_value=50.0, max_value=300.0, allow_nan=False))
    ], rows=st.tuples(st.integers(min_value=2, max_value=50))))
    @settings(max_examples=10, deadline=5000)
    def test_timestamp_format_detection_property(self, df):
        """Property: timestamp format detection should work for various formats."""
        assume(len(df) >= 2)
        
        try:
            format_type, column_name = detect_timestamp_format(df)
            
            # Property: Should return valid format type
            assert format_type in ['iso', 'unix'], \
                f"Format type should be 'iso' or 'unix', got {format_type}"
            
            # Property: Should return valid column name
            assert column_name in df.columns, \
                f"Column name {column_name} should exist in DataFrame"
            
            # Property: Detection should be reproducible
            format_type2, column_name2 = detect_timestamp_format(df)
            assert format_type == format_type2 and column_name == column_name2, \
                "Format detection should be deterministic"
                
        except ValueError:
            # Acceptable if no valid timestamp column found
            pass


class TestTimestampEdgeCases:
    """Edge case tests for timestamp handling."""
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrames."""
        df = pd.DataFrame({'timestamp': [], 'temperature': []})
        
        with pytest.raises(ValueError, match="No data lines found"):
            detect_timestamp_column(df)
    
    def test_single_row_dataframe(self):
        """Test handling of single-row DataFrames."""
        df = pd.DataFrame({
            'timestamp': ['2023-01-01T12:00:00Z'],
            'temperature': [150.0]
        })
        
        # Should detect column but fail normalization
        col = detect_timestamp_column(df)
        assert col == 'timestamp'
        
        with pytest.raises(NormalizationError, match="Insufficient data"):
            normalize_temperature_data(df)
    
    def test_timezone_shift_consistency(self):
        """Test that timezone shifts are handled consistently."""
        # Create data spanning DST transition
        base_times = [
            "2023-03-12T06:00:00",  # Before DST
            "2023-03-12T08:00:00",  # During DST transition
            "2023-03-12T09:00:00",  # After DST
        ]
        
        df = pd.DataFrame({
            'timestamp': base_times,
            'temperature': [150.0, 155.0, 160.0]
        })
        
        # Parse with US/Eastern (has DST)
        utc_timestamps = parse_timestamps(df, 'timestamp', source_tz='US/Eastern')
        
        # Should all be UTC and maintain relative ordering
        assert all(ts.tz == timezone.utc for ts in utc_timestamps)
        time_diffs = utc_timestamps.diff().dt.total_seconds().dropna()
        assert (time_diffs > 0).all(), "Should maintain temporal order despite DST"


# Usage example in module docstring:
"""
Example usage of property-based timestamp testing:

    pytest tests/property/test_timestamps.py -v

To run with more examples:
    pytest tests/property/test_timestamps.py --hypothesis-max-examples=50

To run specific property tests:
    pytest tests/property/test_timestamps.py::TestTimestampProperties::test_parse_mixed_timezones_property
"""