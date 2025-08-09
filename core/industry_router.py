"""Industry routing and specification adaptation."""

from typing import Dict, Any, Callable, Optional
from core.decide import make_decision
from core.metrics_powder import validate_powder_coating_cure
from core.metrics_autoclave import validate_autoclave_sterilization
from core.metrics_coldchain import validate_coldchain_storage
from core.metrics_haccp import validate_haccp_cooling
from core.metrics_concrete import validate_concrete_curing
from core.metrics_sterile import validate_sterile_environment

def select_engine(industry: str) -> Callable:
    """Select appropriate analysis engine for industry."""
    engines = {
        "powder": validate_powder_coating_cure,
        "powder-coating": validate_powder_coating_cure,  # Alias for powder
        "autoclave": validate_autoclave_sterilization,
        "coldchain": validate_coldchain_storage,
        "cold-chain": validate_coldchain_storage,
        "haccp": validate_haccp_cooling,
        "concrete": validate_concrete_curing,
        "sterile": validate_sterile_environment,
        "eto": validate_sterile_environment,
    }
    
    industry_lower = industry.lower().strip()
    if industry_lower not in engines:
        raise ValueError(f"Unknown industry: {industry}. Valid: {list(engines.keys())}")
    
    return engines[industry_lower]

def adapt_spec_v2(industry: str, spec_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapt v2 format to v1 SpecV1-compatible structure.
    
    Converts v2 parameters to v1 spec structure that SpecV1 model expects.
    """
    industry_lower = industry.lower().strip()
    
    # Extract parameters based on format
    if "parameters" in spec_dict:
        # v2 format - extract parameters
        params = spec_dict["parameters"]
    elif "spec" in spec_dict:
        # v1 format - already has spec structure
        return spec_dict  # Return as-is for v1
    else:
        params = spec_dict
    
    # Extract or create data requirements
    data_requirements = spec_dict.get("data_requirements", {
        "max_sample_period_s": 30,
        "allowed_gaps_s": 60
    })
    
    # Create v1-compatible structure with proper spec field
    adapted = {
        "version": "1.0",
        "industry": industry_lower,
        "job": {
            "id": spec_dict.get("job_id", "default_job"),
            "batch": "",
            "product": "",
            "customer": ""
        },
        "data_requirements": data_requirements
    }
    
    # Map v2 parameters to v1 spec structure - ALL industries must use target_temp_C and hold_time_s
    if industry_lower in ["powder", "powder-coating"]:
        # Convert v2 parameters to v1 spec fields
        adapted["spec"] = {
            "target_temp_C": params.get("target_temp", 180),
            "hold_time_s": int(params.get("hold_duration_minutes", 10) * 60),  # Convert minutes to seconds
            "sensor_uncertainty_C": params.get("sensor_uncertainty", 2),
            "hysteresis_C": params.get("hysteresis", 2),
            "max_ramp_rate_C_per_min": params.get("max_ramp_rate", 50),
            "max_time_to_threshold_s": params.get("max_time_to_threshold", 900),
            "hold_logic": params.get("hold_logic", "continuous"),
            "method": "PMT"
        }
    
    elif industry_lower in ["autoclave"]:
        # For autoclave, map to standard v1 fields that SpecV1 expects
        adapted["spec"] = {
            "target_temp_C": params.get("sterilization_temp", 121),  # Map sterilization_temp to target_temp_C
            "hold_time_s": int(params.get("sterilization_time_minutes", 15) * 60),  # Map sterilization_time to hold_time_s
            "sensor_uncertainty_C": 2.0,  # Default sensor uncertainty
            "method": "OVEN_AIR",  # Must be PMT or OVEN_AIR
            # Store autoclave-specific params in a way that won't break validation
            "sterilization_temp_C": params.get("sterilization_temp", 121),
            "sterilization_time_s": int(params.get("sterilization_time_minutes", 15) * 60),
            "min_pressure_bar": params.get("min_pressure_bar", 2.0),
            "z_value": params.get("z_value", 10),
            "min_f0": params.get("min_f0", 12)
        }
    
    elif industry_lower in ["coldchain", "cold-chain"]:
        # Map to standard v1 fields
        adapted["spec"] = {
            "target_temp_C": params.get("max_temp", 8),  # Use max temp as target
            "hold_time_s": 3600,  # Default 1 hour
            "sensor_uncertainty_C": 1.0,
            "method": "OVEN_AIR",  # Must be PMT or OVEN_AIR
            # Store coldchain-specific params
            "min_temp_C": params.get("min_temp", 2),
            "max_temp_C": params.get("max_temp", 8),
            "compliance_percentage": params.get("compliance_percentage", 95),
            "max_excursion_minutes": params.get("max_excursion_minutes", 30)
        }
    
    elif industry_lower == "haccp":
        # Map to standard v1 fields
        adapted["spec"] = {
            "target_temp_C": params.get("temp_1", 135),  # Use first temp as target
            "hold_time_s": int(params.get("time_1_to_2_hours", 2) * 3600),  # Convert hours to seconds
            "sensor_uncertainty_C": 2.0,
            "method": "OVEN_AIR",  # Must be PMT or OVEN_AIR
            # Store HACCP-specific params
            "temp_1_C": params.get("temp_1", 135),
            "temp_2_C": params.get("temp_2", 70),
            "temp_3_C": params.get("temp_3", 41),
            "time_1_to_2_hours": params.get("time_1_to_2_hours", 2),
            "time_2_to_3_hours": params.get("time_2_to_3_hours", 4)
        }
    
    elif industry_lower == "concrete":
        # Map to standard v1 fields
        adapted["spec"] = {
            "target_temp_C": params.get("max_temp", 30),  # Use max temp as target
            "hold_time_s": int(params.get("time_window_hours", 24) * 3600),  # Convert hours to seconds
            "sensor_uncertainty_C": 2.0,
            "method": "OVEN_AIR",  # Must be PMT or OVEN_AIR
            # Store concrete-specific params
            "min_temp_C": params.get("min_temp", 10),
            "max_temp_C": params.get("max_temp", 30),
            "min_humidity": params.get("min_humidity", 80),
            "time_window_hours": params.get("time_window_hours", 24),
            "compliance_percentage": params.get("compliance_percentage", 95)
        }
    
    elif industry_lower in ["sterile", "eto"]:
        # Map to standard v1 fields
        adapted["spec"] = {
            "target_temp_C": params.get("min_temp", 55),  # Use min temp as target
            "hold_time_s": int(params.get("exposure_hours", 12) * 3600),  # Convert hours to seconds
            "sensor_uncertainty_C": 2.0,
            "method": "OVEN_AIR",  # Must be PMT or OVEN_AIR
            # Store sterile-specific params
            "min_temp_C": params.get("min_temp", 55),
            "max_temp_C": params.get("max_temp", 60),
            "exposure_hours": params.get("exposure_hours", 12),
            "min_humidity": params.get("min_humidity", 50)
        }
    
    else:
        # Fallback - generic spec mapping with safe defaults
        adapted["spec"] = {
            "target_temp_C": params.get("target_temp", 100),
            "hold_time_s": params.get("hold_time_s", 600),
            "sensor_uncertainty_C": params.get("sensor_uncertainty", 2),
            "method": "OVEN_AIR"
        }
    
    return adapted

def route_to_engine(industry: str, df: Any, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Route to appropriate engine with adapted spec."""
    engine = select_engine(industry)
    adapted_spec = adapt_spec_v2(industry, spec)
    
    # Pass adapted spec to metrics function
    return engine(df, adapted_spec)