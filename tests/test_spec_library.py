"""
Test suite for industry specification library.

This module validates all industry presets for JSON schema compliance,
Pydantic model validation, and industry-specific constraints.

Example usage:
    pytest tests/test_spec_library.py -v
"""

import json
import pytest
from pathlib import Path
from typing import Dict, Any

from core.models import SpecV1, Industry


class TestSpecLibrary:
    """Test suite for industry specification presets."""
    
    @pytest.fixture
    def base_dir(self) -> Path:
        """Get the base directory of the project."""
        return Path(__file__).parent.parent
    
    @pytest.fixture
    def spec_library_dir(self, base_dir: Path) -> Path:
        """Get the spec library directory."""
        return base_dir / "core" / "spec_library"
    
    @pytest.fixture
    def industry_presets(self, base_dir: Path, spec_library_dir: Path) -> Dict[str, Dict[str, Any]]:
        """Load all industry presets for testing."""
        presets = {}
        
        # Available preset files
        preset_files = {
            "powder": "powder_coat_cure_spec_standard_180c_10min.json",  # Use existing example
            "haccp": "haccp_v1.json",
            "autoclave": "autoclave_v1.json", 
            "sterile": "sterile_v1.json",
            "concrete": "concrete_v1.json",
            "coldchain": "coldchain_v1.json"
        }
        
        for industry, filename in preset_files.items():
            if industry == "powder":
                # Use existing example file
                preset_path = base_dir / "examples" / filename
            else:
                preset_path = spec_library_dir / filename
                
            if preset_path.exists():
                with open(preset_path, 'r') as f:
                    preset_data = json.load(f)
                presets[industry] = preset_data
                
        return presets
    
    def test_spec_library_directory_exists(self, spec_library_dir: Path):
        """Test that the spec library directory exists."""
        assert spec_library_dir.exists(), "Spec library directory should exist"
        assert spec_library_dir.is_dir(), "Spec library should be a directory"
    
    def test_all_preset_files_exist(self, base_dir: Path, spec_library_dir: Path):
        """Test that all expected preset files exist."""
        preset_files = {
            "powder": base_dir / "examples" / "powder_coat_cure_spec_standard_180c_10min.json",
            "haccp": spec_library_dir / "haccp_v1.json",
            "autoclave": spec_library_dir / "autoclave_v1.json",
            "sterile": spec_library_dir / "sterile_v1.json",
            "concrete": spec_library_dir / "concrete_v1.json",
            "coldchain": spec_library_dir / "coldchain_v1.json"
        }
        
        for industry, file_path in preset_files.items():
            assert file_path.exists(), f"{industry} preset file should exist at {file_path}"
    
    @pytest.mark.parametrize("industry", ["haccp", "autoclave", "sterile", "concrete", "coldchain"])
    def test_preset_json_validity(self, industry: str, industry_presets: Dict[str, Dict[str, Any]]):
        """Test that each preset contains valid JSON."""
        assert industry in industry_presets, f"{industry} preset should be loaded"
        
        preset_data = industry_presets[industry]
        assert isinstance(preset_data, dict), f"{industry} preset should be a dictionary"
        assert len(preset_data) > 0, f"{industry} preset should not be empty"
    
    @pytest.mark.parametrize("industry", ["haccp", "autoclave", "sterile", "concrete", "coldchain"])
    def test_preset_pydantic_validation(self, industry: str, industry_presets: Dict[str, Dict[str, Any]]):
        """Test that each preset validates against the SpecV1 Pydantic model."""
        preset_data = industry_presets[industry]
        
        # Should not raise validation errors
        spec = SpecV1(**preset_data)
        
        # Verify basic fields
        assert spec.version == "1.0"
        assert spec.industry == industry
        assert spec.job.job_id is not None
        assert len(spec.job.job_id) > 0
        
        # Verify spec section
        assert spec.spec.target_temp_C > 0
        assert spec.spec.hold_time_s > 0
        assert spec.spec.sensor_uncertainty_C >= 0
        
        # Verify data requirements
        assert spec.data_requirements.max_sample_period_s > 0
        assert spec.data_requirements.allowed_gaps_s >= 0
    
    @pytest.mark.parametrize("industry", ["haccp", "autoclave", "sterile", "concrete", "coldchain"])
    def test_preset_industry_specific_validation(self, industry: str, industry_presets: Dict[str, Dict[str, Any]]):
        """Test industry-specific validation rules."""
        preset_data = industry_presets[industry]
        spec = SpecV1(**preset_data)
        
        if industry == "haccp":
            # HACCP should use OVEN_AIR method for food safety monitoring
            assert spec.spec.method == "OVEN_AIR"
            # Should have reasonable cooling temperatures (typically 57°C max for 135°F)
            assert spec.spec.target_temp_C <= 60.0
            # Should allow cumulative hold logic for cooling validation
            if spec.logic:
                assert spec.logic.continuous == False
        
        elif industry == "autoclave":
            # Autoclave should use OVEN_AIR for steam monitoring
            assert spec.spec.method == "OVEN_AIR"
            # Should have sterilization temperatures around 121°C
            assert 120.0 <= spec.spec.target_temp_C <= 125.0
            # Should require continuous hold for sterilization
            if spec.logic:
                assert spec.logic.continuous == True
        
        elif industry == "sterile":
            # EtO sterilization should use OVEN_AIR
            assert spec.spec.method == "OVEN_AIR"
            # EtO temperatures typically 50-60°C
            assert 45.0 <= spec.spec.target_temp_C <= 65.0
            # Should require continuous hold
            if spec.logic:
                assert spec.logic.continuous == True
        
        elif industry == "concrete":
            # Concrete curing should use OVEN_AIR for ambient monitoring
            assert spec.spec.method == "OVEN_AIR"
            # ASTM C31 specifies 16-27°C range
            assert 16.0 <= spec.spec.target_temp_C <= 27.0
            # Should require continuous hold for proper curing
            if spec.logic:
                assert spec.logic.continuous == True
        
        elif industry == "coldchain":
            # Cold chain should use OVEN_AIR for ambient monitoring
            assert spec.spec.method == "OVEN_AIR"
            # USP <797> specifies 2-8°C range
            assert 2.0 <= spec.spec.target_temp_C <= 8.0
            # May allow brief excursions (cumulative)
            if spec.logic:
                assert spec.logic.continuous == False
    
    def test_preset_required_fields(self, industry_presets: Dict[str, Dict[str, Any]]):
        """Test that all presets contain required fields."""
        required_fields = ["version", "industry", "job", "spec", "data_requirements"]
        
        for industry, preset_data in industry_presets.items():
            if industry == "powder":
                # Powder preset might not have industry field in existing example
                continue
                
            for field in required_fields:
                assert field in preset_data, f"{industry} preset missing required field: {field}"
    
    def test_preset_job_ids_are_unique(self, industry_presets: Dict[str, Dict[str, Any]]):
        """Test that all presets have unique job IDs."""
        job_ids = []
        
        for industry, preset_data in industry_presets.items():
            job_id = preset_data["job"]["job_id"]
            assert job_id not in job_ids, f"Duplicate job ID found: {job_id} in {industry}"
            job_ids.append(job_id)
    
    def test_preset_temperature_units_consistency(self, industry_presets: Dict[str, Dict[str, Any]]):
        """Test temperature units consistency in presets."""
        for industry, preset_data in industry_presets.items():
            if industry == "powder":
                continue  # Skip existing example that might have different format
                
            spec = SpecV1(**preset_data)
            
            # If reporting units are specified, they should be consistent
            if spec.reporting and spec.reporting.units:
                units = spec.reporting.units
                assert units in ["C", "F"], f"{industry} preset has invalid units: {units}"
                
                # HACCP might use Fahrenheit, others typically Celsius
                if industry == "haccp":
                    # HACCP can use either, but if Fahrenheit, temperatures should be higher
                    if units == "F":
                        assert spec.spec.target_temp_C < 100, "Temperature should be in Celsius internally"
                else:
                    # Other industries typically use Celsius
                    assert units == "C", f"{industry} should typically use Celsius units"
    
    def test_preset_sensor_selection_validity(self, industry_presets: Dict[str, Dict[str, Any]]):
        """Test sensor selection configuration validity."""
        for industry, preset_data in industry_presets.items():
            if industry == "powder":
                continue
                
            spec = SpecV1(**preset_data)
            
            if spec.sensor_selection:
                # Mode should be valid
                assert spec.sensor_selection.mode in ["min_of_set", "mean_of_set", "majority_over_threshold"]
                
                # require_at_least should be reasonable
                if spec.sensor_selection.require_at_least:
                    assert spec.sensor_selection.require_at_least >= 1
                    assert spec.sensor_selection.require_at_least <= 10  # Reasonable upper bound
    
    def test_preset_preconditions_validity(self, industry_presets: Dict[str, Dict[str, Any]]):
        """Test preconditions configuration validity."""
        for industry, preset_data in industry_presets.items():
            if industry == "powder":
                continue
                
            spec = SpecV1(**preset_data)
            
            if spec.preconditions:
                # Ramp rate should be positive if specified
                if spec.preconditions.max_ramp_rate_C_per_min:
                    assert spec.preconditions.max_ramp_rate_C_per_min > 0
                
                # Time to threshold should be reasonable
                if spec.preconditions.max_time_to_threshold_s:
                    assert spec.preconditions.max_time_to_threshold_s > 0
                    assert spec.preconditions.max_time_to_threshold_s <= 86400  # Max 24 hours
    
    def test_all_industries_enum_covered(self, industry_presets: Dict[str, Dict[str, Any]]):
        """Test that all Industry enum values have corresponding presets.""" 
        industry_enum_values = [industry.value for industry in Industry]
        
        for industry_value in industry_enum_values:
            # We expect to have presets for all industries
            # (powder uses existing example, others use new preset files)
            preset_exists = (
                industry_value in industry_presets or 
                industry_value == "powder"  # Special case for existing example
            )
            assert preset_exists, f"Missing preset for industry: {industry_value}"


