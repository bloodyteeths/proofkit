"""
Tests for the registry sanity checker.

Tests the validation logic, error handling, and report generation
of the registry sanity checker system.
"""

import pytest
import json
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.registry_sanity import RegistrySanityChecker


class TestRegistrySanityChecker:
    """Test cases for RegistrySanityChecker class."""
    
    def create_test_registry(self, datasets: dict) -> str:
        """Helper to create temporary registry file."""
        registry_data = {
            "schema_version": "1.0",
            "created": "2025-08-08",
            "description": "Test registry",
            "datasets": datasets
        }
        
        temp_file = NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        yaml.dump(registry_data, temp_file, default_flow_style=False)
        temp_file.close()
        return temp_file.name
    
    def create_test_csv(self, data: dict) -> str:
        """Helper to create temporary CSV file."""
        df = pd.DataFrame(data)
        temp_file = NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df.to_csv(temp_file.name, index=False)
        temp_file.close()
        return temp_file.name
    
    def create_test_spec(self, spec_data: dict) -> str:
        """Helper to create temporary spec JSON file."""
        temp_file = NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(spec_data, temp_file, indent=2)
        temp_file.close()
        return temp_file.name
    
    def test_init_default_path(self):
        """Test checker initialization with default path."""
        checker = RegistrySanityChecker()
        assert checker.registry_path.name == "registry.yaml"
        assert "timestamp" in checker.report
        assert checker.report["summary"]["total_datasets"] == 0
    
    def test_init_custom_path(self):
        """Test checker initialization with custom path."""
        custom_path = "custom/path/registry.yaml"
        checker = RegistrySanityChecker(custom_path)
        assert str(checker.registry_path) == custom_path
    
    def test_load_registry_success(self):
        """Test successful registry loading."""
        datasets = {
            "test_dataset": {
                "id": "test_001",
                "industry": "powder",
                "csv_path": "test.csv",
                "spec_path": "test.json",
                "expected_outcome": "PASS"
            }
        }
        
        registry_path = self.create_test_registry(datasets)
        
        try:
            checker = RegistrySanityChecker(registry_path)
            loaded_datasets = checker.load_registry()
            assert loaded_datasets == datasets
        finally:
            Path(registry_path).unlink()
    
    def test_load_registry_file_not_found(self):
        """Test registry loading when file doesn't exist."""
        checker = RegistrySanityChecker("nonexistent.yaml")
        
        with pytest.raises(Exception):
            checker.load_registry()
        
        assert "Failed to load registry" in checker.report["errors"][0]
    
    def test_load_registry_invalid_format(self):
        """Test registry loading with invalid YAML format."""
        temp_file = NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        temp_file.write("invalid: yaml: content: [")
        temp_file.close()
        
        try:
            checker = RegistrySanityChecker(temp_file.name)
            with pytest.raises(Exception):
                checker.load_registry()
        finally:
            Path(temp_file.name).unlink()
    
    def test_validate_dataset_entry_missing_fields(self):
        """Test validation with missing required fields."""
        checker = RegistrySanityChecker()
        
        # Dataset missing required fields
        dataset_config = {
            "id": "test_001",
            # Missing industry, csv_path, spec_path, expected_outcome
        }
        
        result = checker.validate_dataset_entry("test", dataset_config)
        
        assert result["status"] == "error"
        assert len(result["errors"]) >= 3  # Missing multiple fields
        assert any("Missing required field" in error for error in result["errors"])
    
    def test_validate_dataset_entry_files_not_found(self):
        """Test validation when CSV/spec files don't exist."""
        checker = RegistrySanityChecker()
        
        dataset_config = {
            "id": "test_001",
            "industry": "powder",
            "csv_path": "nonexistent.csv",
            "spec_path": "nonexistent.json",
            "expected_outcome": "PASS"
        }
        
        result = checker.validate_dataset_entry("test", dataset_config)
        
        assert result["status"] == "error"
        assert any("CSV file not found" in error for error in result["errors"])
        assert any("Spec file not found" in error for error in result["errors"])
    
    @patch('scripts.registry_sanity.validate_spec_schema')
    @patch('scripts.registry_sanity.models.ProcessSpec.model_validate')
    def test_validate_dataset_entry_invalid_spec(self, mock_validate, mock_schema):
        """Test validation with invalid spec file."""
        # Setup mocks to raise validation error
        mock_schema.side_effect = Exception("Invalid spec schema")
        
        checker = RegistrySanityChecker()
        
        # Create temporary files
        csv_data = {
            'timestamp': ['2025-08-08T10:00:00Z', '2025-08-08T10:01:00Z'],
            'temperature': [180.0, 181.0]
        }
        csv_path = self.create_test_csv(csv_data)
        spec_path = self.create_test_spec({"invalid": "spec"})
        
        try:
            dataset_config = {
                "id": "test_001",
                "industry": "powder",
                "csv_path": csv_path,
                "spec_path": spec_path,
                "expected_outcome": "PASS"
            }
            
            # Override paths to use absolute paths
            checker.root_path = Path("/")
            
            result = checker.validate_dataset_entry("test", dataset_config)
            
            assert result["status"] == "error"
            assert any("Spec validation failed" in error for error in result["errors"])
            assert result["metrics"]["spec_valid"] is False
            
        finally:
            Path(csv_path).unlink()
            Path(spec_path).unlink()
    
    def test_validate_dataset_entry_successful_validation(self):
        """Test successful dataset validation."""
        checker = RegistrySanityChecker()
        
        # Create test data
        csv_data = {
            'timestamp': pd.date_range('2025-08-08T10:00:00Z', periods=100, freq='30S'),
            'temperature': [180.0 + i * 0.1 for i in range(100)]
        }
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_job"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600
            },
            "data_requirements": {
                "max_sample_period_s": 60,
                "allowed_gaps_s": 120
            }
        }
        
        csv_path = self.create_test_csv(csv_data)
        spec_path = self.create_test_spec(spec_data)
        
        try:
            dataset_config = {
                "id": "test_001",
                "industry": "powder",
                "csv_path": csv_path,
                "spec_path": spec_path,
                "expected_outcome": "PASS"
            }
            
            # Override paths to use absolute paths
            checker.root_path = Path("/")
            
            # Mock the validation functions to succeed
            with patch('scripts.registry_sanity.validate_spec_schema'):
                with patch('scripts.registry_sanity.models.ProcessSpec.model_validate'):
                    result = checker.validate_dataset_entry("test", dataset_config)
            
            assert result["status"] in ["passed", "warning"]
            assert result["metrics"]["csv_loadable"] is True
            assert result["metrics"]["spec_valid"] is True
            assert result["metrics"]["sample_count"] == 100
            assert "mean_step_s" in result["metrics"]
            assert result["metrics"]["temperature_column_count"] >= 1
            
        finally:
            Path(csv_path).unlink()
            Path(spec_path).unlink()
    
    def test_validate_dataset_entry_duplicate_timestamps(self):
        """Test validation detects duplicate timestamps."""
        checker = RegistrySanityChecker()
        
        # Create CSV with duplicate timestamps
        csv_data = {
            'timestamp': ['2025-08-08T10:00:00Z', '2025-08-08T10:00:00Z', '2025-08-08T10:01:00Z'],
            'temperature': [180.0, 180.5, 181.0]
        }
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_job"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600
            },
            "data_requirements": {
                "max_sample_period_s": 60,
                "allowed_gaps_s": 120
            }
        }
        
        csv_path = self.create_test_csv(csv_data)
        spec_path = self.create_test_spec(spec_data)
        
        try:
            dataset_config = {
                "id": "test_001",
                "industry": "powder",
                "csv_path": csv_path,
                "spec_path": spec_path,
                "expected_outcome": "ERROR"  # Should be ERROR due to duplicates
            }
            
            checker.root_path = Path("/")
            
            with patch('scripts.registry_sanity.validate_spec_schema'):
                with patch('scripts.registry_sanity.models.ProcessSpec.model_validate'):
                    result = checker.validate_dataset_entry("test", dataset_config)
            
            assert result["metrics"]["duplicate_timestamps"] > 0
            assert any("duplicate timestamps" in warning.lower() for warning in result["warnings"])
            
        finally:
            Path(csv_path).unlink()
            Path(spec_path).unlink()
    
    def test_validate_dataset_entry_no_temperature_columns(self):
        """Test validation when no temperature columns found."""
        checker = RegistrySanityChecker()
        
        # Create CSV without temperature columns
        csv_data = {
            'timestamp': ['2025-08-08T10:00:00Z', '2025-08-08T10:01:00Z'],
            'pressure': [1013.25, 1013.30]  # No temperature column
        }
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_job"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600
            },
            "data_requirements": {
                "max_sample_period_s": 60,
                "allowed_gaps_s": 120
            }
        }
        
        csv_path = self.create_test_csv(csv_data)
        spec_path = self.create_test_spec(spec_data)
        
        try:
            dataset_config = {
                "id": "test_001",
                "industry": "powder", 
                "csv_path": csv_path,
                "spec_path": spec_path,
                "expected_outcome": "ERROR"
            }
            
            checker.root_path = Path("/")
            
            with patch('scripts.registry_sanity.validate_spec_schema'):
                with patch('scripts.registry_sanity.models.ProcessSpec.model_validate'):
                    result = checker.validate_dataset_entry("test", dataset_config)
            
            assert result["status"] == "error"
            assert any("No temperature columns found" in error for error in result["errors"])
            
        finally:
            Path(csv_path).unlink()
            Path(spec_path).unlink()
    
    def test_run_validation_empty_registry(self):
        """Test running validation on empty registry."""
        datasets = {}
        registry_path = self.create_test_registry(datasets)
        
        try:
            checker = RegistrySanityChecker(registry_path)
            report = checker.run_validation()
            
            assert report["summary"]["total_datasets"] == 0
            assert report["summary"]["passed_validation"] == 0
            assert report["summary"]["failed_validation"] == 0
            assert report["summary"]["errors"] == 0
            assert len(report["results"]) == 0
            
        finally:
            Path(registry_path).unlink()
    
    def test_run_validation_multiple_datasets(self):
        """Test running validation on registry with multiple datasets."""
        # Create minimal valid test files
        csv_data = {
            'timestamp': ['2025-08-08T10:00:00Z', '2025-08-08T10:01:00Z'],
            'temperature': [180.0, 181.0]
        }
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_job"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600
            },
            "data_requirements": {
                "max_sample_period_s": 60,
                "allowed_gaps_s": 120
            }
        }
        
        csv_path = self.create_test_csv(csv_data)
        spec_path = self.create_test_spec(spec_data)
        
        try:
            datasets = {
                "dataset_1": {
                    "id": "test_001",
                    "industry": "powder",
                    "csv_path": csv_path,
                    "spec_path": spec_path,
                    "expected_outcome": "PASS"
                },
                "dataset_2": {
                    "id": "test_002", 
                    "industry": "powder",
                    "csv_path": "nonexistent.csv",  # This should fail
                    "spec_path": "nonexistent.json",
                    "expected_outcome": "PASS"
                }
            }
            
            registry_path = self.create_test_registry(datasets)
            
            checker = RegistrySanityChecker(registry_path)
            checker.root_path = Path("/")  # Use absolute paths
            
            with patch('scripts.registry_sanity.validate_spec_schema'):
                with patch('scripts.registry_sanity.models.ProcessSpec.model_validate'):
                    report = checker.run_validation()
            
            assert report["summary"]["total_datasets"] == 2
            assert "dataset_1" in report["results"]
            assert "dataset_2" in report["results"]
            
            # dataset_1 should pass or warn, dataset_2 should error
            assert report["results"]["dataset_2"]["status"] == "error"
            assert report["summary"]["errors"] >= 1
            
        finally:
            Path(csv_path).unlink()
            Path(spec_path).unlink()
            Path(registry_path).unlink()
    
    def test_save_report(self):
        """Test saving validation report to file."""
        checker = RegistrySanityChecker()
        
        # Add some test data to report
        checker.report["test_data"] = "test_value"
        
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_report.json"
            checker.save_report(str(output_path))
            
            assert output_path.exists()
            
            with open(output_path, 'r') as f:
                saved_report = json.load(f)
            
            assert saved_report["test_data"] == "test_value"
            assert "timestamp" in saved_report
    
    def test_temperature_unit_detection(self):
        """Test temperature unit detection logic."""
        checker = RegistrySanityChecker()
        
        # Test cases for different temperature ranges
        test_cases = [
            ([180.0, 185.0, 190.0], "celsius"),  # Clearly Celsius
            ([356.0, 365.0, 374.0], "celsius"),  # High temp, likely Celsius  
            ([75.0, 80.0, 85.0], "uncertain"),   # Could be C or F
            ([5.0, 10.0, 15.0], "celsius_or_other")  # Low temp
        ]
        
        for temps, expected_units in test_cases:
            csv_data = {
                'timestamp': [f'2025-08-08T10:0{i}:00Z' for i in range(len(temps))],
                'temperature': temps
            }
            
            spec_data = {
                "version": "1.0",
                "job": {"job_id": "test_job"},
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 180.0,
                    "hold_time_s": 600
                },
                "data_requirements": {
                    "max_sample_period_s": 60,
                    "allowed_gaps_s": 120
                }
            }
            
            csv_path = self.create_test_csv(csv_data)
            spec_path = self.create_test_spec(spec_data)
            
            try:
                dataset_config = {
                    "id": "test_001",
                    "industry": "powder",
                    "csv_path": csv_path,
                    "spec_path": spec_path,
                    "expected_outcome": "PASS"
                }
                
                checker.root_path = Path("/")
                
                with patch('scripts.registry_sanity.validate_spec_schema'):
                    with patch('scripts.registry_sanity.models.ProcessSpec.model_validate'):
                        result = checker.validate_dataset_entry("test", dataset_config)
                
                assert result["metrics"]["likely_units"] == expected_units
                
            finally:
                Path(csv_path).unlink()
                Path(spec_path).unlink()
    
    def test_expected_outcome_validation(self):
        """Test validation of expected outcomes against data characteristics."""
        checker = RegistrySanityChecker()
        
        # Create clean data that should normalize successfully
        csv_data = {
            'timestamp': pd.date_range('2025-08-08T10:00:00Z', periods=50, freq='30S'),
            'temperature': [180.0] * 50  # Clean, stable temperature
        }
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_job"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600
            },
            "data_requirements": {
                "max_sample_period_s": 60,
                "allowed_gaps_s": 120
            }
        }
        
        csv_path = self.create_test_csv(csv_data)
        spec_path = self.create_test_spec(spec_data)
        
        try:
            # Test: Clean data with expected_outcome="ERROR" should warn
            dataset_config = {
                "id": "test_001",
                "industry": "powder",
                "csv_path": csv_path,
                "spec_path": spec_path,
                "expected_outcome": "ERROR"  # This doesn't match clean data
            }
            
            checker.root_path = Path("/")
            
            with patch('scripts.registry_sanity.validate_spec_schema'):
                with patch('scripts.registry_sanity.models.ProcessSpec.model_validate'):
                    with patch('scripts.registry_sanity.normalize_temperature_data') as mock_norm:
                        mock_norm.return_value = csv_data  # Successful normalization
                        result = checker.validate_dataset_entry("test", dataset_config)
            
            # Should warn about expected ERROR but clean data
            assert result["metrics"]["expected_outcome_reasonable"] is False
            
        finally:
            Path(csv_path).unlink()
            Path(spec_path).unlink()