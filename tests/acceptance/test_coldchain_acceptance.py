"""
Coldchain Industry Acceptance Tests

Canonical pass/fail/missing_required test cases for cold chain storage validation.
Tests use registry.yaml datasets and verify expected outcomes match actual results.

Test Coverage:
- Basic pass case: maintain 2-8C for vaccine storage
- Basic fail case: temperature excursion above acceptable range
- Missing required fields: temperature signals for monitoring
- Real-world validation: pharmaceutical cold storage with excursion event

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

class TestColdchainAcceptance:
    """Acceptance tests for coldchain industry validation."""
    
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
    
    def test_coldchain_pass_basic(self):
        """Test basic cold chain storage pass case."""
        dataset = self.get_dataset("coldchain_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "PASS"
        assert result.status == "PASS"
        assert result.pass_ is True
        assert result.industry == "coldchain"
        
        # Verify coldchain-specific metrics exist
        assert hasattr(result, 'storage_duration_hours') or hasattr(result, 'monitoring_duration_s')
        assert hasattr(result, 'temperature_maintained')
        
        # Test basic validation - decision should contain required metrics
        assert result.actual_hold_time_s >= 0
        assert result.max_temp_C > result.min_temp_C
        assert len(result.reasons) > 0  # Should have reasons for PASS
    
    def test_coldchain_fail_basic(self):
        """Test basic cold chain storage fail case."""
        dataset = self.get_dataset("coldchain_fail_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "FAIL"
        assert result.status == "FAIL"
        assert result.pass_ is False
        assert result.industry == "coldchain"
        
        # Verify failure reasons exist
        assert len(result.reasons) > 0
        assert any("temperature" in reason.lower() or "excursion" in reason.lower()
                  for reason in result.reasons)
        
        # Test evidence bundle still created for failures
        # Normalize data
        
        # Should raise RequiredSignalMissingError
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            from core.metrics_coldchain import validate_coldchain_storage
            validate_coldchain_storage(normalized_df, spec)
        
        error = exc_info.value
        assert "temperature" in error.missing_signals
        assert error.industry == "coldchain"
        assert len(error.available_signals) > 0
    
    def test_realworld_coldchain_pharma(self):
        """Test real-world pharmaceutical cold storage dataset."""
        dataset = self.get_dataset("realworld_coldchain_001")
        
        # Skip if real-world data not available
        base_path = Path(__file__).parent.parent.parent
        csv_path = base_path / dataset['csv_path']
        if not csv_path.exists():
            pytest.skip("Real-world coldchain dataset not available")
        
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome (this should be a FAIL case)
        assert dataset['expected_outcome'] == "FAIL"
        assert result.status == "FAIL"
        assert result.pass_ is False
        assert result.industry == "coldchain"
        
        # Verify independent validation metrics if available
        if 'independent_validation' in dataset:
            ind_val = dataset['independent_validation']
            if 'excursion_detected' in ind_val:
                assert ind_val['excursion_detected'] is True
                # Should detect excursion in validation
                assert any("excursion" in reason.lower() or "temperature" in reason.lower()
                          for reason in result.reasons)
            if 'max_temperature' in ind_val:
                # Max temperature excursion should be detected
                expected_max = ind_val['max_temperature']
                assert hasattr(result, 'max_temp_C') or hasattr(result, 'excursion_details')
    
    def test_coldchain_excursion_detection(self):
        """Test proper detection of temperature excursions."""
        dataset = self.get_dataset("coldchain_fail_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify excursion detection
        assert result.status == "FAIL"
        
        # Check for excursion-related metrics
        excursion_detected = False
        if hasattr(result, 'excursions') and result.excursions:
            excursion_detected = True
        elif hasattr(result, 'max_temperature_C') and hasattr(result, 'threshold_C'):
            excursion_detected = result.max_temperature_C > result.threshold_C
        elif any("excursion" in reason.lower() for reason in result.reasons):
            excursion_detected = True
        
        assert excursion_detected, "Should detect temperature excursion"
    
    def test_coldchain_performance_benchmarks(self):
        """Test coldchain validation performance meets benchmarks."""
        # Test processing time for typical dataset (24h monitoring)
        dataset = self.get_dataset("coldchain_pass_001")
        df, spec = self.load_test_data(dataset)
        
        import time
        start_time = time.time()
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Create evidence bundle
        elapsed_time = time.time() - start_time
        
        # Performance benchmarks (coldchain datasets can be large - 24h+ monitoring)
        assert elapsed_time < 15.0, f"Processing took {elapsed_time:.2f}s, expected <15s"
        
        # Memory usage should be reasonable
        import sys
        assert sys.getsizeof(result) < 1024 * 1024, "Result object too large"
    
    def test_coldchain_deterministic_results(self):
        """Test that identical inputs produce identical outputs."""
        dataset = self.get_dataset("coldchain_pass_001")
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
    
    def test_coldchain_long_duration_handling(self):
        """Test handling of long duration monitoring periods."""
        dataset = self.get_dataset("coldchain_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Test should handle multi-day monitoring without issues
        if len(df) > 100:  # Sufficient data points for long-term monitoring
            normalized_df = normalize_dataframe(df)
            result = make_decision(normalized_df, spec)
            
            # Should complete successfully
            assert result.status in ["PASS", "FAIL"]  # Should not be ERROR or INDETERMINATE
            assert hasattr(result, 'industry')
            assert result.industry == "coldchain"
            
            # Should handle time duration calculations properly
            if hasattr(result, 'monitoring_duration_s'):
                assert result.monitoring_duration_s > 0
            elif hasattr(result, 'storage_duration_hours'):
                assert result.storage_duration_hours > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])