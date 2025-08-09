"""
Integration Tests for Shadow Runs in Application Pipeline

Tests the complete integration of shadow runs within the ProofKit
application, including environment variable control and INDETERMINATE
result handling.
"""

import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.shadow_compare import ShadowStatus, ShadowResult
from core.models import SpecV1


class TestShadowIntegrationApp:
    """Test shadow runs integration in app pipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create sample CSV data
        self.sample_csv = """timestamp,temperature
2024-01-01T12:00:00,20.0
2024-01-01T12:00:30,25.0
2024-01-01T12:01:00,50.0
2024-01-01T12:01:30,100.0
2024-01-01T12:02:00,150.0
2024-01-01T12:02:30,180.0
2024-01-01T12:03:00,180.0
2024-01-01T12:03:30,180.0
2024-01-01T12:04:00,180.0
2024-01-01T12:04:30,180.0
2024-01-01T12:05:00,180.0
2024-01-01T12:05:30,180.0
2024-01-01T12:06:00,180.0
2024-01-01T12:06:30,180.0
2024-01-01T12:07:00,180.0
2024-01-01T12:07:30,180.0
2024-01-01T12:08:00,180.0
2024-01-01T12:08:30,180.0
2024-01-01T12:09:00,180.0
2024-01-01T12:09:30,180.0
2024-01-01T12:10:00,180.0
2024-01-01T12:10:30,150.0
2024-01-01T12:11:00,100.0
2024-01-01T12:11:30,50.0
2024-01-01T12:12:00,25.0
"""
        
        # Sample spec for powder coating
        self.sample_spec = {
            "job": {"job_id": "integration_test"},
            "industry": "powder",
            "spec": {
                "target_temp_C": 180.0,
                "hold_time_s": 300.0,  # 5 minutes
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 300.0
            }
        }
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_shadow_runs_enabled_agreement(self):
        """Test shadow runs when enabled with agreement result."""
        from app import process_csv_and_spec
        
        # Create temporary directory for job storage
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock shadow comparison to return agreement
            mock_shadow_result = ShadowResult(
                status=ShadowStatus.AGREEMENT,
                reason=None
            )
            
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison', 
                      return_value=mock_shadow_result):
                result = process_csv_and_spec(
                    csv_bytes, self.sample_spec, job_dir, "test123"
                )
            
            # Should complete successfully with original decision
            assert result['pass'] == True  # This specific CSV should pass
            assert result['id'] == "test123"
            
            # Should have saved shadow comparison results
            shadow_file = job_dir / "shadow_comparison.json"
            assert shadow_file.exists()
            
            with open(shadow_file, 'r') as f:
                shadow_data = json.load(f)
                assert shadow_data['status'] == 'AGREEMENT'
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_shadow_runs_tolerance_violation_indeterminate(self):
        """Test shadow runs with tolerance violation resulting in INDETERMINATE."""
        from app import process_csv_and_spec
        
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock shadow comparison to return tolerance violation
            mock_shadow_result = ShadowResult(
                status=ShadowStatus.TOLERANCE_VIOLATION,
                reason="DIFF_EXCEEDS_TOL: hold_time_s: 600.0 vs 605.0 (diff: 5.000, tolerance: ±1)"
            )
            
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison',
                      return_value=mock_shadow_result):
                result = process_csv_and_spec(
                    csv_bytes, self.sample_spec, job_dir, "test123"
                )
            
            # Should result in INDETERMINATE status
            assert result['status'] == 'INDETERMINATE'
            assert result['pass'] == False
            
            # Check decision.json was saved with INDETERMINATE status
            decision_file = job_dir / "decision.json"
            assert decision_file.exists()
            
            with open(decision_file, 'r') as f:
                decision_data = json.load(f)
                assert decision_data['status'] == 'INDETERMINATE'
                assert 'DIFF_EXCEEDS_TOL' in str(decision_data.get('reasons', []))
            
            # Shadow comparison results should be saved
            shadow_file = job_dir / "shadow_comparison.json"
            assert shadow_file.exists()
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "0"})  # Explicitly disabled
    def test_shadow_runs_disabled(self):
        """Test that shadow runs are disabled by default."""
        from app import process_csv_and_spec
        
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock that should NOT be called since shadow runs are disabled
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison') as mock_shadow:
                result = process_csv_and_spec(
                    csv_bytes, self.sample_spec, job_dir, "test123"
                )
            
            # Shadow comparison should not have been called
            mock_shadow.assert_not_called()
            
            # Should complete with normal processing
            assert 'pass' in result
            
            # Shadow comparison file should not exist
            shadow_file = job_dir / "shadow_comparison.json"
            assert not shadow_file.exists()
    
    def test_shadow_runs_default_disabled(self):
        """Test that shadow runs are disabled by default when env var not set."""
        # Clear the environment variable
        with patch.dict(os.environ, {}, clear=True):
            from app import process_csv_and_spec
            
            with tempfile.TemporaryDirectory() as temp_dir:
                job_dir = Path(temp_dir) / "test_job"
                job_dir.mkdir()
                
                csv_bytes = self.sample_csv.encode('utf-8')
                
                with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison') as mock_shadow:
                    result = process_csv_and_spec(
                        csv_bytes, self.sample_spec, job_dir, "test123"
                    )
                
                # Should not call shadow comparison
                mock_shadow.assert_not_called()
                
                # Should complete normally
                assert 'pass' in result
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_shadow_runs_engine_error_fallback(self):
        """Test graceful handling when shadow comparison fails with engine error."""
        from app import process_csv_and_spec
        
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock shadow comparison to return engine error
            mock_shadow_result = ShadowResult(
                status=ShadowStatus.ENGINE_ERROR,
                reason="Engine error: Something went wrong"
            )
            
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison',
                      return_value=mock_shadow_result):
                result = process_csv_and_spec(
                    csv_bytes, self.sample_spec, job_dir, "test123"
                )
            
            # Should complete with original decision (fallback behavior)
            assert 'pass' in result
            assert result['id'] == "test123"
            
            # Shadow comparison results should still be saved for debugging
            shadow_file = job_dir / "shadow_comparison.json"
            assert shadow_file.exists()
            
            with open(shadow_file, 'r') as f:
                shadow_data = json.load(f)
                assert shadow_data['status'] == 'ENGINE_ERROR'
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_shadow_runs_independent_error_fallback(self):
        """Test graceful handling when independent calculator fails."""
        from app import process_csv_and_spec
        
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock shadow comparison to return independent error
            mock_shadow_result = ShadowResult(
                status=ShadowStatus.INDEPENDENT_ERROR,
                reason="Independent calculator error: Division by zero"
            )
            
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison',
                      return_value=mock_shadow_result):
                result = process_csv_and_spec(
                    csv_bytes, self.sample_spec, job_dir, "test123"
                )
            
            # Should complete with original decision (fallback behavior)
            assert 'pass' in result
            assert result['id'] == "test123"
            
            # Shadow comparison results should be saved for debugging
            shadow_file = job_dir / "shadow_comparison.json"
            assert shadow_file.exists()
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_shadow_runs_not_supported_industry(self):
        """Test shadow runs with industry not supported by independent calculators."""
        from app import process_csv_and_spec
        
        # Use an unsupported industry
        unsupported_spec = self.sample_spec.copy()
        unsupported_spec['industry'] = 'unknown'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock shadow comparison to return not supported
            mock_shadow_result = ShadowResult(
                status=ShadowStatus.NOT_SUPPORTED,
                reason="Independent calculator not available for unknown"
            )
            
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison',
                      return_value=mock_shadow_result):
                result = process_csv_and_spec(
                    csv_bytes, unsupported_spec, job_dir, "test123"
                )
            
            # Should complete with original decision
            assert 'pass' in result
            
            # Shadow results should be saved
            shadow_file = job_dir / "shadow_comparison.json"
            assert shadow_file.exists()
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_shadow_runs_exception_handling(self):
        """Test that exceptions in shadow comparison don't break main processing."""
        from app import process_csv_and_spec
        
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "test_job"
            job_dir.mkdir()
            
            csv_bytes = self.sample_csv.encode('utf-8')
            
            # Mock shadow comparison to raise an exception
            with patch('core.shadow_compare.ShadowComparator.run_shadow_comparison',
                      side_effect=Exception("Shadow system failure")):
                result = process_csv_and_spec(
                    csv_bytes, self.sample_spec, job_dir, "test123"
                )
            
            # Should complete with original decision despite shadow failure
            assert 'pass' in result
            assert result['id'] == "test123"
            
            # Shadow comparison file should not exist due to exception
            shadow_file = job_dir / "shadow_comparison.json"
            assert not shadow_file.exists()
    
    def test_various_environment_variable_values(self):
        """Test different ways to enable shadow runs via environment variables."""
        test_cases = [
            ("1", True),
            ("true", True), 
            ("TRUE", True),
            ("yes", True),
            ("YES", True),
            ("0", False),
            ("false", False),
            ("FALSE", False),
            ("no", False),
            ("NO", False),
            ("", False),
            ("invalid", False)
        ]
        
        for env_value, should_be_enabled in test_cases:
            with patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": env_value}):
                require_diff = os.getenv("REQUIRE_DIFF_AGREEMENT", "0").lower() in ["1", "true", "yes"]
                assert require_diff == should_be_enabled, f"Value '{env_value}' should be {should_be_enabled}"


