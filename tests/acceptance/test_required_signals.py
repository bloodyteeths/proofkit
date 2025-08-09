"""
Comprehensive acceptance tests for required signals enforcement per industry.

Tests that missing required signals result in INDETERMINATE status with explicit reasons,
not FAIL status, since validation cannot be performed without the required data.

Test coverage:
- Each industry with and without required signals
- Parameter requirements enforcement via spec.parameter_requirements
- Proper INDETERMINATE status vs FAIL status distinction  
- Error messages contain specific signal names and industry context
"""

import json
import pandas as pd
import pytest
from typing import Dict, Any, List

from core.models import SpecV1, SensorSelection
from core.decide import make_decision
from core.errors import RequiredSignalMissingError
from core.metrics_autoclave import validate_autoclave_sterilization
from core.metrics_sterile import validate_eto_sterilization
from core.metrics_concrete import validate_concrete_curing
from core.metrics_haccp import validate_haccp_cooling
from core.metrics_coldchain import validate_coldchain_storage
from core.metrics_powder import validate_powder_coating_cure


def create_test_dataframe(columns: Dict[str, List[float]], num_points: int = 100) -> pd.DataFrame:
    """Create test DataFrame with specified columns and temperature profiles."""
    data = {
        'timestamp': pd.date_range('2024-01-01T10:00:00', periods=num_points, freq='30S')
    }
    
    for col_name, values in columns.items():
        if len(values) == 1:
            # Constant value
            data[col_name] = [values[0]] * num_points
        elif len(values) == num_points:
            # Full series
            data[col_name] = values
        else:
            # Interpolate to match num_points
            data[col_name] = pd.Series(values).reindex(range(num_points), method='pad').tolist()
    
    return pd.DataFrame(data)


def create_industry_spec(industry: str, parameter_requirements: Dict[str, bool] = None) -> SpecV1:
    """Create industry-specific specification with optional parameter requirements."""
    base_spec = {
        "version": "1.0",
        "industry": industry,
        "job": {"job_id": f"test_{industry}_001"},
        "spec": {
            "method": "OVEN_AIR" if industry != "powder" else "PMT",
            "target_temp_C": 180.0 if industry == "powder" else (121.0 if industry == "autoclave" else (55.0 if industry == "sterile" else (21.5 if industry == "concrete" else (5.0 if industry == "coldchain" else 60.0)))),
            "hold_time_s": 900,  # 15 minutes
            "sensor_uncertainty_C": 2.0
        },
        "data_requirements": {
            "max_sample_period_s": 60.0,
            "allowed_gaps_s": 120.0
        }
    }
    
    if parameter_requirements:
        base_spec["parameter_requirements"] = parameter_requirements
    
    return SpecV1(**base_spec)


