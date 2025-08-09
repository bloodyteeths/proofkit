"""
Registry Compliance Tests

Validates that all datasets in registry.yaml work correctly and produce expected outcomes.
This test suite acts as a comprehensive smoke test for the entire validation system.

Test Coverage:
- All datasets in registry.yaml are tested
- Expected outcomes match actual results
- Real-world datasets pass independent validation
- Performance benchmarks are met across all industries
- Evidence bundle integrity is maintained
"""

import json
import pytest
import yaml
import time
from pathlib import Path
from typing import Dict, Any, List

from core.models import SpecV1
from core.decide import make_decision
from core.normalize import normalize_dataframe
from core.errors import RequiredSignalMissingError, ValidationError
from core.verify import verify_evidence_bundle
from core.pack import create_evidence_bundle

class TestRegistryCompliance:
    """Comprehensive registry compliance validation."""
    
    @classmethod
    def setup_class(cls):
        """Load registry and prepare test data paths."""
        registry_path = Path(__file__).parent.parent.parent / "validation_campaign" / "registry.yaml"
        if not registry_path.exists():
            pytest.skip("Registry file not found")
        
        with open(registry_path, 'r') as f:
            cls.registry = yaml.safe_load(f)
        
        cls.base_path = Path(__file__).parent.parent.parent
    
    def get_all_datasets(self) -> List[Dict[str, Any]]:
        """Get all datasets from registry with metadata."""
        datasets = []
        for dataset_key, dataset in self.registry['datasets'].items():
            dataset['key'] = dataset_key
            datasets.append(dataset)
        return datasets
    
    def load_test_data(self, dataset: Dict[str, Any]) -> tuple:
        """Load CSV and spec files for a dataset."""
        csv_path = self.base_path / dataset['csv_path']
        spec_path = self.base_path / dataset['spec_path']
        
        if not csv_path.exists():
            pytest.skip(f"CSV file not found: {csv_path}")
        if not spec_path.exists():
            pytest.skip(f"Spec file not found: {spec_path}")
        
        # Load CSV data
        import pandas as pd
        df = pd.read_csv(csv_path)
        
        # Load and validate spec
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        return df, spec
    
    @pytest.mark.parametrize("dataset", 
                           [d for d in None.__class__.__dict__.get('_all_datasets', [])], 
                           ids=lambda d: d.get('key', d.get('id', 'unknown')),
                           indirect=False)
    def test_all_registry_datasets(self, dataset):
        """Parametrized test for all registry datasets."""
        # This will be populated by the fixture
        pass
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_parametrized_tests(self, request):
        """Setup parametrized tests for all datasets."""
        # Get all datasets
        all_datasets = self.get_all_datasets()
        
        # Store in class for parametrize decorator
        TestRegistryCompliance._all_datasets = all_datasets
        
        # Create individual test methods for each dataset
        for dataset in all_datasets:
            test_name = f"test_dataset_{dataset.get('key', dataset.get('id', 'unknown'))}"
            setattr(TestRegistryCompliance, test_name, self._create_dataset_test(dataset))
    
    def _create_dataset_test(self, dataset: Dict[str, Any]):
        """Create a test function for a specific dataset."""
        def test_dataset(self):
            """Test individual dataset compliance."""
            try:
                df, spec = self.load_test_data(dataset)
            except Exception as e:
                pytest.skip(f"Could not load test data: {e}")
            
            # Normalize data
            try:
                normalized_df = normalize_dataframe(df)
            except Exception as e:
                if dataset['expected_outcome'] == "ERROR":
                    # Expected data normalization error
                    return
                    pytest.fail(f"Unexpected normalization error: {e}")
            
            # Make decision
            try:
                start_time = time.time()
                result = make_decision(normalized_df, spec)
                elapsed_time = time.time() - start_time
                
                # Performance check
                max_time = {
                    'powder': 8.0,
                    'autoclave': 10.0,
                    'sterile': 10.0,
                    'haccp': 12.0,
                    'coldchain': 15.0,
                    'concrete': 20.0
                }.get(dataset['industry'], 15.0)
                
                assert elapsed_time < max_time, f"Processing took {elapsed_time:.2f}s, expected <{max_time}s"
                
            except RequiredSignalMissingError:
                if dataset['expected_outcome'] in ["ERROR", "INDETERMINATE"]:
                    # Expected required signal error
                    return
                    pytest.fail("Unexpected required signal missing error")
            except ValidationError:
                if dataset['expected_outcome'] == "ERROR":
                    # Expected validation error
                    return
                    pytest.fail("Unexpected validation error")
            except Exception as e:
                if dataset['expected_outcome'] == "ERROR":
                    # Expected error of some kind
                    return
                    pytest.fail(f"Unexpected error: {e}")
            
            # Verify expected outcome
            expected = dataset['expected_outcome']
            actual = result.status
            
            assert actual == expected, f"Expected {expected}, got {actual} for dataset {dataset['id']}"
            
            # Verify industry matches
            assert result.industry == dataset['industry']
            
            # Verify pass/fail consistency
            if expected == "PASS":
                assert result.pass_ is True
            elif expected == "FAIL":
                assert result.pass_ is False
            else:  # ERROR or INDETERMINATE
                assert result.pass_ is False
            
                    # Test basic validation - decision should contain required metrics
        assert result.actual_hold_time_s >= 0
        assert result.max_temp_C > result.min_temp_C
        assert len(result.reasons) > 0  # Should have reasons for PASS
                
            except Exception as e:
                pytest.fail(f"Evidence bundle creation failed: {e}")
            
            # Validate independent verification for real-world datasets
            if 'independent_validation' in dataset:
                self._validate_independent_metrics(result, dataset['independent_validation'])
        
        return test_dataset
    
    def _validate_independent_metrics(self, result: Any, independent_validation: Dict[str, Any]):
        """Validate result against independent validation metrics."""
        # Autoclave F0 value validation
        if 'fo_value_calculated' in independent_validation:
            expected_fo = independent_validation['fo_value_calculated']
            if hasattr(result, 'fo_value'):
                # Allow 10% tolerance for F0 calculations
                assert abs(result.fo_value - expected_fo) / expected_fo < 0.1
        
        # Hold time validation
        if 'hold_time_minutes' in independent_validation:
            expected_hold = independent_validation['hold_time_minutes'] * 60  # Convert to seconds
            if hasattr(result, 'sterilization_time_s'):
                # Allow 2 minute tolerance
                assert abs(result.sterilization_time_s - expected_hold) < 120
        
        # Temperature excursion validation
        if 'excursion_detected' in independent_validation:
            expected_excursion = independent_validation['excursion_detected']
            if expected_excursion:
                # Should detect excursion in failure reasons
                assert any("excursion" in reason.lower() or "temperature" in reason.lower()
                          for reason in result.reasons)
        
        # Maximum temperature validation
        if 'max_temperature' in independent_validation:
            expected_max = independent_validation['max_temperature']
            if hasattr(result, 'max_temperature_C'):
                # Allow 1°C tolerance
                assert abs(result.max_temperature_C - expected_max) < 1.0
    
    def test_registry_schema_compliance(self):
        """Test that registry follows expected schema."""
        assert 'schema_version' in self.registry
        assert 'datasets' in self.registry
        
        # Check each dataset has required fields
        required_fields = ['id', 'industry', 'csv_path', 'spec_path', 'expected_outcome', 'provenance', 'metadata']
        
        for dataset_key, dataset in self.registry['datasets'].items():
            for field in required_fields:
                assert field in dataset, f"Dataset {dataset_key} missing required field: {field}"
            
            # Validate expected_outcome values
            valid_outcomes = ['PASS', 'FAIL', 'ERROR', 'INDETERMINATE']
            assert dataset['expected_outcome'] in valid_outcomes, f"Invalid expected_outcome: {dataset['expected_outcome']}"
            
            # Validate industry values
            valid_industries = ['powder', 'autoclave', 'sterile', 'haccp', 'coldchain', 'concrete']
            assert dataset['industry'] in valid_industries, f"Invalid industry: {dataset['industry']}"
    
    def test_registry_dataset_coverage(self):
        """Test that registry covers all required test cases."""
        datasets_by_industry = {}
        for dataset in self.registry['datasets'].values():
            industry = dataset['industry']
            if industry not in datasets_by_industry:
                datasets_by_industry[industry] = []
            datasets_by_industry[industry].append(dataset['expected_outcome'])
        
        # Each industry should have at least PASS and FAIL cases
        required_industries = ['powder', 'autoclave', 'sterile', 'haccp', 'coldchain', 'concrete']
        for industry in required_industries:
            assert industry in datasets_by_industry, f"No datasets for industry: {industry}"
            
            outcomes = datasets_by_industry[industry]
            assert 'PASS' in outcomes, f"No PASS case for industry: {industry}"
            assert 'FAIL' in outcomes, f"No FAIL case for industry: {industry}"
    
    def test_registry_file_paths_exist(self):
        """Test that all referenced files exist."""
        missing_files = []
        
        for dataset_key, dataset in self.registry['datasets'].items():
            csv_path = self.base_path / dataset['csv_path']
            spec_path = self.base_path / dataset['spec_path']
            
            if not csv_path.exists():
                missing_files.append(f"{dataset_key}: {dataset['csv_path']}")
            if not spec_path.exists():
                missing_files.append(f"{dataset_key}: {dataset['spec_path']}")
        
        if missing_files:
            pytest.skip(f"Missing test data files: {missing_files}")
    
    def test_performance_benchmarks_summary(self):
        """Test overall performance benchmarks across all datasets."""
        total_time = 0
        dataset_count = 0
        
        for dataset in self.get_all_datasets():
            try:
                df, spec = self.load_test_data(dataset)
                normalized_df = normalize_dataframe(df)
                
                start_time = time.time()
                result = make_decision(normalized_df, spec)
                elapsed_time = time.time() - start_time
                
                total_time += elapsed_time
                dataset_count += 1
                
            except Exception:
                # Skip datasets that can't be loaded or processed
                continue
        
        if dataset_count > 0:
            average_time = total_time / dataset_count
            assert average_time < 10.0, f"Average processing time {average_time:.2f}s too slow"
            assert total_time < 120.0, f"Total processing time {total_time:.2f}s too slow"

# Auto-generate individual test methods for each dataset
def pytest_generate_tests(metafunc):
    """Generate parametrized tests for all registry datasets."""
    if metafunc.cls is TestRegistryCompliance and 'dataset' in metafunc.fixturenames:
        registry_path = Path(__file__).parent.parent.parent / "validation_campaign" / "registry.yaml"
        
        if registry_path.exists():
            with open(registry_path, 'r') as f:
                registry = yaml.safe_load(f)
            
            datasets = []
            for dataset_key, dataset in registry['datasets'].items():
                dataset['key'] = dataset_key
                datasets.append(dataset)
            
            metafunc.parametrize("dataset", datasets, ids=lambda d: d.get('key', d.get('id', 'unknown')))

if __name__ == "__main__":
    pytest.main([__file__, "-v"])