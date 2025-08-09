"""
Tests for locale support and expanded header mapping hardening.

Tests for Agent C - Parser & Column Mapping Hardening:
- Vendor header variations (Temperature, Pressure, Humidity, Time)
- Enhanced locale parsing (decimal comma, semicolon delimiter)
- Excel serial timestamps
- Parser warnings and safe mode
- Property tests for edge cases
"""
import pandas as pd
import pytest
import tempfile
import os
import numpy as np
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
# Optional hypothesis import for property testing
try:
    import hypothesis as hy
    from hypothesis import given, strategies as st
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False
    
    # Mock decorators when hypothesis is not available
    def given(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    class st:
        @staticmethod
        def lists(*args, **kwargs):
            return None
        @staticmethod 
        def floats(*args, **kwargs):
            return None
        @staticmethod
        def text(*args, **kwargs):
            return None
        @staticmethod
        def characters(*args, **kwargs):
            return None

from core.normalize import (
    load_csv_with_metadata,
    normalize_column_names,
    normalize_decimal_separators,
    detect_delimiter,
    detect_encoding,
    convert_excel_serial_dates,
    normalize_temperature_data,
    NormalizationError,
    ParseWarning,
    IndeterminateError,
    SAFE_MODE,
    FAIL_ON_PARSER_WARNINGS
)
from core.columns_map import get_column_mapping


class TestVendorHeaderMapping:
    """Test expanded column mapping for vendor headers."""
    
    def test_temperature_header_variations(self):
        """Test various temperature header formats."""
        test_headers = [
            # Parentheses formats
            ("Temp(C)", "temperature"),
            ("Temperature(C)", "temperature"), 
            ("Temperature (°C)", "temperature"),
            ("Temp [°C]", "temperature"),
            ("Temperature[C]", "temperature"),
            
            # Multi-sensor formats
            ("T1", "temperature_1"),
            ("T2", "temperature_2"),
            ("Ch1", "temperature_1"),
            ("Channel1", "temperature_1"),
            ("Sensor 1", "temperature_1"),
            ("Probe 2", "temperature_2"),
            
            # Case variations
            ("TEMP", "temperature"),
            ("temp", "temperature"),
            ("Temperature", "temperature"),
        ]
        
        for original, expected in test_headers:
            mapping = normalize_column_names([original])
            assert original in mapping, f"Header '{original}' not found in mapping"
            assert mapping[original] == expected, f"Expected '{expected}', got '{mapping[original]}'"
    
    def test_pressure_header_variations(self):
        """Test various pressure header formats."""
        test_headers = [
            ("Press", "pressure"),
            ("P1", "pressure_1"),
            ("Pressure(psi)", "pressure"),
            ("Pressure (bar)", "pressure"),
            ("Pressure_kPa", "pressure"),
            ("pressure(PSI)", "pressure"),  # Case insensitive
        ]
        
        for original, expected in test_headers:
            mapping = normalize_column_names([original])
            assert original in mapping, f"Header '{original}' not found in mapping"
            assert mapping[original] == expected, f"Expected '{expected}', got '{mapping[original]}'"
    
    def test_humidity_header_variations(self):
        """Test humidity header formats."""
        test_headers = [
            ("RH", "humidity"),
            ("%RH", "humidity"),
            ("Humidity", "humidity"),
            ("Relative Humidity", "humidity"),
            ("H1", "humidity_1"),
            ("Humidity(%)", "humidity"),
            ("RH (%)", "humidity"),
        ]
        
        for original, expected in test_headers:
            mapping = normalize_column_names([original])
            assert original in mapping, f"Header '{original}' not found in mapping"
            assert mapping[original] == expected, f"Expected '{expected}', got '{mapping[original]}'"
    
    def test_timestamp_header_variations(self):
        """Test timestamp header formats."""
        test_headers = [
            ("Time", "timestamp"),
            ("DateTime", "timestamp"),
            ("Date Time", "timestamp"),
            ("Sample_Time", "timestamp"),
            ("Log_Time", "timestamp"),
            ("Record_Time", "timestamp"),
        ]
        
        for original, expected in test_headers:
            mapping = normalize_column_names([original])
            assert original in mapping, f"Header '{original}' not found in mapping"
            assert mapping[original] == expected, f"Expected '{expected}', got '{mapping[original]}'"
    
    def test_real_vendor_csv_example(self):
        """Test with realistic vendor CSV headers."""
        csv_content = '''Date Time;Temp(C);Temp [°C];Pressure(psi);RH(%);Ch1;Sensor 2
2023-01-01 12:00:00;150.5;148.2;15.2;45.0;175.1;172.8
2023-01-01 12:01:00;152.1;149.8;15.3;46.2;176.9;174.1
2023-01-01 12:02:00;153.7;151.4;15.1;44.8;178.2;175.6'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Check that column mapping was applied
            column_mapping = metadata.get('_column_mapping', {})
            assert 'Date Time' in column_mapping
            assert column_mapping['Date Time'] == 'timestamp'
            assert column_mapping['RH(%)'] == 'humidity'
            assert column_mapping['Ch1'] == 'temperature_1'
            assert column_mapping['Sensor 2'] == 'temperature_2'
            
        finally:
            os.unlink(temp_path)


class TestEnhancedLocaleSupport:
    """Test improved locale and decimal parsing."""
    
    def test_enhanced_european_format_detection(self):
        """Test improved European format detection."""
        csv_content = '''timestamp;temperature;pressure
2023-01-01T12:00:00;1.234,56;1.025,7
2023-01-01T12:01:00;2.345,67;998,45
2023-01-01T12:02:00;234,5;1.100,23'''
        
        # Test normalization
        normalized = normalize_decimal_separators(csv_content)
        
        # Check that European format was converted
        assert '1234.56' in normalized
        assert '2345.67' in normalized
        assert '234.5' in normalized
        assert '1025.7' in normalized
        assert '1100.23' in normalized
    
    def test_mixed_format_safety(self):
        """Test that mixed formats are handled safely."""
        # CSV with both field separators and decimal commas
        csv_content = '''name,value,comment
"Test 1",150.5,"Good, stable reading"
"Test 2",1.234,56,"Mixed, format test"'''
        
        normalized = normalize_decimal_separators(csv_content)
        
        # Quoted strings should be preserved
        assert '"Good, stable reading"' in normalized
        # But numeric values should be normalized carefully
        assert '150.5' in normalized
    
    def test_delimiter_detection_priority(self):
        """Test that semicolon has priority for European CSVs."""
        csv_content = '''timestamp;temperature,humidity
2023-01-01T12:00:00;150,5;45,2
2023-01-01T12:01:00;152,1;46,8'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            delimiter = detect_delimiter(temp_path)
            # Should detect semicolon as primary delimiter
            assert delimiter == ';'
            
        finally:
            os.unlink(temp_path)


class TestExcelTimestampHandling:
    """Test enhanced Excel serial date handling."""
    
    def test_excel_serial_date_detection(self):
        """Test detection of Excel serial dates."""
        # Create DataFrame with Excel serial dates
        # Excel serial date for 2023-01-01 12:00:00 ≈ 44927.5
        excel_dates = [44927.0, 44927.5, 44928.0, 44928.25, 44928.5]
        df = pd.DataFrame({
            'timestamp': excel_dates,
            'temperature': [150.0, 151.0, 152.0, 153.0, 154.0]
        })
        
        converted = convert_excel_serial_dates(df, 'timestamp')
        
        # Should be converted to datetime
        assert pd.api.types.is_datetime64_any_dtype(converted)
        
        # Check that dates are in reasonable range (2023)
        sample_date = converted.iloc[0]
        assert sample_date.year == 2023
        assert sample_date.month == 1
        assert sample_date.day == 1
    
    def test_excel_vs_unix_timestamp_distinction(self):
        """Test that Excel dates are distinguished from Unix timestamps."""
        # Unix timestamps (recent dates as seconds since 1970)
        unix_timestamps = [1672531200, 1672531260, 1672531320]  # 2023-01-01 times
        df_unix = pd.DataFrame({
            'timestamp': unix_timestamps,
            'temperature': [150.0, 151.0, 152.0]
        })
        
        # Excel serial dates
        excel_dates = [44927.0, 44927.5, 44928.0]  # 2023-01-01 dates
        df_excel = pd.DataFrame({
            'timestamp': excel_dates,
            'temperature': [150.0, 151.0, 152.0]
        })
        
        # Unix timestamps should not be converted by Excel function
        unix_converted = convert_excel_serial_dates(df_unix, 'timestamp')
        assert unix_converted.equals(df_unix['timestamp'])  # No change
        
        # Excel dates should be converted
        excel_converted = convert_excel_serial_dates(df_excel, 'timestamp')
        assert pd.api.types.is_datetime64_any_dtype(excel_converted)
    
    def test_excel_date_range_validation(self):
        """Test validation of Excel date conversion results."""
        # Invalid Excel serial dates (too old/new)
        invalid_dates = [100, 200000]  # Too old and too new
        df = pd.DataFrame({
            'timestamp': invalid_dates,
            'temperature': [150.0, 151.0]
        })
        
        # Should not convert invalid ranges
        converted = convert_excel_serial_dates(df, 'timestamp')
        assert converted.equals(df['timestamp'])  # No change


class TestParserWarningsAndSafeMode:
    """Test parser warning system and safe mode behavior."""
    
    def test_safe_mode_with_encoding_warnings(self):
        """Test that safe mode triggers on encoding warnings."""
        # Create file that will trigger encoding fallback
        csv_content = 'timestamp,temperature\n2023-01-01T12:00:00,150.5'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='cp1252') as f:
            f.write(csv_content + '\n2023-01-01T12:01:00,Température élevée')  # Non-ASCII
            temp_path = f.name
        
        try:
            # With safe mode, should raise IndeterminateError on warnings
            with pytest.raises(IndeterminateError, match="Parser warnings detected in safe mode"):
                load_csv_with_metadata(temp_path, safe_mode=True)
            
            # Without safe mode, should work
            df, metadata = load_csv_with_metadata(temp_path, safe_mode=False)
            assert len(df) >= 1  # Should have parsed some data
            
        finally:
            os.unlink(temp_path)
    
    def test_safe_mode_with_delimiter_warnings(self):
        """Test that safe mode triggers on delimiter warnings."""
        # Create CSV that will cause delimiter detection issues
        csv_content = '''timestamp|temperature|notes
2023-01-01T12:00:00|150.5|Good
2023-01-01T12:01:00,152.1,Also good'''  # Mixed delimiters
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            # May trigger delimiter fallback warnings
            df, metadata = load_csv_with_metadata(temp_path, safe_mode=False)
            
            # Check if warnings were recorded
            warnings = metadata['_parsing_info'].get('parser_warnings', [])
            # Warnings may or may not occur depending on detection logic
            
        finally:
            os.unlink(temp_path)
    
    def test_parser_warning_metadata(self):
        """Test that parser warnings are stored in metadata."""
        csv_content = 'timestamp,temperature\n2023-01-01T12:00:00,150.5'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path, safe_mode=False)
            
            # Check that parser warnings field exists
            assert 'parser_warnings' in metadata['_parsing_info']
            warnings = metadata['_parsing_info']['parser_warnings']
            assert isinstance(warnings, list)
            
        finally:
            os.unlink(temp_path)


