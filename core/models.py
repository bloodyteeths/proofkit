"""
ProofKit Core Models

Pydantic v2 models for powder-coat cure specifications and data structures.
These models provide type validation, serialization, and documentation
for all ProofKit data contracts.

Example usage:
    from core.models import SpecV1
    
    spec_data = {
        "version": "1.0",
        "job": {"job_id": "batch_001"},
        "spec": {
            "method": "PMT",
            "target_temp_C": 180.0,
            "hold_time_s": 600
        },
        "data_requirements": {
            "max_sample_period_s": 30.0,
            "allowed_gaps_s": 60.0
        }
    }
    spec = SpecV1(**spec_data)
    print(f"Job {spec.job.job_id} targets {spec.spec.target_temp_C}°C")
"""

from enum import Enum
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import re


class CureMethod(str, Enum):
    """Enumeration of supported cure methods."""
    PMT = "PMT"
    OVEN_AIR = "OVEN_AIR"


class SensorMode(str, Enum):
    """Enumeration of sensor combination modes."""
    MIN_OF_SET = "min_of_set"
    MEAN_OF_SET = "mean_of_set"
    MAJORITY_OVER_THRESHOLD = "majority_over_threshold"


class TemperatureUnits(str, Enum):
    """Temperature units for reporting."""
    CELSIUS = "C"
    FAHRENHEIT = "F"


class Industry(str, Enum):
    """Enumeration of supported industries."""
    POWDER = "powder"
    HACCP = "haccp"
    AUTOCLAVE = "autoclave"
    STERILE = "sterile"
    CONCRETE = "concrete"
    COLDCHAIN = "coldchain"


class JobInfo(BaseModel):
    """Job identification and metadata."""
    job_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Unique identifier for this cure job"
    )


class TemperatureBand(BaseModel):
    """Optional temperature band constraints."""
    min: Optional[float] = Field(None, description="Minimum acceptable temperature in Celsius")
    max: Optional[float] = Field(None, description="Maximum acceptable temperature in Celsius")
    
    @model_validator(mode='after')
    def validate_band(self):
        """Ensure min <= max if both are specified."""
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Temperature band minimum cannot be greater than maximum")
        return self


class CureSpec(BaseModel):
    """Core cure process specification."""
    method: CureMethod = Field(..., description="Cure method - PMT or OVEN_AIR")
    target_temp_C: float = Field(
        ...,
        gt=0,
        le=300,
        description="Target cure temperature in Celsius (must be > 0)"
    )
    hold_time_s: int = Field(
        ...,
        ge=1,
        le=172800,  # Increased to 48 hours (172800s) to support concrete curing and other long processes
        description="Required hold time at target temperature in seconds (>= 1, <= 48 hours)"
    )
    temp_band_C: Optional[TemperatureBand] = Field(
        None,
        description="Optional temperature band constraints"
    )
    sensor_uncertainty_C: float = Field(
        2.0,
        ge=0,
        le=10,
        description="Sensor measurement uncertainty in Celsius (default: 2.0)"
    )


class DataRequirements(BaseModel):
    """Data quality and sampling requirements."""
    max_sample_period_s: float = Field(
        ...,
        ge=1,
        le=3600,  # Increased to 1 hour to support longer monitoring intervals
        description="Maximum allowed time between samples in seconds (>= 1, <= 1 hour)"
    )
    allowed_gaps_s: float = Field(
        ...,
        ge=0,
        le=7200,  # Increased to 2 hours to support longer gap tolerances
        description="Maximum allowed gap in data in seconds (>= 0, <= 2 hours)"
    )


class SensorSelection(BaseModel):
    """Sensor selection and combination logic."""
    mode: SensorMode = Field(
        SensorMode.MIN_OF_SET,
        description="Method for combining multiple sensor readings"
    )
    sensors: Optional[List[str]] = Field(
        None,
        min_items=1,
        description="List of sensor column names to use"
    )
    require_at_least: Optional[int] = Field(
        None,
        ge=1,
        description="Minimum number of sensors required for valid reading"
    )
    
    @field_validator('sensors')
    @classmethod
    def validate_sensors(cls, v):
        """Ensure sensor names are unique and non-empty."""
        if v is not None:
            if len(set(v)) != len(v):
                raise ValueError("Sensor names must be unique")
            if any(not sensor.strip() for sensor in v):
                raise ValueError("Sensor names cannot be empty")
        return v


class Logic(BaseModel):
    """Logic configuration for hold time calculation."""
    continuous: bool = Field(
        True,
        description="Whether hold time must be continuous (true) or cumulative (false)"
    )
    max_total_dips_s: int = Field(
        0,
        ge=0,
        description="Maximum total time below threshold allowed in cumulative mode"
    )


class Preconditions(BaseModel):
    """Precondition checks for the cure process."""
    max_ramp_rate_C_per_min: Optional[float] = Field(
        None,
        ge=0,
        description="Maximum allowed temperature ramp rate in Celsius per minute"
    )
    max_time_to_threshold_s: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum time allowed to reach target threshold in seconds"
    )


class Reporting(BaseModel):
    """Reporting preferences and formatting."""
    units: TemperatureUnits = Field(
        TemperatureUnits.CELSIUS,
        description="Temperature units for reporting (Celsius or Fahrenheit)"
    )
    language: str = Field(
        "en",
        pattern=r"^[a-z]{2}$",
        description="Language code for report generation (ISO 639-1)"
    )
    timezone: str = Field(
        "UTC",
        description="Timezone for timestamp formatting (IANA timezone name)"
    )


