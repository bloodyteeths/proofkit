"""
Tests for schema alias coercion to maintain backward compatibility.

Tests that legacy method and sensor mode values are properly coerced
to current enum values without breaking existing specifications.
"""

import pytest
from core.models import SpecV1, CureMethod, SensorMode, CureSpec, SensorSelection


class TestCureMethodAliases:
    """Test cure method alias coercion."""
    
    def test_refrigeration_alias_coerced_to_oven_air(self):
        """REFRIGERATION should be coerced to OVEN_AIR."""
        spec_data = {
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "test_001"},
            "spec": {
                "method": "REFRIGERATION",  # Legacy alias
                "target_temp_C": 4.0,
                "hold_time_s": 3600
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.spec.method == CureMethod.OVEN_AIR
        assert spec.spec.method.value == "OVEN_AIR"
    
    def test_ambient_cure_alias_coerced_to_oven_air(self):
        """AMBIENT_CURE should be coerced to OVEN_AIR."""
        spec_data = {
            "version": "1.0", 
            "industry": "concrete",
            "job": {"job_id": "test_002"},
            "spec": {
                "method": "AMBIENT_CURE",  # Legacy alias
                "target_temp_C": 20.0,
                "hold_time_s": 86400
            },
            "data_requirements": {
                "max_sample_period_s": 300.0,
                "allowed_gaps_s": 600.0
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.spec.method == CureMethod.OVEN_AIR
        assert spec.spec.method.value == "OVEN_AIR"
    
    def test_eto_sterilization_alias_coerced_to_oven_air(self):
        """ETO_STERILIZATION should be coerced to OVEN_AIR."""
        spec_data = {
            "version": "1.0",
            "industry": "sterile", 
            "job": {"job_id": "test_003"},
            "spec": {
                "method": "ETO_STERILIZATION",  # Legacy alias
                "target_temp_C": 55.0,
                "hold_time_s": 7200
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.spec.method == CureMethod.OVEN_AIR
        assert spec.spec.method.value == "OVEN_AIR"
    
    def test_current_methods_unchanged(self):
        """Current method values should pass through unchanged."""
        # Test PMT
        cure_spec = CureSpec(
            method="PMT",
            target_temp_C=180.0,
            hold_time_s=600
        )
        assert cure_spec.method == CureMethod.PMT
        
        # Test OVEN_AIR
        cure_spec = CureSpec(
            method="OVEN_AIR", 
            target_temp_C=200.0,
            hold_time_s=900
        )
        assert cure_spec.method == CureMethod.OVEN_AIR
    
    def test_invalid_method_still_fails(self):
        """Invalid method values should still raise ValidationError."""
        with pytest.raises(ValueError):
            CureSpec(
                method="INVALID_METHOD",
                target_temp_C=180.0,
                hold_time_s=600
            )


class TestSensorModeAliases:
    """Test sensor mode alias coercion."""
    
    def test_mean_alias_coerced_to_mean_of_set(self):
        """mean should be coerced to mean_of_set."""
        sensor_selection = SensorSelection(
            mode="mean",  # Legacy alias
            sensors=["temp1", "temp2"]
        )
        assert sensor_selection.mode == SensorMode.MEAN_OF_SET
        assert sensor_selection.mode.value == "mean_of_set"
    
    def test_min_alias_coerced_to_min_of_set(self):
        """min should be coerced to min_of_set."""
        sensor_selection = SensorSelection(
            mode="min",  # Legacy alias
            sensors=["temp1", "temp2", "temp3"]
        )
        assert sensor_selection.mode == SensorMode.MIN_OF_SET
        assert sensor_selection.mode.value == "min_of_set"
    
    def test_majority_alias_coerced_to_majority_over_threshold(self):
        """majority should be coerced to majority_over_threshold."""
        sensor_selection = SensorSelection(
            mode="majority",  # Legacy alias
            sensors=["temp1", "temp2", "temp3", "temp4", "temp5"]
        )
        assert sensor_selection.mode == SensorMode.MAJORITY_OVER_THRESHOLD
        assert sensor_selection.mode.value == "majority_over_threshold"
    
    def test_current_modes_unchanged(self):
        """Current mode values should pass through unchanged."""
        # Test min_of_set
        sensor_selection = SensorSelection(
            mode="min_of_set",
            sensors=["temp1", "temp2"]
        )
        assert sensor_selection.mode == SensorMode.MIN_OF_SET
        
        # Test mean_of_set
        sensor_selection = SensorSelection(
            mode="mean_of_set",
            sensors=["temp1", "temp2"]
        )
        assert sensor_selection.mode == SensorMode.MEAN_OF_SET
        
        # Test majority_over_threshold
        sensor_selection = SensorSelection(
            mode="majority_over_threshold",
            sensors=["temp1", "temp2", "temp3"]
        )
        assert sensor_selection.mode == SensorMode.MAJORITY_OVER_THRESHOLD
    
    def test_invalid_mode_still_fails(self):
        """Invalid mode values should still raise ValidationError."""
        with pytest.raises(ValueError):
            SensorSelection(
                mode="invalid_mode",
                sensors=["temp1", "temp2"]
            )


class TestIntegratedAliases:
    """Test aliases working in complete specifications."""
    
    def test_coldchain_with_refrigeration_alias(self):
        """Test complete coldchain spec with REFRIGERATION alias."""
        spec_data = {
            "version": "1.0",
            "industry": "coldchain",
            "job": {"job_id": "cold_001"},
            "spec": {
                "method": "REFRIGERATION",  # Legacy alias -> PMT
                "target_temp_C": 2.0,
                "hold_time_s": 1800
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "mean",  # Legacy alias -> mean_of_set
                "sensors": ["fridge_temp", "ambient_temp"]
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.spec.method == CureMethod.OVEN_AIR
        assert spec.sensor_selection.mode == SensorMode.MEAN_OF_SET
    
    def test_sterile_with_eto_alias(self):
        """Test complete sterile spec with ETO_STERILIZATION alias."""
        spec_data = {
            "version": "1.0",
            "industry": "sterile",
            "job": {"job_id": "sterile_001"},
            "spec": {
                "method": "ETO_STERILIZATION",  # Legacy alias -> OVEN_AIR
                "target_temp_C": 55.0,
                "hold_time_s": 3600
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            },
            "sensor_selection": {
                "mode": "min",  # Legacy alias -> min_of_set
                "sensors": ["chamber_temp1", "chamber_temp2", "chamber_temp3"]
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.spec.method == CureMethod.OVEN_AIR
        assert spec.sensor_selection.mode == SensorMode.MIN_OF_SET
    
    def test_concrete_with_ambient_cure_alias(self):
        """Test complete concrete spec with AMBIENT_CURE alias."""
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "concrete_001"},
            "spec": {
                "method": "AMBIENT_CURE",  # Legacy alias -> PMT
                "target_temp_C": 20.0,
                "hold_time_s": 86400
            },
            "data_requirements": {
                "max_sample_period_s": 300.0,
                "allowed_gaps_s": 600.0
            },
            "sensor_selection": {
                "mode": "majority",  # Legacy alias -> majority_over_threshold
                "sensors": ["temp1", "temp2", "temp3", "temp4", "temp5"]
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.spec.method == CureMethod.OVEN_AIR
        assert spec.sensor_selection.mode == SensorMode.MAJORITY_OVER_THRESHOLD


if __name__ == "__main__":
    pytest.main([__file__])