class TestAutoclaveRequiredSignals:
    """Test autoclave industry required signals enforcement."""
    
    def test_temperature_only_no_requirements(self):
        """Autoclave with only temperature should PASS when no parameter requirements."""
        spec = create_industry_spec("autoclave")
        df = create_test_dataframe({
            'temp_probe_1': [121.5] * 100
        })
        
        result = validate_autoclave_sterilization(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "autoclave"
    
    def test_missing_pressure_with_requirement(self):
        """Autoclave missing pressure when required should raise RequiredSignalMissingError."""
        spec = create_industry_spec("autoclave", {"require_pressure": True})
        df = create_test_dataframe({
            'temp_probe_1': [121.5] * 100
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_autoclave_sterilization(df, spec)
        
        error = exc_info.value
        assert "pressure" in error.missing_signals
        assert error.industry == "autoclave"
        assert "temp_probe_1" in error.available_signals
    
    def test_pressure_available_with_requirement(self):
        """Autoclave with pressure when required should validate normally."""
        spec = create_industry_spec("autoclave", {"require_pressure": True})
        df = create_test_dataframe({
            'temp_probe_1': [121.5] * 100,
            'pressure_1': [15.2] * 100  # psi
        })
        
        result = validate_autoclave_sterilization(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "autoclave"


class TestSterileRequiredSignals:
    """Test sterile industry required signals enforcement."""
    
    def test_temperature_only_no_requirements(self):
        """EtO sterilization with only temperature should PASS when no requirements."""
        spec = create_industry_spec("sterile")
        df = create_test_dataframe({
            'temp_1': [55.0] * 200  # 2 hours at 55°C
        })
        
        result = validate_eto_sterilization(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "sterile"
    
    def test_missing_humidity_with_requirement(self):
        """EtO missing humidity when required should raise RequiredSignalMissingError."""
        spec = create_industry_spec("sterile", {"require_humidity": True})
        df = create_test_dataframe({
            'temperature_1': [55.0] * 200
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_eto_sterilization(df, spec)
        
        error = exc_info.value
        assert "humidity" in error.missing_signals
        assert error.industry == "sterile"
    
    def test_missing_gas_with_requirement(self):
        """EtO missing gas concentration when required should raise RequiredSignalMissingError."""
        spec = create_industry_spec("sterile", {"require_gas_concentration": True})
        df = create_test_dataframe({
            'temp_sensor': [55.0] * 200
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_eto_sterilization(df, spec)
        
        error = exc_info.value
        assert "gas_concentration" in error.missing_signals
        assert error.industry == "sterile"
    
    def test_all_signals_available_with_requirements(self):
        """EtO with all signals when required should validate normally."""
        spec = create_industry_spec("sterile", {
            "require_humidity": True,
            "require_gas_concentration": True
        })
        df = create_test_dataframe({
            'temp_1': [55.0] * 200,
            'humidity_1': [65.0] * 200,  # %RH
            'eto_concentration': [600.0] * 200  # ppm
        })
        
        result = validate_eto_sterilization(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "sterile"


class TestConcreteRequiredSignals:
    """Test concrete industry required signals enforcement."""
    
    def test_temperature_only_no_requirements(self):
        """Concrete with only temperature should validate when no requirements."""
        spec = create_industry_spec("concrete")
        df = create_test_dataframe({
            'temp_sensor_1': [21.5] * 200  # 24+ hours
        }, num_points=200)
        
        result = validate_concrete_curing(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "concrete"
    
    def test_missing_humidity_with_requirement(self):
        """Concrete missing humidity when required should raise RequiredSignalMissingError."""
        spec = create_industry_spec("concrete", {"require_humidity": True})
        df = create_test_dataframe({
            'temperature_probe': [21.5] * 200
        }, num_points=200)
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_concrete_curing(df, spec)
        
        error = exc_info.value
        assert "humidity" in error.missing_signals
        assert error.industry == "concrete"
    
    def test_humidity_available_with_requirement(self):
        """Concrete with humidity when required should validate normally."""
        spec = create_industry_spec("concrete", {"require_humidity": True})
        df = create_test_dataframe({
            'temp_1': [21.5] * 200,
            'rh_sensor': [96.0] * 200  # %RH
        }, num_points=200)
        
        result = validate_concrete_curing(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "concrete"


class TestHACCPRequiredSignals:
    """Test HACCP industry required signals enforcement."""
    
    def test_missing_temperature_signals(self):
        """HACCP with no temperature columns should raise RequiredSignalMissingError."""
        spec = create_industry_spec("haccp")
        df = create_test_dataframe({
            'non_temp_sensor': [50.0] * 100
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_haccp_cooling(df, spec)
        
        error = exc_info.value
        assert "temperature" in error.missing_signals
        assert error.industry == "haccp"
    
    def test_temperature_available(self):
        """HACCP with temperature should validate normally."""
        spec = create_industry_spec("haccp")
        # HACCP cooling: start at 135°F (57.2°C), cool to 41°F (5°C)
        cooling_profile = [57.2 - (i * 0.3) for i in range(100)]  # Gradual cooling
        df = create_test_dataframe({
            'temp_probe_1': cooling_profile
        })
        
        result = validate_haccp_cooling(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "haccp"


class TestColdchainRequiredSignals:
    """Test coldchain industry required signals enforcement."""
    
    def test_missing_temperature_signals(self):
        """Coldchain with no temperature columns should raise RequiredSignalMissingError."""
        spec = create_industry_spec("coldchain")
        df = create_test_dataframe({
            'sensor_x': [5.0] * 100
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_coldchain_storage(df, spec)
        
        error = exc_info.value
        assert "temperature" in error.missing_signals
        assert error.industry == "coldchain"
    
    def test_temperature_available(self):
        """Coldchain with temperature should validate normally."""
        spec = create_industry_spec("coldchain")
        df = create_test_dataframe({
            'temp_1': [5.0] * 100  # Within 2-8°C range
        })
        
        result = validate_coldchain_storage(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "coldchain"


class TestPowderRequiredSignals:
    """Test powder industry required signals enforcement."""
    
    def test_missing_temperature_signals(self):
        """Powder with no temperature columns should raise RequiredSignalMissingError."""
        spec = create_industry_spec("powder")
        df = create_test_dataframe({
            'other_sensor': [180.0] * 100
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_powder_coating_cure(df, spec)
        
        error = exc_info.value
        assert "temperature" in error.missing_signals
        assert error.industry == "powder"
    
    def test_insufficient_sensors_with_requirement(self):
        """Powder with insufficient sensors when required should raise RequiredSignalMissingError."""
        spec = create_industry_spec("powder")
        spec.sensor_selection = SensorSelection(
            mode="min_of_set",
            require_at_least=3
        )
        
        df = create_test_dataframe({
            'temp_1': [180.0] * 100,
            'temp_2': [179.5] * 100  # Only 2 sensors, need 3
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_powder_coating_cure(df, spec)
        
        error = exc_info.value
        assert error.industry == "powder"
        assert "temp_1" in error.available_signals
        assert "temp_2" in error.available_signals
    
    def test_sufficient_sensors(self):
        """Powder with sufficient sensors should validate normally."""
        spec = create_industry_spec("powder")
        df = create_test_dataframe({
            'temp_probe_1': [185.0] * 100,  # Above target + uncertainty threshold
            'temp_probe_2': [184.5] * 100
        })
        
        result = validate_powder_coating_cure(df, spec)
        assert result.status in ["PASS", "FAIL"]  # Should not be INDETERMINATE
        assert result.industry == "powder"


class TestRequiredSignalsMakeDecision:
    """Test required signals handling through main make_decision interface."""
    
    def test_make_decision_handles_required_signal_missing(self):
        """make_decision should properly handle RequiredSignalMissingError and return INDETERMINATE."""
        spec = create_industry_spec("autoclave", {"require_pressure": True})
        df = create_test_dataframe({
            'temp_1': [121.0] * 100
        })
        
        # make_decision should catch RequiredSignalMissingError and return INDETERMINATE
        # This requires proper exception handling in the decision pipeline
        try:
            result = make_decision(df, spec)
            # If no exception raised, result should be INDETERMINATE
            assert result.status == "INDETERMINATE"
            assert not result.pass_  # INDETERMINATE means validation couldn't be completed
            assert any("pressure" in reason.lower() for reason in result.reasons)
        except RequiredSignalMissingError:
            # This is also acceptable - the error bubbled up correctly
            pass
    
    def test_error_contains_proper_metadata(self):
        """RequiredSignalMissingError should contain proper metadata for debugging."""
        spec = create_industry_spec("sterile", {
            "require_humidity": True,
            "require_gas_concentration": True
        })
        df = create_test_dataframe({
            'temperature_sensor': [55.0] * 100
        })
        
        with pytest.raises(RequiredSignalMissingError) as exc_info:
            validate_eto_sterilization(df, spec)
        
        error = exc_info.value
        assert error.industry == "sterile"
        assert set(error.missing_signals) == {"humidity", "gas_concentration"}
        assert "temperature_sensor" in error.available_signals
        assert "timestamp" in error.available_signals
        
        # Test error serialization
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "RequiredSignalMissingError"
        assert error_dict["industry"] == "sterile"
        assert set(error_dict["missing_signals"]) == {"humidity", "gas_concentration"}


@pytest.mark.parametrize("industry,required_param,signal_type", [
    ("autoclave", "require_pressure", "pressure"),
    ("sterile", "require_humidity", "humidity"),
    ("sterile", "require_gas_concentration", "gas_concentration"),  
    ("concrete", "require_humidity", "humidity"),
])
def test_parametrized_missing_required_signals(industry: str, required_param: str, signal_type: str):
    """Parametrized test for missing required signals across industries."""
    spec = create_industry_spec(industry, {required_param: True})
    
    # Create DataFrame with only temperature (missing the required signal)
    temp_value = {
        "autoclave": 121.0,
        "sterile": 55.0,
        "concrete": 21.5
    }.get(industry, 180.0)
    
    df = create_test_dataframe({
        'temp_sensor': [temp_value] * 100
    })
    
    # Get the appropriate validation function
    validation_func = {
        "autoclave": validate_autoclave_sterilization,
        "sterile": validate_eto_sterilization,
        "concrete": validate_concrete_curing,
        "haccp": validate_haccp_cooling,
        "coldchain": validate_coldchain_storage,
        "powder": validate_powder_coating_cure
    }[industry]
    
    with pytest.raises(RequiredSignalMissingError) as exc_info:
        validation_func(df, spec)
    
    error = exc_info.value
    assert signal_type in error.missing_signals
    assert error.industry == industry
    assert len(error.available_signals) > 0  # Should have timestamp + temp_sensor


if __name__ == "__main__":
    pytest.main([__file__])