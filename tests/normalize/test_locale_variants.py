"""
Tests for locale-specific CSV variants.

Handles "1.234,56" vs "1,234.56", tab delimiter, CRLF line endings.
"""
import pandas as pd
import pytest
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

from core.normalize import (
    load_csv_with_metadata,
    normalize_decimal_separators,
    detect_delimiter,
    detect_encoding,
    normalize_temperature_data,
    NormalizationError
)


class TestLocaleVariants:
    """Test CSV parsing with various locale-specific formats."""
    
    def test_european_decimal_comma_format(self):
        """Test handling of European decimal comma format (1.234,56)."""
        csv_content = '''timestamp;temperature_c
2023-01-01T12:00:00;150,5
2023-01-01T12:01:00;1.234,56
2023-01-01T12:02:00;175,0
2023-01-01T12:03:00;2.345,67'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Check parsing information
            assert metadata['_parsing_info']['detected_delimiter'] == ';'
            assert metadata['_parsing_info']['decimal_normalized'] is True
            
            # Check that decimal commas were converted to dots
            assert df['temperature_c'].iloc[0] == 150.5
            assert df['temperature_c'].iloc[1] == 1234.56
            assert df['temperature_c'].iloc[2] == 175.0
            assert df['temperature_c'].iloc[3] == 2345.67
            
        finally:
            os.unlink(temp_path)
    
    def test_tab_delimited_csv(self):
        """Test parsing of tab-delimited CSV files."""
        csv_content = '''timestamp\ttemp_probe_1\ttemp_probe_2
2023-01-01T12:00:00\t150.5\t148.2
2023-01-01T12:01:00\t152.1\t149.8
2023-01-01T12:02:00\t153.7\t151.4'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Check delimiter detection
            assert metadata['_parsing_info']['detected_delimiter'] == '\t'
            
            # Check data parsing
            assert len(df) == 3
            assert len(df.columns) == 3
            assert 'timestamp' in df.columns
            assert 'temp_probe_1' in df.columns
            assert 'temp_probe_2' in df.columns
            
            # Check values
            assert df['temp_probe_1'].iloc[0] == 150.5
            assert df['temp_probe_2'].iloc[2] == 151.4
            
        finally:
            os.unlink(temp_path)
    
    def test_pipe_delimited_csv(self):
        """Test parsing of pipe-delimited CSV files."""
        csv_content = '''timestamp|temperature|pressure
2023-01-01T12:00:00|150.5|1.2
2023-01-01T12:01:00|152.1|1.25
2023-01-01T12:02:00|153.7|1.18'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Check delimiter detection
            assert metadata['_parsing_info']['detected_delimiter'] == '|'
            
            # Check data parsing
            assert len(df) == 3
            assert 'temperature' in df.columns
            assert df['temperature'].iloc[1] == 152.1
            
        finally:
            os.unlink(temp_path)
    
    def test_crlf_line_endings(self):
        """Test handling of Windows CRLF line endings."""
        # Create content with CRLF line endings
        csv_content = 'timestamp,temperature\r\n2023-01-01T12:00:00,150.5\r\n2023-01-01T12:01:00,152.1\r\n'
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write(csv_content.encode('utf-8'))
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Should parse correctly despite CRLF
            assert len(df) == 2
            assert 'temperature' in df.columns
            assert df['temperature'].iloc[0] == 150.5
            assert df['temperature'].iloc[1] == 152.1
            
        finally:
            os.unlink(temp_path)
    
    def test_windows_1252_encoding(self):
        """Test handling of Windows-1252 encoded files."""
        # Content with Windows-1252 specific characters
        csv_content = '''timestamp,temperature,notes
