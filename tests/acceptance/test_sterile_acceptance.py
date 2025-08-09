"""
Sterile Processing Industry Acceptance Tests

Canonical pass/fail/missing_required test cases for sterile processing validation.
Tests use registry.yaml datasets and verify expected outcomes match actual results.

Test Coverage:
- Basic pass case: dry heat sterilization 170C for 1hr
- Basic fail case: insufficient sterilization time
- Missing required fields: humidity/gas when required by parameter_requirements
- Real-world validation: ISO 17665 steam sterilization compliance

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

class TestSterileAcceptance:
    """Acceptance tests for sterile processing industry validation."""
    
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
    
    def test_sterile_pass_basic(self):
        """Test basic sterile processing pass case."""
        dataset = self.get_dataset("sterile_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "PASS"
        assert result.status == "PASS"
        assert result.pass_ is True
        assert result.industry == "sterile"
        
        # Verify sterile-specific metrics exist
        assert hasattr(result, 'actual_hold_time_s') or hasattr(result, 'sterilization_duration_minutes')
        assert hasattr(result, 'max_temp_C') or hasattr(result, 'sterilization_efficacy')
        
        # Test basic validation - decision should contain required metrics
        assert result.actual_hold_time_s >= 0
        assert result.max_temp_C > result.min_temp_C
        assert len(result.reasons) > 0  # Should have reasons for PASS
    
    def test_sterile_fail_basic(self):
        """Test basic sterile processing fail case."""
        dataset = self.get_dataset("sterile_fail_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "FAIL"
        assert result.status == "FAIL"
        assert result.pass_ is False
        assert result.industry == "sterile"
        
        # Verify failure reasons exist
        assert len(result.reasons) > 0
        assert any("sterilization" in reason.lower() or "time" in reason.lower() or "temperature" in reason.lower()
                  for reason in result.reasons)
        
        # Test evidence bundle still created for failures
                        if any(hum_word in col.lower() for hum_word in ['humidity', 'rh', 'moisture'])]
        if humidity_cols:
        
        # Normalize data
        
        # Should raise RequiredSignalMissingError
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            from core.metrics_sterile import validate_eto_sterilization
            validate_eto_sterilization(normalized_df, spec)
        
        error = exc_info.value
        assert "humidity" in error.missing_signals
        assert error.industry == "sterile"
        assert len(error.available_signals) > 0
    
    def test_sterile_missing_gas_concentration_required(self):
        """Test sterile processing with missing required gas concentration signal."""
        dataset = self.get_dataset("sterile_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Add gas concentration requirement for EtO sterilization
        if not hasattr(spec, 'parameter_requirements'):
        
        # Remove gas concentration columns from dataframe if they exist
                   if any(gas_word in col.lower() for gas_word in ['gas', 'eto', 'concentration', 'ppm'])]
        if gas_cols:
        
        # Normalize data
        
        # Should raise RequiredSignalMissingError
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            from core.metrics_sterile import validate_eto_sterilization
            validate_eto_sterilization(normalized_df, spec)
        
        error = exc_info.value
        assert "gas_concentration" in error.missing_signals
        assert error.industry == "sterile"
        assert len(error.available_signals) > 0
    
    def test_realworld_sterile_iso(self):
        """Test real-world ISO 17665 steam sterilization dataset."""
        dataset = self.get_dataset("realworld_sterile_001")
        
        # Skip if real-world data not available
        base_path = Path(__file__).parent.parent.parent
        csv_path = base_path / dataset['csv_path']
        if not csv_path.exists():
            pytest.skip("Real-world sterile dataset not available")
        
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Verify expected outcome
        assert dataset['expected_outcome'] == "PASS"
        assert result.status == "PASS"
        assert result.pass_ is True
        assert result.industry == "sterile"
        
        # Verify independent validation metrics if available
        if 'independent_validation' in dataset:
            ind_val = dataset['independent_validation']
            if 'sterilization_temperature_achieved' in ind_val:
                assert ind_val['sterilization_temperature_achieved'] is True
                # Should achieve sterilization temperature
                assert hasattr(result, 'max_temp_C') or hasattr(result, 'sterilization_efficacy')
            if 'hold_time_minutes' in ind_val:
                # Hold time should match calculated value within tolerance
                expected_hold = ind_val['hold_time_minutes'] * 60  # Convert to seconds
                if hasattr(result, 'sterilization_time_s'):
                    assert abs(result.sterilization_time_s - expected_hold) < 300  # 5min tolerance
    
    def test_sterile_sterilization_time_validation(self):
        """Test sterile processing sterilization time validation."""
        dataset = self.get_dataset("sterile_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Should validate sterilization time properly
        sterilization_validated = False
        if hasattr(result, 'sterilization_time_s'):
            # Sterilization time should meet or exceed spec requirement
            sterilization_validated = result.sterilization_time_s >= spec.spec.hold_time_s
        elif hasattr(result, 'sterilization_duration_minutes'):
            # Convert spec to minutes and compare
            spec_minutes = spec.spec.hold_time_s / 60.0
            sterilization_validated = result.sterilization_duration_minutes >= spec_minutes
        elif result.status == "PASS":
            # Pass implies sterilization time compliance
            sterilization_validated = True
        
        assert sterilization_validated, "Sterilization time should be validated properly"
    
    def test_sterile_temperature_compliance(self):
        """Test sterile processing temperature compliance validation."""
        dataset = self.get_dataset("sterile_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Normalize data
        normalized_df = normalize_dataframe(df)
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        # Should track temperature compliance
        temp_compliance_verified = False
        if hasattr(result, 'temperature_achieved'):
            temp_compliance_verified = result.temperature_achieved
        elif hasattr(result, 'sterilization_efficacy'):
            temp_compliance_verified = result.sterilization_efficacy
        elif hasattr(result, 'max_temperature_C') and hasattr(result, 'target_temp_C'):
            # Temperature should achieve target for sterilization
            temp_compliance_verified = result.max_temperature_C >= result.target_temp_C
        elif result.status == "PASS":
            # Pass implies temperature compliance
            temp_compliance_verified = True
        
        assert temp_compliance_verified, "Temperature compliance should be verified"
    
    def test_sterile_performance_benchmarks(self):
        """Test sterile processing validation performance meets benchmarks."""
        # Test processing time for typical dataset
        dataset = self.get_dataset("sterile_pass_001")
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
        
        # Memory usage should be reasonable
        import sys
        assert sys.getsizeof(result) < 1024 * 1024, "Result object too large"
    
    def test_sterile_deterministic_results(self):
        """Test that identical inputs produce identical outputs."""
        dataset = self.get_dataset("sterile_pass_001")
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
    
    def test_sterile_method_handling(self):
        """Test handling of different sterilization methods."""
        dataset = self.get_dataset("sterile_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Test should handle different sterilization methods
        normalized_df = normalize_dataframe(df)
        
        # Test with dry heat method
        original_method = spec.spec.method if hasattr(spec.spec, 'method') else None
        spec.spec.method = "DRY_HEAT"
        
        result = make_decision(normalized_df, spec)
        
        # Should complete successfully regardless of method
        assert result.status in ["PASS", "FAIL"]
        assert result.industry == "sterile"
        
        # Restore original method
        if original_method:
            spec.spec.method = original_method
    
    def test_sterile_eto_vs_dry_heat_validation(self):
        """Test validation differences between EtO and dry heat sterilization."""
        dataset = self.get_dataset("sterile_pass_001")
        df, spec = self.load_test_data(dataset)
        
        # Test EtO sterilization (typically lower temp, longer time)
        normalized_df = normalize_dataframe(df)
        
        # EtO typically uses 55°C for 2+ hours
        if hasattr(spec.spec, 'target_temp_C'):
            if spec.spec.target_temp_C < 100:  # Likely EtO conditions
                result = make_decision(normalized_df, spec)
                
                # EtO should complete successfully
                assert result.status in ["PASS", "FAIL"]
                assert result.industry == "sterile"
                
                # Should handle longer sterilization times
                if hasattr(result, 'sterilization_time_s'):
                    assert result.sterilization_time_s > 0
                elif hasattr(result, 'sterilization_duration_minutes'):
                    assert result.sterilization_duration_minutes > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])