class SpecV1(BaseModel):
    """
    Complete powder-coat cure specification v1.0.
    
    This is the root model that contains all specification data
    required for ProofKit to validate a cure process.
    """
    version: Literal["1.0"] = Field("1.0", description="Specification version identifier")
    industry: Literal["powder", "haccp", "autoclave", "sterile", "concrete", "coldchain"] = Field(
        "powder", 
        description="Industry specification type"
    )
    job: JobInfo = Field(..., description="Job identification and metadata")
    spec: CureSpec = Field(..., description="Core cure process specification")
    data_requirements: DataRequirements = Field(..., description="Data quality requirements")
    
    # Optional sections
    sensor_selection: Optional[SensorSelection] = Field(
        None,
        description="Optional sensor selection and combination logic"
    )
    logic: Optional[Logic] = Field(
        None,
        description="Optional logic configuration for hold time calculation"
    )
    preconditions: Optional[Preconditions] = Field(
        None,
        description="Optional precondition checks for the cure process"
    )
    reporting: Optional[Reporting] = Field(
        None,
        description="Optional reporting preferences"
    )
    
    @model_validator(mode='after')
    def validate_industry_specification(self):
        """Validate that the industry field matches specification constraints."""
        # All industries currently use version 1.0, so version validation is consistent
        if self.version != "1.0":
            raise ValueError(f"Unsupported version '{self.version}' for industry '{self.industry}'")
            
        # Industry-specific validation
        if self.industry == "powder":
            # Powder coat specifications typically use PMT or OVEN_AIR methods
            if self.spec.method not in ["PMT", "OVEN_AIR"]:
                raise ValueError(f"Invalid method '{self.spec.method}' for powder coating industry")
        elif self.industry == "haccp":
            # HACCP cooling requires OVEN_AIR method for food safety monitoring
            if self.spec.method != "OVEN_AIR":
                raise ValueError(f"HACCP industry requires OVEN_AIR method, got '{self.spec.method}'")
        elif self.industry == "autoclave":
            # Autoclave sterilization uses OVEN_AIR for steam monitoring
            if self.spec.method != "OVEN_AIR":
                raise ValueError(f"Autoclave industry requires OVEN_AIR method, got '{self.spec.method}'")
        elif self.industry == "sterile":
            # EtO sterilization uses OVEN_AIR for gas/temperature monitoring
            if self.spec.method != "OVEN_AIR":
                raise ValueError(f"Sterile industry requires OVEN_AIR method, got '{self.spec.method}'")
        elif self.industry == "concrete":
            # Concrete curing uses OVEN_AIR for ambient monitoring
            if self.spec.method != "OVEN_AIR":
                raise ValueError(f"Concrete industry requires OVEN_AIR method, got '{self.spec.method}'")
        elif self.industry == "coldchain":
            # Cold chain uses OVEN_AIR for ambient temperature monitoring
            if self.spec.method != "OVEN_AIR":
                raise ValueError(f"Cold chain industry requires OVEN_AIR method, got '{self.spec.method}'")
                
        return self
    
    model_config = {
        # Reject unknown fields to ensure strict validation
        "extra": "forbid",
        # Use enum values in serialization
        "use_enum_values": True,
        # Validate assignment for runtime safety
        "validate_assignment": True,
        # Generate schema for OpenAPI docs
        "json_schema_extra": {
            "example": {
                "version": "1.0",
                "industry": "powder",
                "job": {
                    "job_id": "batch_001"
                },
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 180.0,
                    "hold_time_s": 600,
                    "sensor_uncertainty_C": 2.0
                },
                "data_requirements": {
                    "max_sample_period_s": 30.0,
                    "allowed_gaps_s": 60.0
                }
            }
        }
    }


class DecisionResult(BaseModel):
    """
    Decision result structure for cure process validation.
    
    This model represents the output of the decision algorithm
    and contains pass/fail status, metrics, and detailed reasons.
    """
    pass_: bool = Field(..., alias="pass", description="Whether the cure process passed")
    job_id: str = Field(..., description="Job identifier from the specification")
    target_temp_C: float = Field(..., description="Target temperature from specification")
    conservative_threshold_C: float = Field(..., description="Calculated threshold (target + uncertainty)")
    actual_hold_time_s: float = Field(..., description="Actual measured hold time in seconds")
    required_hold_time_s: int = Field(..., description="Required hold time from specification")
    max_temp_C: float = Field(..., description="Maximum temperature recorded")
    min_temp_C: float = Field(..., description="Minimum temperature recorded")
    reasons: List[str] = Field(default_factory=list, description="List of reasons for pass/fail decision")
    warnings: List[str] = Field(default_factory=list, description="List of warnings about data quality")
    
    model_config = {
        "extra": "forbid",
        "populate_by_name": True  # Allow both 'pass' and 'pass_' field names
    }


# Usage example in comments:
"""
Example usage:

from core.models import SpecV1, CureMethod, SensorMode

# Create a basic specification
spec = SpecV1(
    job={"job_id": "test_batch_001"},
    spec={
        "method": CureMethod.PMT,
        "target_temp_C": 180.0,
        "hold_time_s": 600
    },
    data_requirements={
        "max_sample_period_s": 30.0,
        "allowed_gaps_s": 60.0
    }
)

# Access validated data
print(f"Target: {spec.spec.target_temp_C}°C for {spec.spec.hold_time_s}s")
"""