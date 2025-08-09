"""
Test coldchain fixes for 2 specific failures:
- fail expected FAIL → got INDETERMINATE
- pass expected PASS → got INDETERMINATE

These tests verify:
1. Temperature is the only required signal (not humidity/CO2)
2. Return PASS/FAIL based on daily % in [2,8]°C range  
3. Use INDETERMINATE only for insufficient data
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from core.models import SpecV1, DecisionResult, SensorMode
from core.metrics_coldchain import validate_coldchain_storage
from core.decide import DecisionError


class TestColdChainFixes:
    """Test cold chain validation fixes for specific failure cases."""
    
    def get_basic_spec(self) -> SpecV1:
        """Create basic cold chain spec."""
        return SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "coldchain_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 300.0,
                "allowed_gaps_s": 900.0
            }
        })
    
    def test_pass_case_95_percent_compliance(self):
        """Test that data with ≥95% compliance returns PASS (not INDETERMINATE)."""
        # Create data with exactly 95% compliance in 2-8°C range
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # 95 samples in range [2,8]°C, 5 samples outside
        temp_values = [4.0] * 95 + [10.0] * 5  # 95% compliance
        np.random.shuffle(temp_values)  # Randomize order
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.1 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should PASS (not INDETERMINATE)
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True, f"Expected PASS but got pass_={result.pass_}, reasons: {result.reasons}"
        
        # Check reasons mention compliance percentage
        reasons_text = " ".join(result.reasons).lower()
        assert "95" in reasons_text or "compliance" in reasons_text
        assert "cold chain" in reasons_text or "storage" in reasons_text
    
    def test_pass_case_99_percent_compliance(self):
        """Test that data with 99% compliance returns PASS."""
        # Create data with 99% compliance in 2-8°C range
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # 99 samples in range [2,8]°C, 1 sample outside
        temp_values = [4.0] * 99 + [15.0] * 1  # 99% compliance
        np.random.shuffle(temp_values)
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.05 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should PASS
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True, f"Expected PASS but got pass_={result.pass_}, reasons: {result.reasons}"
    
    def test_fail_case_90_percent_compliance(self):
        """Test that data with <95% compliance returns FAIL (not INDETERMINATE)."""
        # Create data with 90% compliance in 2-8°C range  
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # 90 samples in range [2,8]°C, 10 samples outside
        temp_values = [4.0] * 90 + [15.0] * 10  # 90% compliance
        np.random.shuffle(temp_values)
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.1 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should FAIL (not INDETERMINATE)
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False, f"Expected FAIL but got pass_={result.pass_}, reasons: {result.reasons}"
        
        # Check failure reasons mention compliance
        reasons_text = " ".join(result.reasons).lower()
        assert "90" in reasons_text or "compliance" in reasons_text
        assert "95" in reasons_text  # Should mention the 95% requirement
    
    def test_fail_case_all_outside_range(self):
        """Test that data with 0% compliance returns FAIL."""
        # Create data with all samples outside 2-8°C range
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=50, freq="5min", tz="UTC"
        )
        
        # All samples way above range
        temp_values = [20.0] * 50  # 0% compliance
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.2 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should FAIL
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False, f"Expected FAIL but got pass_={result.pass_}, reasons: {result.reasons}"
        
        # Check reasons mention low compliance
        reasons_text = " ".join(result.reasons).lower()
        assert "0" in reasons_text or "compliance" in reasons_text
    
    def test_indeterminate_insufficient_data(self):
        """Test that insufficient data returns INDETERMINATE (raises DecisionError)."""
        # Create data with very few points (< 2, triggers early check)
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=1, freq="5min", tz="UTC"
        )
        
        # Perfect compliance but insufficient data
        temp_values = [4.0] * 1  # All in range but too few points
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.1 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        
        # Should raise DecisionError for insufficient data (INDETERMINATE)
        with pytest.raises(DecisionError, match="Insufficient data points for cold chain storage analysis"):
            validate_coldchain_storage(data, spec)
    
    def test_temperature_only_required_signal(self):
        """Test that only temperature is required (humidity/CO2 ignored)."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # Data with temperature (95% compliant) plus other signals that should be ignored
        temp_values = [4.0] * 95 + [15.0] * 5  # 95% compliance
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.1 for t in temp_values],
            "humidity_1": [60.0] * 100,  # Should be ignored
            "co2_1": [400.0] * 100,  # Should be ignored
            "pressure_1": [101.3] * 100  # Should be ignored
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should PASS based only on temperature
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True, f"Expected PASS but got pass_={result.pass_}, reasons: {result.reasons}"
    
    def test_edge_case_exactly_95_percent(self):
        """Test edge case with exactly 95.0% compliance."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # Exactly 95 samples in range, 5 outside
        temp_values = [4.0] * 95 + [10.0] * 5  # Exactly 95% compliance
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.05 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should PASS (≥95% requirement)
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True, f"Expected PASS but got pass_={result.pass_}, reasons: {result.reasons}"
    
    def test_edge_case_just_below_95_percent(self):
        """Test edge case with 94.9% compliance (just below threshold)."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=1000, freq="1min", tz="UTC"  # Use 1000 samples for precise percentage
        )
        
        # 949 samples in range, 51 outside = 94.9% compliance
        temp_values = [4.0] * 949 + [15.0] * 51  # 94.9% compliance
        np.random.shuffle(temp_values)
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": temp_values,
            "temp_2": [t + 0.1 for t in temp_values]
        })
        
        spec = self.get_basic_spec()
        result = validate_coldchain_storage(data, spec)
        
        # Should FAIL (<95% requirement)
        assert isinstance(result, DecisionResult)
        assert result.pass_ is False, f"Expected FAIL but got pass_={result.pass_}, reasons: {result.reasons}"
    
    def test_sensor_mode_handling(self):
        """Test that different sensor modes work correctly."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # Create data where sensors disagree slightly but overall compliance is good
        base_temp = [4.0] * 95 + [10.0] * 5  # 95% compliance on average
        
        data = pd.DataFrame({
            "timestamp": timestamps,
            "temp_1": base_temp,
            "temp_2": [t + 0.5 for t in base_temp],  # Slightly higher
            "temp_3": [t - 0.3 for t in base_temp]   # Slightly lower
        })
        
        # Test with majority_over_threshold mode
        spec = SpecV1(**{
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "sensor_mode_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 5.0,
                "hold_time_s": 3600,
                "sensor_uncertainty_C": 0.5
            },
            "data_requirements": {
                "max_sample_period_s": 300.0,
                "allowed_gaps_s": 900.0
            },
            "sensor_selection": {
                "mode": "majority_over_threshold",
                "require_at_least": 2
            }
        })
        
        result = validate_coldchain_storage(data, spec)
        
        # Should handle sensor combination and still PASS
        assert isinstance(result, DecisionResult)
        assert result.pass_ is True, f"Expected PASS but got pass_={result.pass_}, reasons: {result.reasons}"
    
    def test_missing_temperature_columns_error(self):
        """Test that missing temperature columns raises appropriate error."""
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", periods=100, freq="5min", tz="UTC"
        )
        
        # Data without temperature columns
        data = pd.DataFrame({
            "timestamp": timestamps,
            "humidity_1": [60.0] * 100,
            "pressure_1": [101.3] * 100
        })
        
        spec = self.get_basic_spec()
        
        # Should raise DecisionError for missing temperature columns
        with pytest.raises(DecisionError, match="No temperature columns found in normalized data"):
            validate_coldchain_storage(data, spec)


if __name__ == "__main__":
    # Run tests manually
    test_class = TestColdChainFixes()
    
    print("Testing PASS case (95% compliance)...")
    test_class.test_pass_case_95_percent_compliance()
    print("✓ PASS")
    
    print("Testing FAIL case (90% compliance)...")  
    test_class.test_fail_case_90_percent_compliance()
    print("✓ PASS")
    
    print("Testing INDETERMINATE case (insufficient data)...")
    try:
        test_class.test_indeterminate_insufficient_data()
        print("✓ PASS")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    print("Testing temperature-only requirement...")
    test_class.test_temperature_only_required_signal()
    print("✓ PASS")
    
    print("All critical tests completed!")