class TestShadowRunsComprehensive:
    """Comprehensive tests covering all industry shadow runs."""
    
    @patch.dict(os.environ, {"REQUIRE_DIFF_AGREEMENT": "1"})
    def test_all_industries_shadow_support(self):
        """Test that shadow runs work for all supported industries."""
        from core.shadow_compare import ShadowComparator
        
        comparator = ShadowComparator()
        supported_industries = ['powder', 'haccp', 'coldchain', 'autoclave', 'concrete']
        
        # Verify all industries have tolerance definitions
        for industry in supported_industries:
            assert industry in comparator.INDUSTRY_TOLERANCES, f"No tolerances for {industry}"
            tolerances = comparator.INDUSTRY_TOLERANCES[industry]
            assert len(tolerances) > 0, f"Empty tolerances for {industry}"
    
    def test_tolerance_values_meet_specification(self):
        """Test that tolerance values match the specification requirements."""
        from core.shadow_compare import ShadowComparator
        
        comparator = ShadowComparator()
        
        # Verify powder tolerances
        powder = comparator.INDUSTRY_TOLERANCES['powder']
        assert powder['hold_time_s'] == 1.0
        assert powder['ramp_rate_C_per_min'] == 0.05  # 5% relative
        
        # Verify autoclave tolerances  
        autoclave = comparator.INDUSTRY_TOLERANCES['autoclave']
        assert autoclave['fo_value'] == 0.1
        
        # Verify HACCP tolerances
        haccp = comparator.INDUSTRY_TOLERANCES['haccp']
        assert haccp['phase1_time_s'] == 30.0
        assert haccp['phase2_time_s'] == 30.0
        
        # Verify concrete tolerances
        concrete = comparator.INDUSTRY_TOLERANCES['concrete']
        assert concrete['percent_in_spec_24h'] == 1.0
        
        # Verify cold chain tolerances
        coldchain = comparator.INDUSTRY_TOLERANCES['coldchain']
        assert coldchain['overall_compliance_pct'] == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])