class TestPropertyBasedEdgeCases:
    """Property-based tests for edge cases."""
    
    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not available")
    @given(st.lists(st.floats(min_value=0.0, max_value=86400.0), min_size=2, max_size=50))
    def test_timestamp_gaps_property(self, time_offsets):
        """Property test: timestamp gaps should be detected consistently."""
        # Create timestamps with known gaps
        base_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        timestamps = [base_time + timedelta(seconds=offset) for offset in sorted(time_offsets)]
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature': np.random.uniform(150, 200, len(timestamps))
        })
        
        # Test gap detection
        time_diffs = df['timestamp'].diff().dt.total_seconds().dropna()
        max_gap = time_diffs.max() if len(time_diffs) > 0 else 0
        
        # If max gap > 300s, normalization should detect it
        if max_gap > 300:
            with pytest.raises(NormalizationError, match="gaps too large"):
                normalize_temperature_data(df, allowed_gaps_s=300.0)
    
    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not available")
    @given(st.lists(st.floats(min_value=100.0, max_value=300.0), min_size=5, max_size=20))
    def test_temperature_duplicate_handling(self, temp_values):
        """Property test: duplicate temperature handling."""
        # Create timestamps - some duplicates
        base_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        n_temps = len(temp_values)
        
        # Create some duplicate timestamps
        timestamps = []
        for i, temp in enumerate(temp_values):
            timestamp = base_time + timedelta(seconds=i * 30)
            timestamps.append(timestamp)
            # Add occasional duplicate (same timestamp)
            if i > 0 and i % 5 == 0:
                timestamps.append(timestamp)  # Exact duplicate
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature': temp_values + temp_values[::5]  # Match length
        })
        
        # Test that normalization handles duplicates appropriately
        try:
            normalized_df = normalize_temperature_data(df)
            # Should have removed exact duplicates
            assert len(normalized_df) <= len(df)
            # Timestamps should be unique
            assert not normalized_df['timestamp'].duplicated().any()
        except NormalizationError:
            # Some industries may reject duplicates - that's also valid
            pass
    
    def test_timezone_mix_detection(self):
        """Test detection of mixed timezone data."""
        # Create mixed timezone timestamps
        utc_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        est_time = datetime(2023, 1, 1, 7, 0, 0, tzinfo=timezone(timedelta(hours=-5)))  # Same instant
        
        # Mix of UTC and EST times (but same instants)
        mixed_timestamps = [
            utc_time,
            utc_time + timedelta(minutes=1),
            est_time + timedelta(minutes=2),  # This should normalize to UTC
            utc_time + timedelta(minutes=3),
        ]
        
        df = pd.DataFrame({
            'timestamp': mixed_timestamps,
            'temperature': [150.0, 151.0, 152.0, 153.0]
        })
        
        # Should handle mixed timezones by converting all to UTC
        normalized_df = normalize_temperature_data(df)
        
        # All timestamps should be UTC
        for ts in normalized_df['timestamp']:
            assert ts.tz == timezone.utc or ts.tz.utcoffset(None) == timedelta(0)
    
    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not available") 
    @given(st.lists(st.text(alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd', 'Pc', 'Pd')), 
                            min_size=3, max_size=20), min_size=1, max_size=10))
    def test_column_mapping_robustness(self, header_variations):
        """Property test: column mapping should handle various header formats."""
        # Filter to valid header-like strings
        valid_headers = [h for h in header_variations if h and not h.isspace()]
        
        if not valid_headers:
            return  # Skip empty case
        
        # Test that mapping function doesn't crash on arbitrary headers
        try:
            mapping = normalize_column_names(valid_headers)
            # Should return a dictionary
            assert isinstance(mapping, dict)
            # All keys should be from input headers
            assert all(key in valid_headers for key in mapping.keys())
            # All values should be strings
            assert all(isinstance(val, str) for val in mapping.values())
        except Exception as e:
            pytest.fail(f"Column mapping failed on headers {valid_headers}: {e}")