2023-01-01T12:00:00,150.5,"Température élevée"
2023-01-01T12:01:00,152.1,"Mesure précise"'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='cp1252') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Should detect encoding and parse correctly
            detected_encoding = metadata['_parsing_info']['detected_encoding']
            assert detected_encoding in ['cp1252', 'latin1']  # chardet may return either
            
            assert len(df) == 2
            assert 'temperature' in df.columns
            assert df['temperature'].iloc[0] == 150.5
            
        finally:
            os.unlink(temp_path)
    
    def test_utf8_bom(self):
        """Test handling of UTF-8 files with BOM."""
        csv_content = '''timestamp,temperature
2023-01-01T12:00:00,150.5
2023-01-01T12:01:00,152.1'''
        
        # Write with UTF-8 BOM
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write('\ufeff'.encode('utf-8'))  # BOM
            f.write(csv_content.encode('utf-8'))
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Should detect UTF-8 with BOM
            assert metadata['_parsing_info']['detected_encoding'] == 'utf-8-sig'
            
            # Should parse data correctly
            assert len(df) == 2
            assert 'temperature' in df.columns
            assert df['temperature'].iloc[0] == 150.5
            
        finally:
            os.unlink(temp_path)
    
    def test_mixed_thousand_separator_and_decimal_comma(self):
        """Test complex European format with thousand separators and decimal commas."""
        csv_content = '''timestamp;temperature;pressure
2023-01-01T12:00:00;1.234,56;1.025,7
2023-01-01T12:01:00;12.345,67;998,45
2023-01-01T12:02:00;234,5;1.100,0'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Check that complex European format was handled correctly
            assert df['temperature'].iloc[0] == 1234.56  # 1.234,56 -> 1234.56
            assert df['temperature'].iloc[1] == 12345.67  # 12.345,67 -> 12345.67
            assert df['temperature'].iloc[2] == 234.5    # 234,5 -> 234.5
            
            assert df['pressure'].iloc[0] == 1025.7     # 1.025,7 -> 1025.7
            assert df['pressure'].iloc[1] == 998.45     # 998,45 -> 998.45
            assert df['pressure'].iloc[2] == 1100.0     # 1.100,0 -> 1100.0
            
        finally:
            os.unlink(temp_path)
    
    def test_metadata_with_special_characters(self):
        """Test metadata extraction with locale-specific characters."""
        csv_content = '''# Expérience: Test de cuisson poudre
# Température: 180°C
# Durée: 10 minutes
timestamp,temperature
2023-01-01T12:00:00,150.5
2023-01-01T12:01:00,152.1'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Check that metadata with special characters was extracted
            assert 'Expérience' in metadata
            assert metadata['Expérience'] == 'Test de cuisson poudre'
            assert 'Température' in metadata
            assert metadata['Température'] == '180°C'
            assert 'Durée' in metadata
            assert metadata['Durée'] == '10 minutes'
            
        finally:
            os.unlink(temp_path)


class TestDecimalNormalization:
    """Test decimal separator normalization functions."""
    
    def test_normalize_decimal_separators_european(self):
        """Test normalization of European decimal format."""
        text = "1.234,56\n2.345,67\n1.000,0"
        result = normalize_decimal_separators(text)
        
        expected = "1234.56\n2345.67\n1000.0"
        assert result == expected
    
    def test_normalize_decimal_separators_simple_comma(self):
        """Test normalization of simple comma decimals."""
        text = "150,5\n175,0\n200,25"
        result = normalize_decimal_separators(text)
        
        expected = "150.5\n175.0\n200.25"
        assert result == expected
    
    def test_normalize_decimal_separators_mixed_format(self):
        """Test normalization with mixed formats in same text."""
        text = "timestamp,temperature\n2023-01-01,150,5\n2023-01-02,1.234,56"
        result = normalize_decimal_separators(text)
        
        # Should handle both simple comma (150,5) and European format (1.234,56)
        lines = result.split('\n')
        assert '150.5' in lines[1]
        assert '1234.56' in lines[2]
    
    def test_normalize_decimal_separators_preserves_non_numeric(self):
        """Test that non-numeric commas are preserved."""
        text = "timestamp,temperature,notes\n2023-01-01,150,5,\"Good, stable reading\""
        result = normalize_decimal_separators(text)
        
        # Comma in quoted string should be preserved
        assert '"Good, stable reading"' in result
        # Decimal comma should be converted
        assert '150.5' in result
    
    def test_normalize_decimal_separators_no_change_us_format(self):
        """Test that US format numbers are left unchanged."""
        text = "1,234.56\n2,345.67\n150.5"
        result = normalize_decimal_separators(text)
        
        # Should remain unchanged as it's already US format
        assert result == text


class TestDelimiterDetection:
    """Test delimiter detection with various formats."""
    
    def test_detect_delimiter_comma(self):
        """Test detection of comma delimiter."""
        csv_content = '''timestamp,temperature
2023-01-01T12:00:00,150.5'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            delimiter = detect_delimiter(temp_path)
            assert delimiter == ','
        finally:
            os.unlink(temp_path)
    
    def test_detect_delimiter_semicolon(self):
        """Test detection of semicolon delimiter."""
        csv_content = '''timestamp;temperature
2023-01-01T12:00:00;150,5'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            delimiter = detect_delimiter(temp_path)
            assert delimiter == ';'
        finally:
            os.unlink(temp_path)
    
    def test_detect_delimiter_tab(self):
        """Test detection of tab delimiter."""
        csv_content = '''timestamp\ttemperature
2023-01-01T12:00:00\t150.5'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            delimiter = detect_delimiter(temp_path)
            assert delimiter == '\t'
        finally:
            os.unlink(temp_path)
    
    def test_detect_delimiter_with_comments(self):
        """Test delimiter detection skips comment lines."""
        csv_content = '''# This is a comment with, commas and; semicolons
