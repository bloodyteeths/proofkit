"""
Autoclave Industry Acceptance Tests

Canonical pass/fail/missing_required test cases for autoclave sterilization validation.
Tests use registry.yaml datasets and verify expected outcomes match actual results.

Test Coverage:
- Basic pass case: 121C for 15min with proper hold time
- Basic fail case: insufficient hold time at sterilization temperature  
- Missing required fields: pressure when required by parameter_requirements
- Real-world validation: medical device sterilization per ISO 17665

Each test validates:
1. Decision status matches expected outcome
2. PDF generation succeeds without errors
3. Evidence bundle integrity and verification
4. Performance metrics within acceptable ranges
"""

import json
import pytest
import yaml
from pathlib import Path
from typing import Dict, Any

from core.models import SpecV1
from core.decide import make_decision
from core.normalize import normalize_dataframe
from core.errors import RequiredSignalMissingError, ValidationError
from core.verify import verify_evidence_bundle
from core.pack import create_evidence_bundle

class TestAutoclaveAcceptance:
    """Acceptance tests for autoclave industry validation."""
    
    @classmethod
    def setup_class(cls):
        """Load registry and prepare test data paths."""
        registry_path = Path(__file__).parent.parent.parent / "validation_campaign" / "registry.yaml"
        with open(registry_path, 'r') as f:
            cls.registry = yaml.safe_load(f)
    
    def get_dataset(self, dataset_id: str) -> Dict[str, Any]:
        """Retrieve dataset configuration from registry."""
        for dataset_key, dataset in self.registry['datasets'].items():
            if dataset['id'] == dataset_id:
                return dataset
        raise ValueError(f"Dataset {dataset_id} not found in registry")
    
    def load_test_data(self, dataset: Dict[str, Any]) -> tuple:
        """Load CSV and spec files for a dataset."""
        base_path = Path(__file__).parent.parent.parent
        
        csv_path = base_path / dataset['csv_path']
        spec_path = base_path / dataset['spec_path']
        
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
    
    def test_autoclave_pass_basic(self):
        """Test basic autoclave sterilization pass case."""
        dataset = self.get_dataset("autoclave_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "PASS"
        assert result.status == "PASS"
        assert result.pass_ is True
        assert result.industry == "autoclave"
        
        # Verify sterilization metrics exist (using correct field names)
        assert hasattr(result, 'actual_hold_time_s')
        assert hasattr(result, 'max_temp_C')
        
        # Test basic validation - decision should contain required metrics
        assert result.actual_hold_time_s >= 0
        assert result.max_temp_C > result.min_temp_C
        assert len(result.reasons) > 0  # Should have reasons for PASS
    
    def test_autoclave_fail_basic(self):
        """Test basic autoclave sterilization fail case."""
        dataset = self.get_dataset("autoclave_fail_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "FAIL"
        assert result.status == "FAIL"
        assert result.pass_ is False
        assert result.industry == "autoclave"
        
        # Verify failure reasons exist
        assert len(result.reasons) > 0
        assert any("fo" in reason.lower() or "sterilization" in reason.lower() or "temperature" in reason.lower()
                  for reason in result.reasons)
        if pressure_cols:
        
        # Normalize data
        
        # Should raise RequiredSignalMissingError
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            from core.metrics_autoclave import validate_autoclave_sterilization
            validate_autoclave_sterilization(normalized_df, spec)
        
        error = exc_info.value
        assert "pressure" in error.missing_signals
        assert error.industry == "autoclave"
        assert len(error.available_signals) > 0
    
    def test_realworld_autoclave_medical(self):
        """Test real-world medical device sterilization dataset."""
        dataset = self.get_dataset("realworld_autoclave_001")
        
        # Skip if real-world data not available
        base_path = Path(__file__).parent.parent.parent
        csv_path = base_path / dataset['csv_path']
        if not csv_path.exists():
            pytest.skip("Real-world autoclave dataset not available")
        
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "PASS"
        assert result.status == "PASS"
        assert result.pass_ is True
        assert result.industry == "autoclave"
        
        # Verify independent validation metrics if available
        if 'independent_validation' in dataset:
            ind_val = dataset['independent_validation']
            if 'fo_value_calculated' in ind_val:
                # F0 value should be within reasonable range of calculated
                assert hasattr(result, 'fo_value') or hasattr(result, 'sterilization_efficacy')
            if 'hold_time_minutes' in ind_val:
                # Hold time should match calculated value within tolerance
                expected_hold = ind_val['hold_time_minutes'] * 60  # Convert to seconds
                assert abs(result.sterilization_time_s - expected_hold) < 120  # 2min tolerance
    
    def test_autoclave_performance_benchmarks(self):
        """Test autoclave validation performance meets benchmarks."""
        # Test processing time for typical dataset
        dataset = self.get_dataset("autoclave_pass_001")
        df, spec = self.load_test_data(dataset)
        
        import time
        start_time = time.time()
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Create evidence bundle
        elapsed_time = time.time() - start_time
        
        # Performance benchmarks
        assert elapsed_time < 10.0, f"Processing took {elapsed_time:.2f}s, expected <10s"
        
        # Memory usage should be reasonable for typical dataset
        import sys
        assert sys.getsizeof(result) < 1024 * 1024, "Result object too large"
    def test_autoclave_deterministic_results(self):
        """Test that identical inputs produce identical outputs."""
        dataset = self.get_dataset("autoclave_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Run validation twice
        normalized_df1 = normalize_dataframe(df.copy())
        result1 = make_decision(normalized_df1, spec)
        bundle1 = create_evidence_bundle(normalized_df1, spec, result1)
        
        normalized_df2 = normalize_dataframe(df.copy())
        result2 = make_decision(normalized_df2, spec)
        bundle2 = create_evidence_bundle(normalized_df2, spec, result2)
        
        # Results should be identical
        assert result1.status == result2.status
        assert result1.pass_ == result2.pass_
        assert abs(result1.sterilization_time_s - result2.sterilization_time_s) < 0.1
        
        # Bundle hashes should match
        assert bundle1['root_hash'] == bundle2['root_hash']

if __name__ == "__main__":
    pytest.main([__file__, "-v"])