"""
Models Validation Tests

Tests for core.models to achieve ≥95% coverage.
Focuses on Pydantic validation edge cases, field constraints,
and model relationships.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
import json

from core.models import (
    SpecV1,
    JobInfo,
    DataRequirements,
    SensorSelection,
    CureSpec,
    Logic,
    Reporting,
    SensorMode,
    Industry,
    DecisionResult
)


class TestSpecV1Validation:
    """Test SpecV1 model validation."""
    
    def test_minimal_valid_spec(self):
        """Test minimal valid specification."""
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "test123"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        }
        
        spec = SpecV1(**spec_data)
        assert spec.version == "1.0"
        assert spec.job.job_id == "test123"
        assert spec.spec.target_temp_C == 180.0
    
    def test_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        # Missing version
        with pytest.raises(ValidationError) as exc_info:
            SpecV1(**{
                "job": {"job_id": "test"},
                "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 600, "sensor_uncertainty_C": 2.0}
            })
        assert "version" in str(exc_info.value)
        
        # Missing job
        with pytest.raises(ValidationError) as exc_info:
            SpecV1(**{
                "version": "1.0",
                "spec": {"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 600, "sensor_uncertainty_C": 2.0}
            })
        assert "job" in str(exc_info.value)
        
        # Missing spec
        with pytest.raises(ValidationError) as exc_info:
            SpecV1(**{
                "version": "1.0",
                "job": {"job_id": "test"}
            })
        assert "spec" in str(exc_info.value)
    
    def test_invalid_version_format(self):
        """Test that invalid version format is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SpecV1(**{
                "version": "2.0",  # Only "1.0" is valid
                "job": {"job_id": "test"},
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 180.0,
                    "hold_time_s": 600,
                    "sensor_uncertainty_C": 2.0
                }
            })
        assert "version" in str(exc_info.value)


class TestSpecFieldValidation:
    """Test CureSpec model field validation."""
    
    def test_negative_hold_time(self):
        """Test that negative hold_time_s is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CureSpec(**{
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": -60,  # Negative!
                "sensor_uncertainty_C": 2.0
            })
        assert "hold_time_s" in str(exc_info.value)
        assert "greater than or equal to 0" in str(exc_info.value)
    
    def test_negative_sensor_uncertainty(self):
        """Test that negative sensor_uncertainty_C is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CureSpec(**{
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": -1.0  # Negative!
            })
        assert "sensor_uncertainty_C" in str(exc_info.value)
    
    def test_invalid_hysteresis(self):
        """Test that negative hysteresis_C is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CureSpec(**{
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0,
                "hysteresis_C": -0.5  # Negative!
            })
        assert "hysteresis_C" in str(exc_info.value)
    
    def test_extreme_temperature_values(self):
        """Test extreme but valid temperature values."""
        # Very high temperature
        spec_high = CureSpec(**{
            "method": "Autoclave",
            "target_temp_C": 500.0,  # High but valid
            "hold_time_s": 60,
            "sensor_uncertainty_C": 5.0
        })
        assert spec_high.target_temp_C == 500.0
        
        # Negative temperature (e.g., freezing)
        spec_low = CureSpec(**{
            "method": "ColdChain",
            "target_temp_C": -80.0,  # Low but valid
            "hold_time_s": 3600,
            "sensor_uncertainty_C": 1.0
        })
        assert spec_low.target_temp_C == -80.0
    
    def test_all_optional_fields_populated(self):
        """Test spec with all optional fields."""
        spec = CureSpec(**{
            "method": "PMT",
            "target_temp_C": 180.0,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 2.0,
            "hysteresis_C": 1.5,
            "min_preheat_temp_C": 150.0,
            "max_ramp_rate_C_per_min": 10.0,
            "max_time_to_threshold_s": 900,
            "industry": "powder"
        })
        
        assert spec.hysteresis_C == 1.5
        assert spec.min_preheat_temp_C == 150.0
        assert spec.max_ramp_rate_C_per_min == 10.0
        assert spec.max_time_to_threshold_s == 900
        assert spec.industry == Industry.POWDER


class TestSensorSelectionValidation:
    """Test SensorSelection model validation."""
    
    def test_mode_sensors_mismatch(self):
        """Test mismatch between mode and require_at_least."""
        # require_at_least > number of sensors
        with pytest.raises(ValidationError) as exc_info:
            SensorSelection(**{
                "mode": "majority_over_threshold",
                "sensors": ["temp1", "temp2"],  # Only 2 sensors
                "require_at_least": 3  # But require 3!
            })
        assert "require_at_least cannot exceed" in str(exc_info.value)
    
    def test_invalid_sensor_mode(self):
        """Test invalid sensor mode."""
        with pytest.raises(ValidationError) as exc_info:
            SensorSelection(**{
                "mode": "invalid_mode",
                "sensors": ["temp1"],
                "require_at_least": 1
            })
        assert "Input should be" in str(exc_info.value)
    
    def test_empty_sensors_list(self):
        """Test that empty sensors list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SensorSelection(**{
                "mode": "min_of_set",
                "sensors": [],  # Empty!
                "require_at_least": 1
            })
        assert "List should have at least 1 item" in str(exc_info.value)
    
    def test_require_at_least_zero(self):
        """Test that require_at_least must be positive."""
        with pytest.raises(ValidationError) as exc_info:
            SensorSelection(**{
                "mode": "mean_of_set",
                "sensors": ["temp1", "temp2"],
                "require_at_least": 0  # Must be at least 1
            })
        assert "greater than or equal to 1" in str(exc_info.value)
    
    def test_valid_sensor_selection_all_modes(self):
        """Test valid sensor selection for all modes."""
        # min_of_set
        sel1 = SensorSelection(
            mode=SensorMode.MIN_OF_SET,
            sensors=["s1", "s2", "s3"],
            require_at_least=2
        )
        assert sel1.mode == SensorMode.MIN_OF_SET
        
        # mean_of_set
        sel2 = SensorSelection(
            mode=SensorMode.MEAN_OF_SET,
            sensors=["s1", "s2"],
            require_at_least=2
        )
        assert sel2.mode == SensorMode.MEAN_OF_SET
        
        # majority_over_threshold
        sel3 = SensorSelection(
            mode=SensorMode.MAJORITY_OVER_THRESHOLD,
            sensors=["s1", "s2", "s3", "s4", "s5"],
            require_at_least=3
        )
        assert sel3.mode == SensorMode.MAJORITY_OVER_THRESHOLD