# Another comment with\ttabs
timestamp;temperature
2023-01-01T12:00:00;150,5'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            delimiter = detect_delimiter(temp_path)
            assert delimiter == ';'  # Should detect from data lines, not comments
        finally:
            os.unlink(temp_path)
    
    def test_detect_delimiter_fallback(self):
        """Test delimiter detection fallback to comma."""
        csv_content = '''singlecolumnheader
singlevalue'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            delimiter = detect_delimiter(temp_path)
            assert delimiter == ','  # Should fallback to comma
        finally:
            os.unlink(temp_path)


class TestEncodingDetection:
    """Test encoding detection for various file formats."""
    
    def test_detect_encoding_utf8(self):
        """Test UTF-8 encoding detection."""
        csv_content = 'timestamp,temperature\n2023-01-01T12:00:00,150.5'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            encoding = detect_encoding(temp_path)
            assert encoding in ['utf-8', 'ascii']  # ASCII is subset of UTF-8
        finally:
            os.unlink(temp_path)
    
    def test_detect_encoding_utf8_bom(self):
        """Test UTF-8 BOM detection."""
        csv_content = 'timestamp,temperature\n2023-01-01T12:00:00,150.5'
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write('\ufeff'.encode('utf-8'))  # BOM
            f.write(csv_content.encode('utf-8'))
            temp_path = f.name
        
        try:
            encoding = detect_encoding(temp_path)
            assert encoding == 'utf-8-sig'
        finally:
            os.unlink(temp_path)
    
    def test_detect_encoding_windows1252(self):
        """Test Windows-1252 encoding detection."""
        csv_content = 'timestamp,température\n2023-01-01T12:00:00,150.5'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='cp1252') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            encoding = detect_encoding(temp_path)
            # chardet may return different but compatible encodings
            assert encoding in ['cp1252', 'windows-1252', 'latin1', 'iso-8859-1']
        finally:
            os.unlink(temp_path)


class TestFullNormalizationWithLocaleVariants:
    """Test full normalization pipeline with locale-specific data."""
    
    def test_full_normalization_european_format(self):
        """Test complete normalization with European CSV format."""
        csv_content = '''# Test: European format powder coat cure
timestamp;temp_oven_c;temp_part_c
2023-01-01T12:00:00;180,5;175,2
2023-01-01T12:01:00;181,2;176,8
2023-01-01T12:02:00;182,0;178,1
2023-01-01T12:03:00;183,5;179,9
2023-01-01T12:04:00;184,2;181,0'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Should have detected semicolon delimiter and normalized decimals
            assert metadata['_parsing_info']['detected_delimiter'] == ';'
            assert metadata['_parsing_info']['decimal_normalized'] is True
            
            # Normalize the data
            normalized_df = normalize_temperature_data(df, target_step_s=60.0)
            
            # Should have processed successfully
            assert len(normalized_df) >= 3  # May be resampled
            assert 'timestamp' in normalized_df.columns
            temp_cols = [col for col in normalized_df.columns if 'temp' in col.lower()]
            assert len(temp_cols) >= 2
            
            # Temperature values should be in reasonable range
            for col in temp_cols:
                temps = normalized_df[col].dropna()
                assert temps.min() > 170  # Should be in Celsius range
                assert temps.max() < 190
            
        finally:
            os.unlink(temp_path)
    
    def test_full_normalization_with_trace(self):
        """Test normalization with trace information for locale handling."""
        csv_content = '''timestamp;temperature_f
2023-01-01T12:00:00;356,0
2023-01-01T12:01:00;358,4
2023-01-01T12:02:00;361,2'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            temp_path = f.name
        
        try:
            df, metadata = load_csv_with_metadata(temp_path)
            
            # Normalize with trace
            result = normalize_temperature_data(df, return_trace=True)
            
            # Should return NormalizedTrace
            assert hasattr(result, 'dataframe')
            assert hasattr(result, 'trace')
            
            # Check trace information
            trace_json = result.to_json()
            assert 'processing_steps' in trace_json
            assert 'conversions' in trace_json
            
            # Should have detected and converted Fahrenheit
            conversions = result.trace.get('conversions', [])
            assert any('Fahrenheit to Celsius' in conv for conv in conversions)
            
            # Final temperatures should be in Celsius range
            temps = result.dataframe['temperature_f'].dropna()
            assert temps.min() > 150  # Should be converted to ~180C range
            assert temps.max() < 200
            
        finally:
            os.unlink(temp_path)


# Usage example in module docstring:
"""
Example usage of locale variant testing:

    pytest tests/normalize/test_locale_variants.py -v

To test specific locale handling:
    pytest tests/normalize/test_locale_variants.py::TestLocaleVariants::test_european_decimal_comma_format

To test with various encodings:
    pytest tests/normalize/test_locale_variants.py::TestEncodingDetection
"""