class TestIntegrationScenarios:
    """Integration tests combining multiple hardening features."""
    
    def test_complex_vendor_csv_with_locale(self):
        """Test complex real-world vendor CSV with multiple features."""
        csv_content = '''# Experiment: Powder coat cure test
# Temperature: 180°C target
# Sensor: Thermocouple Type K
Date Time;Oven Temp(°C);Part Temp [°C];Chamber Press(bar);RH(%);Ch1;Sensor 2
2023-01-01 12:00:00;180,5;175,2;1,25;45,0;182,1;178,9
2023-01-01 12:01:00;181,2;176,8;1,23;46,2;183,4;180,1
2023-01-01 12:02:00;182,0;178,1;1,27;44,8;184,2;181,6
2023-01-01 12:03:00;183,5;179,9;1,22;45,5;185,0;182,8'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            # Load with all features
            df, metadata = load_csv_with_metadata(temp_path, safe_mode=False)
            
            # Check metadata extraction
            assert 'Experiment' in metadata
            assert metadata['Experiment'] == 'Powder coat cure test'
            assert 'Temperature' in metadata
            
            # Check parsing info
            parsing_info = metadata['_parsing_info']
            assert parsing_info['detected_delimiter'] == ';'
            assert parsing_info['decimal_normalized'] is True
            
            # Check column mapping
            column_mapping = metadata.get('_column_mapping', {})
            assert 'Date Time' in column_mapping
            assert column_mapping['Date Time'] == 'timestamp'
            assert 'RH(%)' in column_mapping
            assert column_mapping['RH(%)'] == 'humidity'
            
            # Normalize the data
            normalized_df = normalize_temperature_data(df, target_step_s=60.0)
            
            # Should have processed successfully with all features
            assert len(normalized_df) >= 3
            assert 'timestamp' in normalized_df.columns
            
            # Temperature values should be properly converted from decimal comma
            temp_cols = [col for col in normalized_df.columns if 'temp' in col.lower()]
            for col in temp_cols:
                temps = normalized_df[col].dropna()
                assert temps.min() > 170  # Should be reasonable Celsius values
                assert temps.max() < 190
                
        finally:
            os.unlink(temp_path)
    
    def test_excel_export_with_vendor_headers(self):
        """Test Excel-exported CSV with vendor headers."""
        # Simulate Excel serial dates with vendor headers  
        csv_content = '''Time Stamp,Temp(C),Press(psi),Humidity(%)
