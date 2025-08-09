"""
Tests for Shadow Comparison Engine

Validates that the shadow runs system correctly compares main engine
against independent calculators with proper tolerance handling.
"""

import pytest
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from core.shadow_compare import ShadowComparator, ShadowStatus, ShadowResult, create_indeterminate_result
from core.models import SpecV1, DecisionResult
from core.decide import make_decision


class TestShadowComparator:
    """Test cases for ShadowComparator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.comparator = ShadowComparator()
        
        # Create sample data
        timestamps = pd.date_range('2024-01-01 12:00:00', periods=100, freq='30S')
        temperatures = np.concatenate([
            np.linspace(20, 180, 30),   # Ramp up
            np.full(40, 180),           # Hold at target
            np.linspace(180, 25, 30)    # Cool down
        ])
        
        self.sample_df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature': temperatures
        })
        
        # Create sample spec
        self.sample_spec_data = {
            "job": {"job_id": "test123"},
            "industry": "powder",
            "spec": {
                "target_temp_C": 180.0,
                "hold_time_s": 600.0,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 300.0
            }
        }
        
        self.sample_spec = SpecV1(**self.sample_spec_data)
    
    def test_powder_coating_shadow_comparison_agreement(self):
        """Test powder coating shadow runs with agreement within tolerance."""
        # Create mock engine result
        engine_result = DecisionResult(
            pass_=True,
            status="PASS",
            industry="powder",
            job_id="test123",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=1200.0,
            required_hold_time_s=600.0,
            max_temp_C=182.5,
            min_temp_C=18.2,
            reasons=["Hold time 1200.0s ≥ required 600.0s"]
        )
        
        # Mock the make_decision to return our controlled result
        with patch('core.shadow_compare.make_decision', return_value=engine_result):
            result = self.comparator.run_shadow_comparison(self.sample_df, self.sample_spec)
        
        assert result.status == ShadowStatus.AGREEMENT
        assert result.engine_result == engine_result
        assert result.independent_result is not None
        assert result.differences is not None
    
    def test_powder_coating_tolerance_violation(self):
        """Test powder coating with tolerance violation causing INDETERMINATE."""
        # Create engine result that will disagree significantly with independent
        engine_result = DecisionResult(
            pass_=True,
            status="PASS", 
            industry="powder",
            job_id="test123",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=1200.0,  # This will be compared against independent calc
            required_hold_time_s=600.0,
            max_temp_C=182.5,
            min_temp_C=18.2,
            reasons=["Hold time 1200.0s ≥ required 600.0s"]
        )
        
        # Mock make_decision and create a scenario where independent calc differs significantly
        with patch('core.shadow_compare.make_decision', return_value=engine_result):
            # Mock the independent calculator to return a very different hold time
            with patch('validation.independent.powder_hold.calculate_hold_time', return_value=600.0):
                result = self.comparator.run_shadow_comparison(self.sample_df, self.sample_spec)
        
        # With default tolerance of 5% and 1s absolute for powder, a diff of 600s should violate
        assert result.status == ShadowStatus.TOLERANCE_VIOLATION
        assert "DIFF_EXCEEDS_TOL" in result.reason
        assert result.engine_result == engine_result
    
    def test_haccp_cooling_shadow_comparison(self):
        """Test HACCP cooling shadow comparison."""
        # Create HACCP data - cooling from 135F to 41F
        timestamps = pd.date_range('2024-01-01 12:00:00', periods=300, freq='1min')
        # 135F = 57.2C, 70F = 21.1C, 41F = 5.0C
        temperatures = np.concatenate([
            np.linspace(57.2, 21.1, 120),  # Phase 1: 2 hours to cool to 70F
            np.linspace(21.1, 5.0, 180)    # Phase 2: 3 more hours to cool to 41F
        ])
        
        haccp_df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature': temperatures
        })
        
        haccp_spec_data = {
            "job": {"job_id": "haccp123"},
            "industry": "haccp",
            "spec": {
                "target_temp_C": 57.2,
                "hold_time_s": 0.0,
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 120.0,
                "allowed_gaps_s": 600.0
            }
        }
        
        haccp_spec = SpecV1(**haccp_spec_data)
        
        # Mock engine result for HACCP
        engine_result = DecisionResult(
            pass_=True,
            status="PASS",
            industry="haccp", 
            job_id="haccp123",
            target_temp_C=57.2,
            conservative_threshold_C=58.2,
            actual_hold_time_s=0.0,
            required_hold_time_s=0.0,
            max_temp_C=57.2,
            min_temp_C=5.0,
            reasons=["HACCP cooling successful"]
        )
        
        # Add phase times to engine result (normally set by HACCP metrics engine)
        engine_result.phase1_actual_time_s = 7200.0  # 2 hours
        engine_result.phase2_actual_time_s = 18000.0  # 5 hours total
        
        with patch('core.shadow_compare.make_decision', return_value=engine_result):
            result = self.comparator.run_shadow_comparison(haccp_df, haccp_spec)
        
        assert result.status == ShadowStatus.AGREEMENT
        assert result.engine_result.industry == "haccp"
        assert 'phase1_actual_time_s' in result.independent_result
    
    def test_unsupported_industry(self):
        """Test shadow comparison for unsupported industry."""
        unsupported_spec_data = {
            "job": {"job_id": "unknown123"},
            "industry": "unknown",
            "spec": {
                "target_temp_C": 100.0,
                "hold_time_s": 300.0,
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 300.0
            }
        }
        
        unsupported_spec = SpecV1(**unsupported_spec_data)
        
        # Mock engine result
        engine_result = DecisionResult(
            pass_=True,
            status="PASS",
            industry="unknown",
            job_id="unknown123",
            target_temp_C=100.0,
            conservative_threshold_C=101.0,
            actual_hold_time_s=400.0,
            required_hold_time_s=300.0,
            max_temp_C=105.0,
            min_temp_C=20.0,
            reasons=["Pass"]
        )
        
        with patch('core.shadow_compare.make_decision', return_value=engine_result):
            result = self.comparator.run_shadow_comparison(self.sample_df, unsupported_spec)
        
        assert result.status == ShadowStatus.NOT_SUPPORTED
        assert result.engine_result == engine_result
        assert "Independent calculator not available" in result.reason
    
    def test_engine_error_handling(self):
        """Test handling of engine errors during shadow comparison."""
        with patch('core.shadow_compare.make_decision', side_effect=Exception("Engine failed")):
            result = self.comparator.run_shadow_comparison(self.sample_df, self.sample_spec)
        
        assert result.status == ShadowStatus.ENGINE_ERROR
        assert "Engine error" in result.reason
        assert "Engine failed" in result.reason
    
    def test_independent_calculator_error(self):
        """Test handling of independent calculator errors."""
        # Mock successful engine result
        engine_result = DecisionResult(
            pass_=True,
            status="PASS",
            industry="powder",
            job_id="test123",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=1200.0,
            required_hold_time_s=600.0,
            max_temp_C=182.5,
            min_temp_C=18.2,
            reasons=["Pass"]
        )
        
        with patch('core.shadow_compare.make_decision', return_value=engine_result):
            with patch('validation.independent.powder_hold.calculate_hold_time', 
                      side_effect=Exception("Independent calc failed")):
                result = self.comparator.run_shadow_comparison(self.sample_df, self.sample_spec)
        
        assert result.status == ShadowStatus.INDEPENDENT_ERROR
        assert result.engine_result == engine_result
        assert "Independent calculator error" in result.reason
    
    def test_tolerance_comparison_logic(self):
        """Test the tolerance comparison logic with various scenarios."""
        # Test absolute tolerance for powder hold time
        comparison = self.comparator._compare_values(
            1200.0, 1201.5, 'hold_time_s', 
            self.comparator.INDUSTRY_TOLERANCES['powder']
        )
        
        assert comparison['within_tolerance'] == False  # 1.5s > 1s tolerance
        assert comparison['tolerance_type'] == 'absolute'
        assert comparison['tolerance_used'] == 1.0
        
        # Test within tolerance
        comparison = self.comparator._compare_values(
            1200.0, 1200.8, 'hold_time_s',
            self.comparator.INDUSTRY_TOLERANCES['powder']
        )
        
        assert comparison['within_tolerance'] == True  # 0.8s < 1s tolerance
    
    def test_create_indeterminate_result(self):
        """Test creation of INDETERMINATE result from shadow violation."""
        original = DecisionResult(
            pass_=True,
            status="PASS", 
            industry="powder",
            job_id="test123",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=1200.0,
            required_hold_time_s=600.0,
            max_temp_C=182.5,
            min_temp_C=18.2,
            reasons=["Original pass reason"]
        )
        
        shadow = ShadowResult(
            status=ShadowStatus.TOLERANCE_VIOLATION,
            reason="DIFF_EXCEEDS_TOL: hold_time_s violation"
        )
        
        indeterminate = create_indeterminate_result(shadow, original)
        
        assert indeterminate.status == "INDETERMINATE"
        assert indeterminate.pass_ == False
        assert indeterminate.job_id == original.job_id
        assert indeterminate.industry == original.industry
        assert shadow.reason in indeterminate.reasons
        
        # Should preserve original measurements
        assert indeterminate.actual_hold_time_s == original.actual_hold_time_s
        assert indeterminate.max_temp_C == original.max_temp_C
    
    def test_multiple_metrics_comparison(self):
        """Test comparison when multiple metrics are available."""
        engine_result = DecisionResult(
            pass_=True,
            status="PASS",
            industry="powder", 
            job_id="test123",
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=1200.0,
            required_hold_time_s=600.0,
            max_temp_C=182.5,
            min_temp_C=18.2,
            reasons=["Pass"]
        )
        
        # Add additional metrics that might be compared
        engine_result.ramp_rate_C_per_min = 5.0
        engine_result.time_to_threshold_s = 450.0
        
        with patch('core.shadow_compare.make_decision', return_value=engine_result):
            # Mock independent calculators to return values within tolerance
            with patch('validation.independent.powder_hold.calculate_hold_time', return_value=1200.5):
                with patch('validation.independent.powder_hold.powder_ramp_rate', return_value=4.98):
                    with patch('validation.independent.powder_hold.calculate_time_to_threshold', return_value=450.2):
                        result = self.comparator.run_shadow_comparison(self.sample_df, self.sample_spec)
        
        assert result.status == ShadowStatus.AGREEMENT
        assert len(result.differences) >= 1  # Should have compared multiple metrics
        
        # All comparisons should be within tolerance
        for metric, comparison in result.differences.items():
            assert comparison['within_tolerance'], f"Metric {metric} outside tolerance: {comparison}"


class TestShadowIntegration:
    """Integration tests for shadow runs in the full pipeline."""
    
    def test_shadow_runs_environment_variable(self):
        """Test that shadow runs are controlled by environment variable."""
        # Test with environment variable disabled (default)
        with patch.dict(os.environ, {}, clear=True):
            from core.shadow_compare import ShadowComparator
            
            # Should not run shadow comparison by default
            # (This would be tested in app.py integration, here we just verify the env var logic)
            require_diff = os.getenv("REQUIRE_DIFF_AGREEMENT", "0").lower() in ["1", "true", "yes"]
            assert require_diff == False
        
        # Test with environment variable enabled
        with patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"}):
            require_diff = os.getenv("REQUIRE_DIFF_AGREEMENT", "0").lower() in ["1", "true", "yes"]
            assert require_diff == True
        
        with patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "true"}):
            require_diff = os.getenv("REQUIRE_DIFF_AGREEMENT", "0").lower() in ["1", "true", "yes"]
            assert require_diff == True
    
    def test_industry_specific_tolerances(self):
        """Test that each industry uses correct tolerances."""
        comparator = ShadowComparator()
        
        # Powder coating tolerances
        powder_tolerances = comparator.INDUSTRY_TOLERANCES['powder']
        assert powder_tolerances['hold_time_s'] == 1.0
        assert powder_tolerances['ramp_rate_C_per_min'] == 0.05  # 5%
        
        # HACCP tolerances
        haccp_tolerances = comparator.INDUSTRY_TOLERANCES['haccp']
        assert haccp_tolerances['phase1_time_s'] == 30.0
        assert haccp_tolerances['phase2_time_s'] == 30.0
        
        # Autoclave tolerances
        autoclave_tolerances = comparator.INDUSTRY_TOLERANCES['autoclave']
        assert autoclave_tolerances['fo_value'] == 0.1
        assert autoclave_tolerances['hold_time_s'] == 1.0
        
        # Sterile tolerances
        sterile_tolerances = comparator.INDUSTRY_TOLERANCES['sterile']
        assert sterile_tolerances['phase_times_s'] == 60.0
        
        # Concrete tolerances
        concrete_tolerances = comparator.INDUSTRY_TOLERANCES['concrete']
        assert concrete_tolerances['percent_in_spec_24h'] == 1.0
        assert concrete_tolerances['temperature_time_hours'] == 0.1
        
        # Cold chain tolerances
        coldchain_tolerances = comparator.INDUSTRY_TOLERANCES['coldchain']
        assert coldchain_tolerances['overall_compliance_pct'] == 0.5
        assert coldchain_tolerances['excursion_duration_s'] == 1.0


class TestShadowResultSerialization:
    """Test serialization of shadow results for storage and debugging."""
    
    def test_shadow_result_to_dict(self):
        """Test that ShadowResult can be serialized to dict/JSON."""
        engine_result = DecisionResult(
            pass_=True,
            status="PASS",
            industry="powder",
            job_id="test123", 
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            actual_hold_time_s=1200.0,
            required_hold_time_s=600.0,
            max_temp_C=182.5,
            min_temp_C=18.2,
            reasons=["Pass"]
        )
        
        shadow_result = ShadowResult(
            status=ShadowStatus.AGREEMENT,
            engine_result=engine_result,
            independent_result={'hold_time_s': 1200.5},
            differences={'hold_time_s': {'within_tolerance': True}},
            tolerances_used={'hold_time_s': 1.0}
        )
        
        result_dict = shadow_result.to_dict()
        
        assert result_dict['status'] == 'AGREEMENT'
        assert result_dict['engine_result'] is not None
        assert result_dict['independent_result']['hold_time_s'] == 1200.5
        assert result_dict['differences']['hold_time_s']['within_tolerance'] == True
        assert result_dict['tolerances_used']['hold_time_s'] == 1.0
        
        # Should be JSON serializable
        import json
        json_str = json.dumps(result_dict, default=str)
        assert isinstance(json_str, str)
    
    def test_tolerance_violation_result_serialization(self):
        """Test serialization of tolerance violation results."""
        shadow_result = ShadowResult(
            status=ShadowStatus.TOLERANCE_VIOLATION,
            reason="DIFF_EXCEEDS_TOL: hold_time_s: 1200 vs 1205 (diff: 5.000, tolerance: ±1)"
        )
        
        result_dict = shadow_result.to_dict()
        
        assert result_dict['status'] == 'TOLERANCE_VIOLATION'
        assert 'DIFF_EXCEEDS_TOL' in result_dict['reason']
        assert result_dict['engine_result'] is None
        assert result_dict['independent_result'] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])