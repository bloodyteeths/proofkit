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

def adapt_spec(industry: str, spec_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapt v1 legacy spec format to v2 unified format.
    
    Handles both:
    - v1: {"spec": {...}, "data_requirements": {...}}
    - v2: {"industry": "...", "parameters": {...}}
    """
    industry_lower = industry.lower().strip()
    
    # Extract parameters based on various possible formats
    if "parameters" in spec_dict:
        # v2 format - already in desired structure
        params = spec_dict["parameters"]
    elif "spec" in spec_dict:
        # v1 format - extract from "spec" key
        params = spec_dict["spec"]
    else:
        # Fallback - treat entire dict as parameters
        params = spec_dict
    
    # Extract data requirements if present (from v1)
    data_requirements = spec_dict.get("data_requirements", {})
    
    # Create unified v2 format
    adapted = {
        "industry": industry_lower,
        "data_requirements": data_requirements
    }
    
    if industry_lower in ["powder", "powder-coating"]:
        adapted["parameters"] = {
            "target_temp": params.get("target_temp", params.get("target_temp_C", 180)),
            "hold_duration_minutes": params.get("hold_duration_minutes", params.get("hold_time_s", 600) / 60),
            "sensor_uncertainty": params.get("sensor_uncertainty", params.get("sensor_uncertainty_C", 2)),
            "hysteresis": params.get("hysteresis", 2),
            "max_ramp_rate": params.get("max_ramp_rate", params.get("max_ramp_rate_C_per_min", 50))
        }
    
    elif industry_lower in ["autoclave"]:
        adapted["parameters"] = {
            "sterilization_temp": params.get("sterilization_temp", 121),
            "sterilization_time_minutes": params.get("sterilization_time_minutes", 15),
            "min_pressure_bar": params.get("min_pressure_bar", 2.0),
            "z_value": params.get("z_value", 10),
            "min_f0": params.get("min_f0", 12)
        }
    
    elif industry_lower in ["coldchain", "cold-chain"]:
        adapted["parameters"] = {
            "min_temp": params.get("min_temp", 2),
            "max_temp": params.get("max_temp", 8),
            "compliance_percentage": params.get("compliance_percentage", 95),
            "max_excursion_minutes": params.get("max_excursion_minutes", 30)
        }
    
    elif industry_lower == "haccp":
        adapted["parameters"] = {
            "temp_1": params.get("temp_1", 135),
            "temp_2": params.get("temp_2", 70),
            "temp_3": params.get("temp_3", 41),
            "time_1_to_2_hours": params.get("time_1_to_2_hours", 2),
            "time_2_to_3_hours": params.get("time_2_to_3_hours", 4)
        }
    
    elif industry_lower == "concrete":
        adapted["parameters"] = {
            "min_temp": params.get("min_temp", 10),
            "max_temp": params.get("max_temp", 30),
            "min_humidity": params.get("min_humidity", 80),
            "time_window_hours": params.get("time_window_hours", 24),
            "compliance_percentage": params.get("compliance_percentage", 95)
        }
    
    elif industry_lower in ["sterile", "eto"]:
        adapted["parameters"] = {
            "min_temp": params.get("min_temp", 55),
            "exposure_hours": params.get("exposure_hours", 12),
            "min_humidity": params.get("min_humidity", 50),
            "max_temp": params.get("max_temp", 60)
        }
    
    else:
        adapted["parameters"] = params
    
    return adapted

def route_to_engine(industry: str, df: Any, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Route to appropriate engine with adapted spec."""
    engine = select_engine(industry)
    adapted_spec = adapt_spec(industry, spec)
    
    # Call the appropriate metrics function directly
    return engine(df, adapted_spec)