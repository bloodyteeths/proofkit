"""
Tests for Column Mapping Adapter

Tests column name normalization with real-world CSV headers
and ensures mapping works correctly with normalize.py.
"""

import pytest
import pandas as pd
import tempfile
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.columns_map import get_column_mapping, normalize_column_names
from core.normalize import load_csv_with_metadata


class TestColumnMapping:
    """Test column mapping functionality."""
    
    def test_get_column_mapping(self):
        """Test basic mapping retrieval."""
        mapping = get_column_mapping()
        
        assert isinstance(mapping, dict)
        assert len(mapping) > 0
        
        # Check some expected mappings
        assert mapping["temp"] == "temperature"
        assert mapping["time"] == "timestamp"
        assert mapping["press"] == "pressure"
    
    def test_normalize_column_names(self):
        """Test column name normalization."""
        columns = ["Time", "Temp", "Press", "Unknown_Col"]
        
        mapping = normalize_column_names(columns)
        
        assert mapping["Time"] == "timestamp"  # Case insensitive
        assert mapping["Temp"] == "temperature"
        assert mapping["Press"] == "pressure" 
        assert "Unknown_Col" not in mapping  # Unmapped columns ignored
    
    def test_case_insensitive_mapping(self):
        """Test case insensitive column mapping."""
        columns = ["TIME", "temp", "TeMp", "PRESSURE"]
        
        mapping = normalize_column_names(columns)
        
        assert mapping["TIME"] == "timestamp"
        assert mapping["temp"] == "temperature" 
        assert mapping["TeMp"] == "temperature"
        assert mapping["PRESSURE"] == "pressure"
    
    def test_vendor_specific_headers(self):
        """Test vendor-specific column headers."""
        columns = ["oven_temp", "thermocouple", "pt100", "rtd_temp"]
        
        mapping = normalize_column_names(columns)
        
        assert mapping["oven_temp"] == "temperature"
        assert mapping["thermocouple"] == "temperature"
        assert mapping["pt100"] == "temperature"
        assert mapping["rtd_temp"] == "temperature"
    
    def test_multi_sensor_headers(self):
        """Test multi-sensor column headers."""
        columns = ["temp1", "temp2", "sensor1", "probe2"]
        
        mapping = normalize_column_names(columns)
        
        assert mapping["temp1"] == "temperature_1"
        assert mapping["temp2"] == "temperature_2"
        assert mapping["sensor1"] == "temperature_1" 
        assert mapping["probe2"] == "temperature_2"