class TestLogicValidation:
    """Test Logic model validation."""
    
    def test_negative_max_total_dips(self):
        """Test that negative max_total_dips_s is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Logic(**{
                "continuous": False,
                "cumulative": True,
                "max_total_dips_s": -10  # Negative!
            })
        assert "max_total_dips_s" in str(exc_info.value)
    
    def test_continuous_cumulative_conflict(self):
        """Test both continuous and cumulative can be set."""
        # This is actually valid - spec allows both
        logic = Logic(
            continuous=True,
            cumulative=True,
            max_total_dips_s=60
        )
        assert logic.continuous is True
        assert logic.cumulative is True
    
    def test_default_logic_values(self):
        """Test default logic values."""
        logic = Logic()
        assert logic.continuous is True  # Default
        assert logic.cumulative is False  # Default
        assert logic.max_total_dips_s == 0  # Default


class TestReportingValidation:
    """Test Reporting model validation."""
    
    def test_invalid_units(self):
        """Test that invalid units are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Reporting(**{
                "units": "X",  # Invalid - only C, F, or K
                "language": "en",
                "timezone": "UTC"
            })
        assert "units" in str(exc_info.value)
    
    def test_invalid_language(self):
        """Test that invalid language codes are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Reporting(**{
                "units": "C",
                "language": "xx",  # Invalid ISO code
                "timezone": "UTC"
            })
        assert "language" in str(exc_info.value)
    
    def test_invalid_timezone(self):
        """Test that invalid timezone is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Reporting(**{
                "units": "C",
                "language": "en",
                "timezone": "Invalid/Timezone"
            })
        assert "timezone" in str(exc_info.value)
    
    def test_valid_reporting_configurations(self):
        """Test various valid reporting configurations."""
        # Fahrenheit with US Eastern time
        r1 = Reporting(
            units="F",
            language="en",
            timezone="America/New_York"
        )
        assert r1.units == "F"
        
        # Kelvin with German
        r2 = Reporting(
            units="K",
            language="de",
            timezone="Europe/Berlin"
        )
        assert r2.language == "de"
        
        # Celsius with Japanese
        r3 = Reporting(
            units="C",
            language="ja",
            timezone="Asia/Tokyo"
        )
        assert r3.timezone == "Asia/Tokyo"


