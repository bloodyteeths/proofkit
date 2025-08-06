"""
Data Gaps Boundary Tests

Tests boundary conditions for data gaps:
- Gap exactly == allowed_gaps_s should pass
- Gap > allowed_gaps_s should fail
- Multiple gaps accumulation
- Edge cases around gap detection
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.normalize import normalize_temperature_data, NormalizationError
from core.decide import make_decision, DecisionError
from core.models import SpecV1, DecisionResult


class TestDataGapsBoundary:
    """Test boundary conditions for data gap detection and validation."""
    
    @pytest.fixture
    def base_spec(self):
        """Base specification with gap tolerance."""
        return {
            "version": "1.0",
            "job": {"job_id": "gap_boundary_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0  # Exactly 60 seconds allowed
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "sensors": ["temp_sensor"],
                "require_at_least": 1
            }
        }
    
    def create_data_with_gap(self, gap_seconds: float, num_samples: int = 50) -> pd.DataFrame:
        """Create temperature data with a specific gap in the middle."""
        # First half of data
        timestamps1 = pd.date_range(
            start="2024-01-15T10:00:00Z",
            periods=num_samples // 2,
            freq="30S",
            tz="UTC"
        )
        
        # Second half starts after the gap
        gap_start = timestamps1[-1] + timedelta(seconds=gap_seconds)
        timestamps2 = pd.date_range(
            start=gap_start,
            periods=num_samples // 2,
            freq="30S",
            tz="UTC"
        )
        
        # Combine timestamps
        all_timestamps = pd.concat([
            pd.Series(timestamps1),
            pd.Series(timestamps2)
        ])
        
        # Create temperature data (above threshold)
        temps = [182.5 + np.random.normal(0, 0.5) for _ in range(num_samples)]
        
        df = pd.DataFrame({
            "timestamp": all_timestamps,
            "temp_sensor": temps
        })
        
        return df
    
    def test_gap_exactly_at_boundary_passes(self, base_spec):
        """Test that a gap exactly equal to allowed_gaps_s passes."""
        # Create data with exactly 60-second gap
        df = self.create_data_with_gap(gap_seconds=60.0)
        
        # Normalize with the exact boundary
        spec = SpecV1(**base_spec)
        
        # This should pass - gap is exactly at the limit
        try:
            normalized = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,
                max_sample_period_s=30.0
            )
            
            # Should succeed without raising exception
            assert normalized is not None
            assert len(normalized) > 0
            
            # Verify normalization succeeded with gap at boundary
            # Gap detection is internal to normalize function
            
        except NormalizationError:
            pytest.fail("Normalization should pass with gap exactly at boundary")
    
    def test_gap_exceeding_boundary_fails(self, base_spec):
        """Test that a gap exceeding allowed_gaps_s fails."""
        # Create data with 61-second gap (1 second over limit)
        df = self.create_data_with_gap(gap_seconds=61.0)
        
        spec = SpecV1(**base_spec)
        
        # This should fail - gap exceeds limit
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,  # Limit is 60
                max_sample_period_s=30.0
            )
        
        # Check error message mentions gap
        assert "gap" in str(exc_info.value).lower()
    
    def test_gap_just_under_boundary_passes(self, base_spec):
        """Test that a gap just under the boundary passes."""
        # Create data with 59.9-second gap
        df = self.create_data_with_gap(gap_seconds=59.9)
        
        spec = SpecV1(**base_spec)
        
        # This should pass - gap is under the limit
        try:
            normalized = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,
                max_sample_period_s=30.0
            )
            
            assert normalized is not None
            # Gap is under the limit, so normalization succeeds
                
        except NormalizationError:
            pytest.fail("Normalization should pass with gap under boundary")
    
    def test_multiple_gaps_cumulative_check(self, base_spec):
        """Test multiple gaps that individually pass but cumulatively might fail."""
        # Create data with multiple smaller gaps
        timestamps = []
        temps = []
        
        # Pattern: 10 samples, 45s gap, 10 samples, 45s gap, 10 samples
        current_time = pd.Timestamp("2024-01-15T10:00:00Z")
        
        for segment in range(3):
            # Add 10 samples
            for i in range(10):
                timestamps.append(current_time)
                temps.append(182.5 + np.random.normal(0, 0.5))
                current_time += timedelta(seconds=30)
            
            # Add gap (except after last segment)
            if segment < 2:
                current_time += timedelta(seconds=45)  # 45s gap
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps
        })
        
        spec = SpecV1(**base_spec)
        
        # Each gap is 45s (under 60s limit), should pass
        try:
            normalized = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,
                max_sample_period_s=30.0
            )
            
            # Each gap is 45s (under 60s limit), should pass
            
        except NormalizationError:
            pytest.fail("Multiple gaps under limit should pass")
    
    def test_gap_at_data_boundaries(self, base_spec):
        """Test gap detection at the start and end of data."""
        # Create data with gap at the beginning
        timestamps = []
        temps = []
        
        # Start with a timestamp, then jump forward
        timestamps.append(pd.Timestamp("2024-01-15T10:00:00Z"))
        temps.append(182.5)
        
        # Jump 65 seconds (exceeds limit)
        next_time = timestamps[0] + timedelta(seconds=65)
        
        # Add more regular samples
        for i in range(20):
            timestamps.append(next_time)
            temps.append(182.5 + np.random.normal(0, 0.5))
            next_time += timedelta(seconds=30)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps
        })
        
        # This should fail due to large gap at start
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,
                max_sample_period_s=30.0
            )
        
        assert "gap" in str(exc_info.value).lower()
    
    def test_floating_point_gap_precision(self, base_spec):
        """Test floating-point precision in gap detection."""
        # Create gaps that are very close to the boundary due to floating point
        timestamps = []
        temps = []
        
        # Use precise timedelta calculations
        current = pd.Timestamp("2024-01-15T10:00:00Z")
        
        for i in range(20):
            timestamps.append(current)
            temps.append(182.5)
            
            if i == 10:
                # Add a gap that's exactly 60.0 seconds in theory
                # but might be 60.000000001 due to float precision
                current += timedelta(seconds=30.0)
                current += timedelta(seconds=60.0)
            else:
                current += timedelta(seconds=30.0)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": temps
        })
        
        # Should handle floating-point comparison properly
        try:
            normalized = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,
                max_sample_period_s=30.0
            )
            
            # Should pass even with potential float precision issues
            assert normalized is not None
            
        except NormalizationError as e:
            # If it fails, check it's not due to tiny float differences
            if "60.00000" in str(e):
                pytest.fail("Gap detection should handle float precision")
            else:
                raise
    
    def test_decision_with_gap_boundary(self, base_spec):
        """Test full decision process with gap at boundary."""
        # Create data with exactly allowed gap
        df = self.create_data_with_gap(gap_seconds=60.0, num_samples=50)
        
        spec = SpecV1(**base_spec)
        
        # Run full decision process
        result = make_decision(df, spec)
        
        assert isinstance(result, DecisionResult)
        
        # Check if warnings mention the gap
        gap_warnings = [w for w in result.warnings if 'gap' in w.lower()]
        
        # Should have warning about gap being at limit
        assert len(gap_warnings) > 0
    
    def test_zero_gap_handling(self, base_spec):
        """Test handling when allowed_gaps_s is 0 (no gaps allowed)."""
        # Modify spec to allow no gaps
        spec_data = base_spec.copy()
        spec_data['data_requirements']['allowed_gaps_s'] = 0.0
        
        # Create perfect data (no gaps)
        df = pd.DataFrame({
            "timestamp": pd.date_range(
                start="2024-01-15T10:00:00Z",
                periods=30,
                freq="30S",
                tz="UTC"
            ),
            "temp_sensor": [182.5] * 30
        })
        
        spec = SpecV1(**spec_data)
        
        # Should pass with no gaps
        try:
            normalized = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=0.0,
                max_sample_period_s=30.0
            )
            assert normalized is not None
        except NormalizationError:
            pytest.fail("Should pass with no gaps when allowed_gaps_s=0")
        
        # Now add even a tiny gap
        df.loc[15, 'timestamp'] += timedelta(seconds=1)  # 1 second gap
        
        # Should fail with any gap
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=0.0,
                max_sample_period_s=30.0
            )
        
        assert "gap" in str(exc_info.value).lower()
    
    def test_negative_gap_handling(self):
        """Test handling of negative gaps (overlapping timestamps)."""
        # Create data with overlapping timestamps
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z",
            periods=20,
            freq="30S",
            tz="UTC"
        )
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "temp_sensor": [182.5] * 20
        })
        
        # Make some timestamps go backwards
        df.loc[10, 'timestamp'] = df.loc[8, 'timestamp']  # Duplicate
        df.loc[11, 'timestamp'] = df.loc[7, 'timestamp']  # Out of order
        
        # Should handle gracefully
        with pytest.raises(NormalizationError) as exc_info:
            normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=60.0,
                max_sample_period_s=30.0
            )
        
        # Should mention timestamp issues
        error_msg = str(exc_info.value).lower()
        assert "timestamp" in error_msg or "duplicate" in error_msg or "order" in error_msg