"""
Test file to validate the sterile pass/fail fix.

Tests focus on:
1. Temperature window 50-60°C validation
2. Humidity window 45-85% RH validation  
3. Gas concentration validation
4. Ensuring FAIL (not INDETERMINATE) when conditions not met

Example usage:
    python -m pytest tests/test_sterile_fix.py -v
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone

from core.models import SpecV1, DecisionResult
from core.metrics_sterile import validate_eto_sterilization


class TestSterileFix:
    """Test cases to validate the sterile pass/fail fix."""
    
    def create_test_data(self, temp_value=55.0, humidity_value=65.0, gas_value=500.0, duration_hours=3):
        """Create test DataFrame with specified parameter values."""
        num_points = duration_hours * 30  # 2-minute intervals
        timestamps = pd.date_range(
            start="2024-01-15T10:00:00Z", 
            periods=num_points, 
            freq="2min", 
            tz="UTC"
        )
        
        data = {
            "timestamp": timestamps,
            "temp_1": [temp_value + np.random.normal(0, 0.2) for _ in range(num_points)],
            "temp_2": [temp_value + np.random.normal(0, 0.3) for _ in range(num_points)],
            "temp_3": [temp_value + np.random.normal(0, 0.1) for _ in range(num_points)]
        }
        
        if humidity_value is not None:
            data["humidity_1"] = [humidity_value + np.random.normal(0, 1.0) for _ in range(num_points)]
            data["humidity_rh"] = [humidity_value + np.random.normal(0, 0.5) for _ in range(num_points)]
        
        if gas_value is not None:
            data["eto_ppm"] = [gas_value + np.random.normal(0, 10.0) for _ in range(num_points)]
            data["gas_concentration"] = [gas_value + np.random.normal(0, 5.0) for _ in range(num_points)]
        
        return pd.DataFrame(data)
    
    def get_base_spec(self):
        """Get base sterile specification."""
        return {
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "sterile_fix_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 55.0,
                "hold_time_s": 7200,  # 2 hours
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 120.0,
                "allowed_gaps_s": 300.0
            },
            "sensor_selection": {
                "mode": "mean_of_set"
            }
        }
    
    def test_temperature_window_pass_50_60C(self):
        """Test that temperatures in 50-60°C window result in PASS."""
        # Test temperature at minimum boundary (50°C)
        df = self.create_test_data(temp_value=50.1, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS for temp=50.1°C, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
        
        # Test temperature at maximum boundary (60°C)
        df = self.create_test_data(temp_value=59.5, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS for temp=59.5°C, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
        
        # Test temperature in middle of range (55°C)
        df = self.create_test_data(temp_value=55.0, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS for temp=55°C, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
    
    def test_temperature_window_fail_outside_50_60C(self):
        """Test that temperatures outside 50-60°C window result in FAIL."""
        # Test temperature below minimum (< 50°C)
        df = self.create_test_data(temp_value=48.0, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == False, f"Expected FAIL for temp=48°C, got PASS"
        assert result.status == 'FAIL', f"Expected status=FAIL, got {result.status}"
        assert "Temperature never reached sterilization range" in " ".join(result.reasons)
        
        # Test temperature above maximum (> 60°C)
        df = self.create_test_data(temp_value=65.0, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == False, f"Expected FAIL for temp=65°C, got PASS"
        assert result.status == 'FAIL', f"Expected status=FAIL, got {result.status}"
        assert "Maximum temperature" in " ".join(result.reasons) and "60.0°C limit" in " ".join(result.reasons)
    
    def test_humidity_window_pass_45_85_RH(self):
        """Test that humidity in 45-85% RH window results in PASS."""
        # Test humidity at minimum boundary (45% RH)
        df = self.create_test_data(temp_value=55.0, humidity_value=47.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS for RH=47%, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
        
        # Test humidity at maximum boundary (85% RH)
        df = self.create_test_data(temp_value=55.0, humidity_value=83.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS for RH=83%, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
        
        # Test humidity in middle of range (65% RH)
        df = self.create_test_data(temp_value=55.0, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS for RH=65%, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
    
    def test_humidity_window_fail_outside_45_85_RH(self):
        """Test that humidity outside 45-85% RH window results in FAIL."""
        # Test humidity below minimum (< 45% RH)
        df = self.create_test_data(temp_value=55.0, humidity_value=35.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == False, f"Expected FAIL for RH=35%, got PASS"
        assert result.status == 'FAIL', f"Expected status=FAIL, got {result.status}"
        assert "Humidity outside range" in " ".join(result.reasons)
        
        # Test humidity above maximum (> 85% RH)
        df = self.create_test_data(temp_value=55.0, humidity_value=95.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == False, f"Expected FAIL for RH=95%, got PASS"
        assert result.status == 'FAIL', f"Expected status=FAIL, got {result.status}"
        assert "Humidity outside range" in " ".join(result.reasons)
    
    def test_gas_concentration_validation(self):
        """Test gas concentration validation when data is available."""
        # Test with adequate gas concentration
        df = self.create_test_data(temp_value=55.0, humidity_value=65.0, gas_value=500.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS with gas=500ppm, got FAIL. Reasons: {result.reasons}"
        assert "sterilization requirements met" in " ".join(result.reasons)
        
        # Test with low gas concentration (should fail)
        df = self.create_test_data(temp_value=55.0, humidity_value=65.0, gas_value=10.0)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == False, f"Expected FAIL with gas=10ppm, got PASS"
        assert result.status == 'FAIL', f"Expected status=FAIL, got {result.status}"
        assert "EtO gas concentration not adequately maintained" in " ".join(result.reasons)
    
    def test_no_indeterminate_status(self):
        """Test that we never return INDETERMINATE - only PASS or FAIL."""
        # Test various failing conditions
        test_cases = [
            {"temp": 45.0, "humidity": 65.0, "gas": 500.0},  # Temp too low
            {"temp": 65.0, "humidity": 65.0, "gas": 500.0},  # Temp too high
            {"temp": 55.0, "humidity": 35.0, "gas": 500.0},  # Humidity too low
            {"temp": 55.0, "humidity": 95.0, "gas": 500.0},  # Humidity too high
            {"temp": 55.0, "humidity": 65.0, "gas": 10.0},   # Gas too low
            {"temp": 55.0, "humidity": None, "gas": 500.0},  # No humidity data
            {"temp": 55.0, "humidity": 65.0, "gas": None},   # No gas data
        ]
        
        for i, case in enumerate(test_cases):
            df = self.create_test_data(
                temp_value=case["temp"], 
                humidity_value=case["humidity"], 
                gas_value=case["gas"]
            )
            spec = SpecV1(**self.get_base_spec())
            result = validate_eto_sterilization(df, spec)
            
            assert result.status in ['PASS', 'FAIL'], f"Test case {i}: Got status={result.status}, expected PASS or FAIL"
            assert result.status != 'INDETERMINATE', f"Test case {i}: Should never return INDETERMINATE status"
    
    def test_short_duration_fail(self):
        """Test that insufficient sterilization time results in FAIL."""
        # Test with only 1 hour (less than 2-hour minimum)
        df = self.create_test_data(temp_value=55.0, humidity_value=65.0, gas_value=500.0, duration_hours=1)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == False, f"Expected FAIL for 1-hour duration, got PASS"
        assert result.status == 'FAIL', f"Expected status=FAIL, got {result.status}"
        assert "minimum requirement" in " ".join(result.reasons)
    
    def test_all_conditions_met_pass(self):
        """Test that when all conditions are met, result is PASS."""
        # Perfect conditions: temp 55°C, humidity 65% RH, gas 500ppm, 3 hours
        df = self.create_test_data(temp_value=55.0, humidity_value=65.0, gas_value=500.0, duration_hours=3)
        spec = SpecV1(**self.get_base_spec())
        result = validate_eto_sterilization(df, spec)
        
        assert result.pass_ == True, f"Expected PASS when all conditions met, got FAIL. Reasons: {result.reasons}"
        assert result.status == 'PASS', f"Expected status=PASS, got {result.status}"
        assert "sterilization requirements met" in " ".join(result.reasons)
        assert "Temperature maintained" in " ".join(result.reasons)


if __name__ == "__main__":
    # Simple test runner if pytest not available
    test_class = TestSterileFix()
    
    try:
        print("Testing temperature window pass cases...")
        test_class.test_temperature_window_pass_50_60C()
        print("✓ Temperature window pass tests passed")
        
        print("Testing temperature window fail cases...")
        test_class.test_temperature_window_fail_outside_50_60C()
        print("✓ Temperature window fail tests passed")
        
        print("Testing humidity window pass cases...")
        test_class.test_humidity_window_pass_45_85_RH()
        print("✓ Humidity window pass tests passed")
        
        print("Testing humidity window fail cases...")
        test_class.test_humidity_window_fail_outside_45_85_RH()
        print("✓ Humidity window fail tests passed")
        
        print("Testing gas concentration validation...")
        test_class.test_gas_concentration_validation()
        print("✓ Gas concentration tests passed")
        
        print("Testing no INDETERMINATE status...")
        test_class.test_no_indeterminate_status()
        print("✓ No INDETERMINATE status tests passed")
        
        print("Testing short duration fail...")
        test_class.test_short_duration_fail()
        print("✓ Short duration fail tests passed")
        
        print("Testing all conditions met pass...")
        test_class.test_all_conditions_met_pass()
        print("✓ All conditions met tests passed")
        
        print("\n🎉 All sterile fix tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()