class TestDataRequirementsValidation:
    """Test DataRequirements validation."""
    
    def test_negative_sample_period(self):
        """Test that negative max_sample_period_s is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            DataRequirements(**{
                "max_sample_period_s": -30.0,
                "allowed_gaps_s": 120.0
            })
        assert "greater than 0" in str(exc_info.value)
    
    def test_negative_allowed_gaps(self):
        """Test that negative allowed_gaps_s is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            DataRequirements(**{
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": -60.0
            })
        assert "greater than or equal to 0" in str(exc_info.value)
    
    def test_invalid_min_data_points(self):
        """Test that min_data_points must be at least 2."""
        with pytest.raises(ValidationError) as exc_info:
            DataRequirements(**{
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0,
                "min_data_points": 1  # Too few
            })
        assert "greater than or equal to 2" in str(exc_info.value)
    
    def test_zero_allowed_gaps(self):
        """Test that zero allowed_gaps_s is valid (no gaps allowed)."""
        dr = DataRequirements(
            max_sample_period_s=30.0,
            allowed_gaps_s=0.0  # No gaps allowed
        )
        assert dr.allowed_gaps_s == 0.0


class TestDecisionResultValidation:
    """Test DecisionResult model validation."""
    
    def test_minimal_decision_result(self):
        """Test minimal valid decision result."""
        result = DecisionResult(
            job_id="test123",
            pass_=True,
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            required_hold_time_s=600,
            actual_hold_time_s=650.5,
            max_temp_C=185.0,
            min_temp_C=175.0
        )
        
        assert result.job_id == "test123"
        assert result.pass_ is True
        assert len(result.reasons) == 0  # Default empty list
    
    def test_decision_result_with_all_fields(self):
        """Test decision result with all optional fields."""
        result = DecisionResult(
            job_id="test456",
            pass_=False,
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            required_hold_time_s=600,
            actual_hold_time_s=300.0,
            max_temp_C=181.0,
            min_temp_C=165.0,
            timestamp=datetime.now(timezone.utc),
            reasons=["Temperature below threshold", "Insufficient hold time"],
            time_to_threshold_s=120.5,
            time_above_threshold_s=300.0,
            max_ramp_rate_C_per_min=15.5,
            cumulative_hold_time_s=450.0,
            continuous_hold_time_s=300.0,
            total_dip_time_s=150.0,
            sensor_data={"sensor1": 180.5, "sensor2": 179.8},
            metadata={"operator": "John", "batch": "B123"}
        )
        
        assert result.pass_ is False
        assert len(result.reasons) == 2
        assert result.time_to_threshold_s == 120.5
        assert result.sensor_data["sensor1"] == 180.5
        assert result.metadata["batch"] == "B123"
    
    def test_negative_times_rejected(self):
        """Test that negative time values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            DecisionResult(
                job_id="test",
                pass_=True,
                target_temp_C=180.0,
                conservative_threshold_C=182.0,
                required_hold_time_s=600,
                actual_hold_time_s=-10.0,  # Negative!
                max_temp_C=185.0,
                min_temp_C=175.0
            )
        assert "actual_hold_time_s" in str(exc_info.value)




class TestIndustryEnum:
    """Test Industry enum validation."""
    
    def test_all_industries_valid(self):
        """Test that all industry values are valid."""
        industries = [
            Industry.POWDER,
            Industry.HACCP,
            Industry.AUTOCLAVE,
            Industry.STERILE,
            Industry.CONCRETE,
            Industry.COLDCHAIN
        ]
        
        for industry in industries:
            # Should be able to use in spec
            spec = CureSpec(
                method="Test",
                target_temp_C=100.0,
                hold_time_s=60,
                sensor_uncertainty_C=1.0,
                industry=industry
            )
            assert spec.industry == industry
    
    def test_industry_string_conversion(self):
        """Test industry enum string representation."""
        assert Industry.POWDER.value == "powder"
        assert Industry.HACCP.value == "haccp"
        assert Industry.AUTOCLAVE.value == "autoclave"
        assert Industry.STERILE.value == "sterile"
        assert Industry.CONCRETE.value == "concrete"
        assert Industry.COLDCHAIN.value == "coldchain"


class TestJobInfoValidation:
    """Test JobInfo model validation."""
    
    def test_empty_job_id_rejected(self):
        """Test that empty job_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            JobInfo(job_id="")  # Empty string
        assert "at least 1 character" in str(exc_info.value)
    
    def test_job_info_with_metadata(self):
        """Test JobInfo with optional metadata."""
        job = JobInfo(
            job_id="BATCH-2024-001",
            customer_id="CUST123",
            batch_number="B20240115",
            operator_name="Jane Smith",
            equipment_id="OVEN-03",
            metadata={
                "shift": "day",
                "location": "Plant A",
                "product_code": "PC-180"
            }
        )
        
        assert job.job_id == "BATCH-2024-001"
        assert job.customer_id == "CUST123"
        assert job.operator_name == "Jane Smith"
        assert job.metadata["shift"] == "day"


