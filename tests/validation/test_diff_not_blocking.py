"""
Test that shadow comparison differences don't block the main decision flow.

Shadow comparisons should record differences but always return a result,
never blocking or causing failures in the main pipeline.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from core.shadow_compare import ShadowComparator, ShadowResult, ShadowStatus, create_indeterminate_result
from core.models import SpecV1, DecisionResult
from core.decide import make_decision


class TestShadowComparisonNonBlocking:
    """Test that shadow comparisons never block the main decision flow."""
    
    def create_test_data(self):
        """Create test data for shadow comparison tests."""
        timestamps = pd.date_range('2023-01-01 00:00:00', periods=100, freq='30s', tz='UTC')
        temperatures = np.array([20] * 20 + [180] * 60 + [20] * 20)  # Ramp up, hold, ramp down
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature_C': temperatures
        })
        
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test_shadow"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 1800,
                "sensor_uncertainty_C": 2.0
            },
            "industry": "powder",
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        }
        spec = SpecV1(**spec_data)
        
        return df, spec
    
    def test_shadow_comparison_tolerance_violation_creates_indeterminate(self):
        """Test that tolerance violations create INDETERMINATE results, not failures."""
        df, spec = self.create_test_data()
        comparator = ShadowComparator()
        
        # Mock independent calculator to return different results
        with patch.object(comparator, '_run_independent_calculator') as mock_independent:
            mock_independent.return_value = {
                'industry': 'powder',
                'hold_time_s': 999.0,  # Very different from what engine would calculate
                'ramp_rate_C_per_min': 999.0,  # Very different
                'time_to_threshold_s': 999.0,  # Very different
                'threshold_temp_C': 182.0,
                'pass': True
            }
            
            # Run shadow comparison
            result = comparator.run_shadow_comparison(df, spec)
            
            # Should detect tolerance violation but not block
            assert result.status == ShadowStatus.TOLERANCE_VIOLATION
            assert result.engine_result is not None  # Engine result should still be available
            assert result.reason is not None
            assert "DIFF_EXCEEDS_TOL" in result.reason
    
    def test_create_indeterminate_result_preserves_original_data(self):
        """Test that creating INDETERMINATE result preserves original decision data."""
        df, spec = self.create_test_data()
        
        # Create original engine result
        original_result = make_decision(df, spec)
        
        # Create a mock shadow result with tolerance violation
        shadow_result = ShadowResult(
            status=ShadowStatus.TOLERANCE_VIOLATION,
            engine_result=original_result,
            reason="Test tolerance violation"
        )
        
        # Create indeterminate result
        indeterminate_result = create_indeterminate_result(shadow_result, original_result)
        
        # Should preserve all original data but change status
        assert indeterminate_result.status == "INDETERMINATE"
        assert indeterminate_result.pass_ is False  # INDETERMINATE is always False
        assert indeterminate_result.job_id == original_result.job_id
        assert indeterminate_result.target_temp_C == original_result.target_temp_C
        assert indeterminate_result.conservative_threshold_C == original_result.conservative_threshold_C
        assert indeterminate_result.actual_hold_time_s == original_result.actual_hold_time_s
        assert indeterminate_result.required_hold_time_s == original_result.required_hold_time_s
        assert indeterminate_result.max_temp_C == original_result.max_temp_C
        assert indeterminate_result.min_temp_C == original_result.min_temp_C
        
        # Should have shadow comparison reason
        assert len(indeterminate_result.reasons) > 0
        assert any("tolerance violation" in reason.lower() for reason in indeterminate_result.reasons)
    
    def test_shadow_comparison_independent_error_still_returns_engine_result(self):
        """Test that independent calculator errors don't block engine results."""
        df, spec = self.create_test_data()
        comparator = ShadowComparator()
        
        # Mock independent calculator to raise an exception
        with patch.object(comparator, '_run_independent_calculator') as mock_independent:
            mock_independent.side_effect = RuntimeError("Independent calculator failed")
            
            # Run shadow comparison
            result = comparator.run_shadow_comparison(df, spec)
            
            # Should return independent error status but still have engine result
            assert result.status == ShadowStatus.INDEPENDENT_ERROR
            assert result.engine_result is not None
            assert result.engine_result.status in ["PASS", "FAIL"]  # Valid engine result
            assert "Independent calculator error" in result.reason
    
    def test_shadow_comparison_engine_error_handled_gracefully(self):
        """Test that engine errors are handled gracefully in shadow comparison."""
        df, spec = self.create_test_data()
        comparator = ShadowComparator()
        
        # Mock make_decision to raise an exception
        with patch('core.shadow_compare.make_decision') as mock_decision:
            mock_decision.side_effect = RuntimeError("Engine failed")
            
            # Run shadow comparison
            result = comparator.run_shadow_comparison(df, spec)
            
            # Should return engine error status
            assert result.status == ShadowStatus.ENGINE_ERROR
            assert "Engine error" in result.reason
    
    def test_shadow_comparison_unsupported_industry_returns_engine_result(self):
        """Test that unsupported industries still return engine results."""
        df, spec = self.create_test_data()
        
        # Modify spec to use unsupported industry
        spec.industry = "unsupported_industry"
        
        comparator = ShadowComparator()
        result = comparator.run_shadow_comparison(df, spec)
        
        # Should return not supported status but still have engine result
        assert result.status == ShadowStatus.NOT_SUPPORTED
        assert result.engine_result is not None
        assert result.engine_result.status in ["PASS", "FAIL"]
        assert "Independent calculator not available" in result.reason
    
    def test_shadow_comparison_agreement_preserves_engine_result(self):
        """Test that when shadow and engine agree, engine result is preserved."""
        df, spec = self.create_test_data()
        comparator = ShadowComparator()
        
        # Get what the engine would actually calculate
        engine_result = make_decision(df, spec)
        
        # Mock independent calculator to return similar results (within tolerance)
        with patch.object(comparator, '_run_independent_calculator') as mock_independent:
            mock_independent.return_value = {
                'industry': 'powder',
                'hold_time_s': engine_result.actual_hold_time_s,  # Same as engine
                'ramp_rate_C_per_min': getattr(engine_result, 'ramp_rate_C_per_min', 10.0),
                'time_to_threshold_s': getattr(engine_result, 'time_to_threshold_s', 600.0),
                'threshold_temp_C': engine_result.conservative_threshold_C,
                'pass': engine_result.pass_
            }
            
            # Run shadow comparison
            result = comparator.run_shadow_comparison(df, spec)
            
            # Should show agreement and preserve engine result unchanged
            assert result.status == ShadowStatus.AGREEMENT
            assert result.engine_result.status == engine_result.status
            assert result.engine_result.pass_ == engine_result.pass_
    
    def test_make_decision_with_shadow_comparison_integration(self):
        """Test that make_decision handles shadow comparison results properly."""
        df, spec = self.create_test_data()
        
        # Test that decision making works even with shadow comparison issues
        # This should never raise an exception or block
        result = make_decision(df, spec)
        
        # Should always get a valid result
        assert result.status in ["PASS", "FAIL", "INDETERMINATE"]
        assert hasattr(result, 'pass_')
        assert hasattr(result, 'job_id')
        assert hasattr(result, 'actual_hold_time_s')
    
    def test_shadow_result_serialization(self):
        """Test that shadow results can be serialized to JSON without errors."""
        df, spec = self.create_test_data()
        comparator = ShadowComparator()
        
        # Create a shadow result with tolerance violation
        with patch.object(comparator, '_run_independent_calculator') as mock_independent:
            mock_independent.return_value = {
                'industry': 'powder',
                'hold_time_s': 999.0,
                'pass': True
            }
            
            result = comparator.run_shadow_comparison(df, spec)
            
            # Should be able to serialize to dict for JSON
            result_dict = result.to_dict()
            assert isinstance(result_dict, dict)
            assert 'status' in result_dict
            assert 'reason' in result_dict
            assert 'engine_result' in result_dict
            assert 'differences' in result_dict


