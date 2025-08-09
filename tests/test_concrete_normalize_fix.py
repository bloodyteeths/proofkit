"""
Test to verify concrete fixture normalization fix.

This test validates that concrete fixtures with 5-minute intervals
normalize correctly without collapsing to 1 data point.
"""

import pandas as pd
from pathlib import Path

from core.normalize import load_csv_with_metadata, normalize_temperature_data
from core.metrics_concrete import validate_concrete_curing
from core.models import SpecV1
from core.temperature_utils import DecisionError


class TestConcreteNormalizeFix:
    """Test concrete fixture normalization fixes."""
    
    def test_concrete_fixture_normalization(self):
        """Test that concrete fixtures normalize without losing data points."""
        # Load concrete fixture
        fixture_path = Path(__file__).parent / "data" / "concrete_curing_pass.csv"
        df, metadata = load_csv_with_metadata(str(fixture_path))
        
        original_count = len(df)
        assert original_count > 0, "Fixture should have data"
        
        # Normalize with appropriate settings for concrete industry
        normalized_df = normalize_temperature_data(
            df, 
            target_step_s=300.0,  # 5 minutes to match fixture
            allowed_gaps_s=1800.0,  # 30 minutes allowed gaps  
            max_sample_period_s=900.0,  # 15 minutes max period
            industry='concrete'
        )
        
        # Should preserve original data points since intervals match
        assert len(normalized_df) == original_count
        assert len(normalized_df) > 10, f"Expected >10 points, got {len(normalized_df)}"
        
        # Check time range is preserved
        original_start = pd.to_datetime(df['timestamp'].iloc[0])
        original_end = pd.to_datetime(df['timestamp'].iloc[-1])
        normalized_start = pd.to_datetime(normalized_df['timestamp'].iloc[0])
        normalized_end = pd.to_datetime(normalized_df['timestamp'].iloc[-1])
        
        original_duration = (original_end - original_start).total_seconds()
        normalized_duration = (normalized_end - normalized_start).total_seconds()
        assert abs(original_duration - normalized_duration) < 60, "Duration should be preserved"
    
    def test_concrete_fixture_with_default_normalization(self):
        """Test concrete fixture with default normalization settings (should be smart)."""
        fixture_path = Path(__file__).parent / "data" / "concrete_curing_pass.csv"
        df, metadata = load_csv_with_metadata(str(fixture_path))
        
        original_count = len(df)
        
        # Test with default 30s target but appropriate gap settings
        normalized_df = normalize_temperature_data(
            df, 
            target_step_s=30.0,  # Default 30 seconds
            allowed_gaps_s=1800.0,  # 30 minutes allowed gaps  
            max_sample_period_s=900.0,  # 15 minutes max period
            industry='concrete'
        )
        
        # Should either preserve original data or provide reasonable resampling
        assert len(normalized_df) >= 10, f"Expected ≥10 points, got {len(normalized_df)}"
    
    def test_concrete_end_to_end_validation(self):
        """Test full end-to-end concrete validation with fixture."""
        fixture_path = Path(__file__).parent / "data" / "concrete_curing_pass.csv"
        df, metadata = load_csv_with_metadata(str(fixture_path))
        
        # Normalize data
        normalized_df = normalize_temperature_data(
            df, 
            target_step_s=300.0,  
            allowed_gaps_s=1800.0, 
            max_sample_period_s=900.0,
            industry='concrete'
        )
        
        # Create concrete spec
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_fixture_validation"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 23.0,
                "hold_time_s": 86400,  # 24 hours
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 900.0,
                "allowed_gaps_s": 1800.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 1
            }
        }
        
        spec = SpecV1(**spec_data)
        result = validate_concrete_curing(normalized_df, spec)
        
        # Validation should complete without error
        assert result is not None
        assert result.job_id == "test_fixture_validation"
        assert result.industry == "concrete"
        assert len(result.reasons) > 0, "Should have reasons for decision"
        
        # Result should be based on actual data analysis
        assert isinstance(result.pass_, bool)
        
        print(f"Concrete validation result: {'PASS' if result.pass_ else 'FAIL'}")
        print(f"Reasons: {result.reasons[:2]}")  # Show first 2 reasons


def run_tests():
    """Run all test methods."""
    test_instance = TestConcreteNormalizeFix()
    
    tests = [
        "test_concrete_fixture_normalization",
        "test_concrete_fixture_with_default_normalization", 
        "test_concrete_end_to_end_validation",
    ]
    
    passed = 0
    failed = 0
    
    for test_name in tests:
        try:
            print(f"Running {test_name}...")
            getattr(test_instance, test_name)()
            print(f"  PASSED")
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
    
    print(f"\nTest Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)