class TestPresetIntegration:
    """Integration tests for preset functionality."""
    
    def test_preset_model_serialization(self):
        """Test that presets can be serialized and deserialized."""
        from core.models import SpecV1
        
        # Test with a simple preset
        preset_data = {
            "version": "1.0",
            "industry": "haccp",
            "job": {"job_id": "test_haccp_001"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 57.22,
                "hold_time_s": 7200,
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,
                "allowed_gaps_s": 120.0
            }
        }
        
        # Should validate successfully
        spec = SpecV1(**preset_data)
        
        # Should serialize back to dict
        serialized = spec.model_dump()
        assert serialized["industry"] == "haccp"
        assert serialized["version"] == "1.0"
        
        # Should be able to recreate from serialized data
        spec2 = SpecV1(**serialized)
        assert spec2.industry == spec.industry
        assert spec2.spec.target_temp_C == spec.spec.target_temp_C
    
    def test_preset_validation_errors(self):
        """Test that invalid presets raise appropriate validation errors."""
        from core.models import SpecV1
        from pydantic import ValidationError
        
        # Test invalid industry
        with pytest.raises(ValidationError):
            SpecV1(
                version="1.0",
                industry="invalid_industry",
                job={"job_id": "test"},
                spec={"method": "PMT", "target_temp_C": 180.0, "hold_time_s": 600},
                data_requirements={"max_sample_period_s": 30.0, "allowed_gaps_s": 60.0}
            )
        
        # Test invalid method for non-powder industry
        with pytest.raises(ValidationError, match="requires OVEN_AIR method"):
            SpecV1(
                version="1.0",
                industry="haccp",
                job={"job_id": "test"},
                spec={"method": "PMT", "target_temp_C": 57.0, "hold_time_s": 7200},
                data_requirements={"max_sample_period_s": 60.0, "allowed_gaps_s": 120.0}
            )