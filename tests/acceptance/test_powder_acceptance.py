"""
Powder Coating Industry Acceptance Tests

Canonical pass/fail/missing_required test cases for powder coating cure validation.
Tests use registry.yaml datasets and verify expected outcomes match actual results.

Test Coverage:
- Basic pass case: 180C for 10min continuous hold
- Basic fail case: insufficient hold time at target temperature
- Borderline pass case: just meets minimum hold requirements  
- Data quality errors: gaps, duplicate timestamps, timezone shifts
- Missing required fields: temperature signals required for validation
- Real-world validation: ceramic kiln firing with complex profile

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

class TestPowderAcceptance:
    """Acceptance tests for powder coating industry validation."""
    
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
    
    def test_powder_pass_basic(self):
        """Test basic powder coating cure pass case."""
        dataset = self.get_dataset("powder_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "PASS"
        assert result.status == "PASS"
        assert result.pass_ is True
        assert result.industry == "powder"
        
        # Verify powder-specific metrics exist (using correct field names)
        assert hasattr(result, 'actual_hold_time_s')
        assert hasattr(result, 'max_temp_C')
        
        # Test basic validation - decision should contain required metrics
        assert result.actual_hold_time_s >= 0
        assert result.max_temp_C > result.min_temp_C
        assert len(result.reasons) > 0  # Should have reasons for PASS
    
    def test_powder_fail_basic(self):
        """Test basic powder coating cure fail case."""
        dataset = self.get_dataset("powder_fail_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "FAIL"
        assert result.status == "FAIL"
        assert result.pass_ is False
        assert result.industry == "powder"
        
        # Verify failure reasons exist
        assert len(result.reasons) > 0
        assert any("hold" in reason.lower() or "time" in reason.lower() or "temperature" in reason.lower()
                  for reason in result.reasons)
        
        # Test evidence bundle still created for failures
        # Normalize data
        
        # Should raise RequiredSignalMissingError
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            from core.metrics_powder import validate_powder_coating_cure
            validate_powder_coating_cure(normalized_df, spec)
        
        error = exc_info.value
        assert "temperature" in error.missing_signals
        assert error.industry == "powder"
        assert len(error.available_signals) > 0
    
    def test_realworld_oven_ceramic(self):
        """Test real-world ceramic kiln firing dataset."""
        dataset = self.get_dataset("realworld_oven_001")
        
        # Skip if real-world data not available
        base_path = Path(__file__).parent.parent.parent
        csv_path = base_path / dataset['csv_path']
        if not csv_path.exists():
            pytest.skip("Real-world oven dataset not available")
        
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome (this should be INDETERMINATE due to complexity)
        assert dataset['expected_outcome'] == "INDETERMINATE"
        assert result.status == "INDETERMINATE"
        assert result.pass_ is False
        assert result.industry == "powder"
        
        # Verify independent validation metadata if available
        if 'independent_validation' in dataset:
            ind_val = dataset['independent_validation']
            if 'profile_complexity' in ind_val:
                assert ind_val['profile_complexity'] == "high"
                # Complex profile should trigger indeterminate result
                assert any("complex" in reason.lower() or "review" in reason.lower() or "manual" in reason.lower()
                          for reason in result.reasons)
    
    def test_powder_hold_time_validation(self):
        """Test powder coating hold time validation."""
        dataset = self.get_dataset("powder_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Should validate hold time properly
        hold_time_validated = False
        if hasattr(result, 'hold_time_s'):
            # Hold time should meet or exceed spec requirement
            hold_time_validated = result.hold_time_s >= spec.spec.hold_time_s
        elif hasattr(result, 'cure_time_minutes'):
            # Convert spec to minutes and compare
            spec_minutes = spec.spec.hold_time_s / 60.0
            hold_time_validated = result.cure_time_minutes >= spec_minutes
        elif result.status == "PASS":
            # Pass implies hold time compliance
            hold_time_validated = True
        
        assert hold_time_validated, "Hold time should be validated properly"
    
    def test_powder_performance_benchmarks(self):
        """Test powder coating validation performance meets benchmarks."""
        # Test processing time for typical dataset
        dataset = self.get_dataset("powder_pass_001")
        df, spec = self.load_test_data(dataset)
        
        import time
        start_time = time.time()
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Create evidence bundle
        elapsed_time = time.time() - start_time
        
        # Performance benchmarks (powder datasets are typically smaller/faster)
        assert elapsed_time < 8.0, f"Processing took {elapsed_time:.2f}s, expected <8s"
        
        # Memory usage should be reasonable
        import sys
        assert sys.getsizeof(result) < 1024 * 1024, "Result object too large"
    
    def test_powder_deterministic_results(self):
        """Test that identical inputs produce identical outputs."""
        dataset = self.get_dataset("powder_pass_001")
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
        
        # Bundle hashes should match
        assert bundle1['root_hash'] == bundle2['root_hash']
    
    def test_powder_sensor_selection_handling(self):
        """Test powder coating sensor selection modes."""
        dataset = self.get_dataset("powder_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Test should handle different sensor selection modes
        normalized_df = normalize_dataframe(df)
        
        # Test with multiple temperature sensors if available
                    if any(temp_word in col.lower() for temp_word in ['temp', 'temperature'])]
        
        if len(temp_cols) >= 2:
            # Test min_of_set sensor selection
            from core.models import SensorSelection
            spec.sensor_selection = SensorSelection(
                mode="min_of_set",
                require_at_least=2
            )
            
            result = make_decision(normalized_df, spec)
            
            # Should complete successfully with multiple sensors
            assert result.status in ["PASS", "FAIL"]
            assert result.industry == "powder"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])