class TestComplexSpecScenarios:
    """Test complex specification scenarios."""
    
    def test_spec_with_conflicting_requirements(self):
        """Test spec with potentially conflicting requirements."""
        # This should still validate - runtime will handle conflicts
        spec_data = {
            "version": "1.0",
            "job": {"job_id": "conflict_test"},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600,
                "sensor_uncertainty_C": 2.0,
                "max_time_to_threshold_s": 60,  # Very short
                "max_ramp_rate_C_per_min": 1.0  # Very slow
                # These conflict - can't reach 180°C in 60s at 1°C/min
            }
        }
        
        # Should still create valid spec - runtime handles logic
        spec = SpecV1(**spec_data)
        assert spec.spec.max_time_to_threshold_s == 60
        assert spec.spec.max_ramp_rate_C_per_min == 1.0
    
    def test_spec_version_industry_combinations(self):
        """Test various spec version and industry combinations."""
        # Version 1.0 with all industries
        for industry in ["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"]:
            spec_data = {
                "version": "1.0",
                "job": {"job_id": f"test_{industry}"},
                "spec": {
                    "method": industry.upper(),
                    "target_temp_C": 100.0,
                    "hold_time_s": 60,
                    "sensor_uncertainty_C": 1.0,
                    "industry": industry
                }
            }
            
            spec = SpecV1(**spec_data)
            assert spec.spec.industry.value == industry


class TestModelSerialization:
    """Test model serialization/deserialization."""
    
    def test_spec_json_round_trip(self):
        """Test spec can be serialized to JSON and back."""
        original_spec = SpecV1(
            version="1.0",
            job=JobInfo(job_id="json_test", customer_id="C123"),
            spec=CureSpec(
                method="PMT",
                target_temp_C=180.0,
                hold_time_s=600,
                sensor_uncertainty_C=2.0,
                industry=Industry.POWDER
            ),
            data_requirements=DataRequirements(
                max_sample_period_s=30.0,
                allowed_gaps_s=60.0
            )
        )
        
        # Serialize to JSON
        json_str = original_spec.model_dump_json(indent=2)
        
        # Parse back
        parsed_data = json.loads(json_str)
        reconstructed_spec = SpecV1(**parsed_data)
        
        # Verify equality
        assert reconstructed_spec.version == original_spec.version
        assert reconstructed_spec.job.job_id == original_spec.job.job_id
        assert reconstructed_spec.spec.target_temp_C == original_spec.spec.target_temp_C
        assert reconstructed_spec.spec.industry == original_spec.spec.industry
    
    def test_decision_result_json_serialization(self):
        """Test DecisionResult JSON serialization."""
        result = DecisionResult(
            job_id="serialize_test",
            pass_=True,
            target_temp_C=180.0,
            conservative_threshold_C=182.0,
            required_hold_time_s=600,
            actual_hold_time_s=650.0,
            max_temp_C=185.0,
            min_temp_C=175.0,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            reasons=["All requirements met"],
            sensor_data={"sensor1": 182.5}
        )
        
        # Serialize
        json_str = result.model_dump_json()
        
        # Parse back
        parsed = json.loads(json_str)
        reconstructed = DecisionResult(**parsed)
        
        assert reconstructed.job_id == result.job_id
        assert reconstructed.pass_ == result.pass_
        assert reconstructed.timestamp == result.timestamp