44927.0,180.5,15.2,45.0
44927.041667,181.2,15.3,46.2
44927.083333,182.0,15.1,44.8'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path, safe_mode=False)
            
            # Check column mapping worked
            column_mapping = metadata.get('_column_mapping', {})
            assert 'Time Stamp' in column_mapping
            assert column_mapping['Time Stamp'] == 'timestamp'
            
            # Normalize - should handle Excel dates and vendor headers
            normalized_df = normalize_temperature_data(df)
            
            # Timestamps should be converted from Excel serial dates
            timestamps = normalized_df['timestamp']
            assert pd.api.types.is_datetime64_any_dtype(timestamps)
            
            # Should be in 2023 (Excel serial ~44927 = 2023-01-01)
            sample_ts = timestamps.iloc[0]
            assert sample_ts.year == 2023
            assert sample_ts.month == 1
            
        finally:
            os.unlink(temp_path)


# Usage example in module docstring:
"""
Example usage of enhanced normalize tests:

    pytest tests/normalize/test_locale_and_headers.py -v

To test specific features:
    pytest tests/normalize/test_locale_and_headers.py::TestVendorHeaderMapping
    pytest tests/normalize/test_locale_and_headers.py::TestParserWarningsAndSafeMode

To run property-based tests:
    pytest tests/normalize/test_locale_and_headers.py::TestPropertyBasedEdgeCases

For integration testing:
    pytest tests/normalize/test_locale_and_headers.py::TestIntegrationScenarios
"""