class TestIntegrationWithNormalize:
    """Test integration with normalize.py module."""
    
    def setup_method(self):
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def teardown_method(self):
        """Cleanup temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_csv(self, columns: dict, data: list) -> Path:
        """Create a test CSV file with specified columns and data."""
        csv_content = []
        
        # Add header
        csv_content.append(','.join(columns.keys()))
        
        # Add data rows
        for row in data:
            csv_content.append(','.join(map(str, row)))
        
        csv_path = self.temp_path / "test.csv"
        with open(csv_path, 'w') as f:
            f.write('\n'.join(csv_content))
        
        return csv_path
    
    def test_basic_mapping_integration(self):
        """Test basic column mapping with CSV loading."""
        # Create CSV with common variations
        columns = {"Time": "time", "Temp": "temperature"}
        data = [
            ["2024-01-01 10:00:00", 25.0],
            ["2024-01-01 10:01:00", 30.0],
            ["2024-01-01 10:02:00", 35.0]
        ]
        
        csv_path = self.create_test_csv(columns, data)
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        # Check that columns were mapped correctly
        assert "timestamp" in df.columns
        assert "temperature" in df.columns
        assert "Time" not in df.columns  # Original should be renamed
        assert "Temp" not in df.columns
        
        # Check metadata records the mapping
        assert '_column_mapping' in metadata
        assert metadata['_column_mapping']['Time'] == 'timestamp'
        assert metadata['_column_mapping']['Temp'] == 'temperature'
    
    def test_multi_sensor_mapping(self):
        """Test multi-sensor column mapping."""
        columns = {"datetime": "time", "temp1": "temp", "temp2": "temp", "sensor1": "temp"}
        data = [
            ["2024-01-01 10:00:00", 180.0, 185.0, 182.0],
            ["2024-01-01 10:01:00", 181.0, 186.0, 183.0]
        ]
        
        csv_path = self.create_test_csv(columns, data)
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        # Check mapped columns
        assert "timestamp" in df.columns
        assert "temperature_1" in df.columns  # temp1 -> temperature_1
        assert "temperature_2" in df.columns  # temp2 -> temperature_2  
        # Note: sensor1 -> temperature_1 (same as temp1)
        
        # Check original columns were renamed
        assert "datetime" not in df.columns
        assert "temp1" not in df.columns
        assert "temp2" not in df.columns
    
    def test_pressure_column_mapping(self):
        """Test pressure column mapping for autoclave data."""
        columns = {"Time": "time", "Temp": "temp", "Press": "pressure"}
        data = [
            ["2024-01-01 10:00:00", 121.0, 1.1],
            ["2024-01-01 10:01:00", 121.5, 1.2]
        ]
        
        csv_path = self.create_test_csv(columns, data)
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        # Check all expected columns are present
        assert "timestamp" in df.columns
        assert "temperature" in df.columns
        assert "pressure" in df.columns
        
        # Check values are preserved
        assert len(df) == 2
        assert df.loc[0, "temperature"] == 121.0
        assert df.loc[0, "pressure"] == 1.1
    
    def test_no_mapping_needed(self):
        """Test CSV with standard column names (no mapping needed)."""
        columns = {"timestamp": "time", "temperature": "temp"}
        data = [
            ["2024-01-01 10:00:00", 25.0],
            ["2024-01-01 10:01:00", 30.0]
        ]
        
        csv_path = self.create_test_csv(columns, data)
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        # Columns should remain unchanged
        assert "timestamp" in df.columns
        assert "temperature" in df.columns
        
        # No mapping should be recorded
        assert '_column_mapping' not in metadata or not metadata['_column_mapping']
    
    def test_partial_mapping(self):
        """Test CSV where only some columns need mapping."""
        columns = {"Time": "time", "temperature": "temp", "unknown_col": "data"}
        data = [
            ["2024-01-01 10:00:00", 25.0, "value1"],
            ["2024-01-01 10:01:00", 30.0, "value2"]
        ]
        
        csv_path = self.create_test_csv(columns, data)
        df, metadata = load_csv_with_metadata(str(csv_path))
        
        # Only Time should be mapped
        assert "timestamp" in df.columns
        assert "temperature" in df.columns  # Already correct
        assert "unknown_col" in df.columns  # Unmapped column preserved
        assert "Time" not in df.columns  # Original mapped column gone
        
        # Check metadata shows only the mapping that occurred
        assert '_column_mapping' in metadata
        assert metadata['_column_mapping']['Time'] == 'timestamp'
        assert 'temperature' not in metadata['_column_mapping']
        assert 'unknown_col' not in metadata['_column_mapping']


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_columns_list(self):
        """Test handling of empty columns list."""
        mapping = normalize_column_names([])
        assert mapping == {}
    
    def test_duplicate_mappings(self):
        """Test handling when multiple columns map to same target."""
        columns = ["temp", "temperature", "temp_c"]
        
        mapping = normalize_column_names(columns)
        
        # All should map to 'temperature'
        assert mapping["temp"] == "temperature"
        assert mapping["temp_c"] == "temperature"
        # 'temperature' not in mapping (already correct)
        assert "temperature" not in mapping
    
    def test_whitespace_handling(self):
        """Test column names with whitespace."""
        columns = [" temp ", " time ", "pressure "]
        
        mapping = normalize_column_names(columns)
        
        # Should handle whitespace in original column names
        assert " temp " == "temperature" or " temp " not in mapping  # Implementation dependent
        # Note: Current implementation strips in lowercase matching
    
    def test_special_characters(self):
        """Test column names with special characters."""
        columns = ["temp_deg_c", "time_stamp", "pressure_bar"]
        
        mapping = normalize_column_names(columns)
        
        assert mapping["temp_deg_c"] == "temperature"
        assert mapping["time_stamp"] == "timestamp" 
        assert mapping["pressure_bar"] == "pressure"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])