class TestShadowComparisonTolerances:
    """Test industry-specific tolerances in shadow comparison."""
    
    def test_powder_industry_tolerances(self):
        """Test that powder industry uses correct tolerances."""
        comparator = ShadowComparator()
        tolerances = comparator.INDUSTRY_TOLERANCES['powder']
        
        # Verify expected tolerances exist
        assert 'hold_time_s' in tolerances
        assert 'ramp_rate_C_per_min' in tolerances
        assert 'time_to_threshold_s' in tolerances
        
        # Should be reasonable values
        assert tolerances['hold_time_s'] == 1.0  # ±1s
        assert tolerances['time_to_threshold_s'] == 1.0  # ±1s
    
    def test_autoclave_industry_tolerances(self):
        """Test that autoclave industry uses correct tolerances."""
        comparator = ShadowComparator()
        tolerances = comparator.INDUSTRY_TOLERANCES['autoclave']
        
        # Verify expected tolerances exist
        assert 'fo_value' in tolerances
        assert 'hold_time_s' in tolerances
        
        # Should be reasonable values for autoclave
        assert tolerances['fo_value'] == 0.1  # ±0.1 for F0
        assert tolerances['hold_time_s'] == 1.0  # ±1s
    
    @pytest.mark.parametrize("industry,expected_keys", [
        ('haccp', ['phase1_time_s', 'phase2_time_s']),
        ('concrete', ['percent_in_spec_24h', 'temperature_time_hours']),
        ('coldchain', ['overall_compliance_pct', 'excursion_duration_s']),
    ])
    def test_industry_specific_tolerances_exist(self, industry, expected_keys):
        """Test that each industry has appropriate tolerance definitions."""
        comparator = ShadowComparator()
        
        assert industry in comparator.INDUSTRY_TOLERANCES
        tolerances = comparator.INDUSTRY_TOLERANCES[industry]
        
        for key in expected_keys:
            assert key in tolerances, f"Missing tolerance key {key} for {industry}"
            assert isinstance(tolerances[key], (int, float))
            assert tolerances[key] > 0, f"Tolerance {key} should be positive"