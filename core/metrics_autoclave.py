"""
ProofKit Autoclave Sterilization Validation Metrics Engine

Implements autoclave sterilization validation according to pharmaceutical and medical device
standards. Validates critical sterilization parameters:
- Temperature: 121°C ± 2°C for minimum 15 minutes
- Pressure: ≥15 psi (103.4 kPa) maintained throughout cycle
- Fo value: ≥12 (lethality equivalent to 121°C for 12 minutes)

Example usage:
    from core.metrics_autoclave import validate_autoclave_sterilization
    from core.models import SpecV1
    
    spec = SpecV1(**spec_data)  # Autoclave industry spec
    normalized_df = pd.read_csv("sterilization_data.csv")
    
    result = validate_autoclave_sterilization(normalized_df, spec)
    print(f"Autoclave Sterilization: {'PASS' if result.pass_ else 'FAIL'}")
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from core.models import SpecV1, DecisionResult, SensorMode
from core.sensor_utils import combine_sensor_readings
from core.temperature_utils import detect_temperature_columns, DecisionError
from core.decide import calculate_continuous_hold_time

logger = logging.getLogger(__name__)


def calculate_fo_value(temperature_series: pd.Series, time_series: pd.Series, 
                      z_value: float = 10.0, reference_temp_c: float = 121.0) -> float:
    """
    Calculate Fo (sterilization lethality) value according to pharmaceutical standards.
    
    Fo represents the equivalent time in minutes at 121°C that would provide 
    the same lethality as the actual temperature profile.
    
    Formula: Fo = Σ(Δt × 10^((T-121)/z))
    where:
    - Δt = time interval in minutes
    - T = temperature in Celsius
    - z = temperature coefficient (typically 10°C for steam sterilization)
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        z_value: Temperature coefficient for lethality calculation (default 10°C)
        reference_temp_c: Reference temperature for Fo calculation (default 121°C)
        
    Returns:
        Fo value in minutes equivalent at 121°C
    """
    if len(temperature_series) < 2:
        return 0.0
    
    fo_value = 0.0
    
    for i in range(1, len(temperature_series)):
        # Calculate time interval in minutes
        time_interval_s = (time_series.iloc[i] - time_series.iloc[i-1]).total_seconds()
        time_interval_min = time_interval_s / 60.0
        
        # Use average temperature over interval
        temp_c = (temperature_series.iloc[i] + temperature_series.iloc[i-1]) / 2.0
        
        # Calculate lethality rate at this temperature
        lethality_rate = 10 ** ((temp_c - reference_temp_c) / z_value)
        
        # Add to cumulative Fo value
        fo_value += time_interval_min * lethality_rate
    
    return fo_value


def detect_pressure_columns(df: pd.DataFrame) -> List[str]:
    """
    Detect pressure columns in the DataFrame.
    
    Args:
        df: Input DataFrame
        
    Returns:
        List of pressure column names
    """
    import re
    
    pressure_patterns = [
        r'.*pressure.*', r'.*press.*', r'.*psi.*', r'.*kpa.*', r'.*bar.*',
        r'.*_p$', r'.*_pressure$'
    ]
    
    pressure_columns = []
    
    for col in df.columns:
        if col.lower() == 'timestamp' or 'time' in col.lower():
            continue
            
        col_lower = col.lower()
        if any(re.match(pattern, col_lower) for pattern in pressure_patterns):
            # Verify it's numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                pressure_columns.append(col)
    
    return pressure_columns


def psi_to_kpa(pressure_psi: float) -> float:
    """Convert pressure from PSI to kPa."""
    return pressure_psi * 6.895


def kpa_to_psi(pressure_kpa: float) -> float:
    """Convert pressure from kPa to PSI."""
    return pressure_kpa / 6.895


def validate_autoclave_cycle(temperature_series: pd.Series, time_series: pd.Series,
                           pressure_series: Optional[pd.Series] = None) -> Dict[str, Any]:
    """
    Validate autoclave sterilization cycle according to pharmaceutical standards.
    
    Requirements:
    - Temperature: 121°C ± 2°C (119-123°C) for minimum 15 minutes
    - Pressure: ≥15 psi (103.4 kPa) maintained throughout sterilization phase
    - Fo value: ≥12 minutes equivalent at 121°C
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        pressure_series: Optional pressure values (assumed in kPa)
        
    Returns:
        Dictionary with autoclave validation results and metrics
    """
    # Autoclave critical parameters
    MIN_TEMP_C = 119.0  # 121°C - 2°C tolerance
    MAX_TEMP_C = 123.0  # 121°C + 2°C tolerance
    TARGET_TEMP_C = 121.0
    MIN_HOLD_TIME_S = 15 * 60  # 15 minutes
    MIN_PRESSURE_KPA = 103.4  # 15 psi
    MIN_FO_VALUE = 12.0
    
    metrics = {
        'start_temp_C': float(temperature_series.iloc[0]),
        'end_temp_C': float(temperature_series.iloc[-1]),
        'min_temp_C': float(temperature_series.min()),
        'max_temp_C': float(temperature_series.max()),
        'target_temp_C': TARGET_TEMP_C,
        'min_sterilization_temp_C': MIN_TEMP_C,
        'max_sterilization_temp_C': MAX_TEMP_C,
        'total_duration_s': (time_series.iloc[-1] - time_series.iloc[0]).total_seconds(),
        'sterilization_hold_time_s': 0.0,
        'fo_value': 0.0,
        'min_pressure_kpa': None,
        'avg_pressure_kpa': None,
        'pressure_maintained': True,
        'temperature_range_valid': False,
        'hold_time_valid': False,
        'fo_value_valid': False,
        'pressure_valid': True,  # Default to True if no pressure data
        'reasons': []
    }
    
    # Calculate Fo value
    fo_value = calculate_fo_value(temperature_series, time_series)
    metrics['fo_value'] = fo_value
    
    if fo_value >= MIN_FO_VALUE:
        metrics['fo_value_valid'] = True
    else:
        metrics['reasons'].append(f"Fo value {fo_value:.1f} < {MIN_FO_VALUE} minimum requirement")
    
    # Validate temperature range and hold time
    in_sterilization_range = (temperature_series >= MIN_TEMP_C) & (temperature_series <= MAX_TEMP_C)
    
    if in_sterilization_range.any():
        metrics['temperature_range_valid'] = True
        
        # Calculate continuous hold time in sterilization range using hysteresis
        hold_time_s, start_idx, end_idx = calculate_continuous_hold_time(
            temperature_series, time_series, MIN_TEMP_C, hysteresis_C=1.0
        )
        metrics['sterilization_hold_time_s'] = hold_time_s
        
        if hold_time_s >= MIN_HOLD_TIME_S:
            metrics['hold_time_valid'] = True
        else:
            metrics['reasons'].append(f"Sterilization hold time {hold_time_s/60:.1f}min < {MIN_HOLD_TIME_S/60}min requirement")
    else:
        metrics['reasons'].append(f"Temperature never reached sterilization range ({MIN_TEMP_C}-{MAX_TEMP_C}°C)")
    
    # Validate temperature doesn't exceed maximum
    if temperature_series.max() > MAX_TEMP_C:
        metrics['reasons'].append(f"Maximum temperature {temperature_series.max():.1f}°C > {MAX_TEMP_C}°C limit")
        metrics['temperature_range_valid'] = False
    
    # Validate pressure if provided
    if pressure_series is not None:
        metrics['min_pressure_kpa'] = float(pressure_series.min())
        metrics['avg_pressure_kpa'] = float(pressure_series.mean())
        
        # Check if pressure maintained above minimum during sterilization phase
        if in_sterilization_range.any():
            sterilization_pressures = pressure_series[in_sterilization_range]
            if len(sterilization_pressures) > 0:
                min_sterilization_pressure = sterilization_pressures.min()
                if min_sterilization_pressure < MIN_PRESSURE_KPA:
                    metrics['pressure_maintained'] = False
                    metrics['pressure_valid'] = False
                    metrics['reasons'].append(
                        f"Pressure dropped to {kpa_to_psi(min_sterilization_pressure):.1f} psi "
                        f"< {kpa_to_psi(MIN_PRESSURE_KPA):.1f} psi during sterilization"
                    )
        
        # Overall pressure check
        if pressure_series.min() < MIN_PRESSURE_KPA:
            low_pressure_time = (pressure_series < MIN_PRESSURE_KPA).sum()
            total_samples = len(pressure_series)
            low_pressure_pct = (low_pressure_time / total_samples) * 100
            if low_pressure_pct > 5:  # Allow brief pressure drops (≤5% of time)
                metrics['pressure_valid'] = False
                metrics['reasons'].append(
                    f"Pressure below {kpa_to_psi(MIN_PRESSURE_KPA):.1f} psi for {low_pressure_pct:.1f}% of cycle"
                )
    
    return metrics


def validate_autoclave_sterilization(normalized_df: pd.DataFrame, spec: SpecV1) -> DecisionResult:
    """
    Validate autoclave sterilization process based on normalized data and specification.
    
    Args:
        normalized_df: Normalized temperature and pressure data from core.normalize.py
        spec: Autoclave industry specification
        
    Returns:
        DecisionResult with autoclave-specific pass/fail status and detailed metrics
        
    Raises:
        DecisionError: If validation cannot be performed due to data issues
    """
    try:
        # Initialize result tracking
        reasons = []
        warnings = []
        
        # Validate inputs
        if normalized_df.empty:
            raise DecisionError("Normalized DataFrame is empty")
        
        if len(normalized_df) < 2:
            raise DecisionError("Insufficient data points for autoclave sterilization analysis")
            
        if spec.industry != "autoclave":
            raise DecisionError(f"Invalid industry '{spec.industry}' for autoclave sterilization validation")
        
        # Detect timestamp column
        timestamp_col = None
        for col in normalized_df.columns:
            if 'time' in col.lower() or pd.api.types.is_datetime64_any_dtype(normalized_df[col]):
                timestamp_col = col
                break
        
        if timestamp_col is None:
            raise DecisionError("No timestamp column found in normalized data")
        
        # Ensure timestamps are datetime
        if not pd.api.types.is_datetime64_any_dtype(normalized_df[timestamp_col]):
            normalized_df[timestamp_col] = pd.to_datetime(normalized_df[timestamp_col])
        
        # Detect temperature columns
        temp_columns = detect_temperature_columns(normalized_df)
        if not temp_columns:
            raise DecisionError("No temperature columns found in normalized data")
        
        # Detect pressure columns (optional by default; may be required by spec)
        pressure_columns = detect_pressure_columns(normalized_df)
        
        # Get sensor selection configuration
        sensor_selection = spec.sensor_selection
        if sensor_selection and sensor_selection.sensors:
            # Filter for available temperature sensors
            available_temp_sensors = [col for col in sensor_selection.sensors if col in temp_columns]
            if not available_temp_sensors:
                # Do not fail; warn and continue with auto-detected temp columns
                warnings.append(
                    f"Specified temperature sensors not found: {sensor_selection.sensors}. Using auto-detected sensors: {temp_columns}"
                )
                flags = locals().get('flags', {})
                flags['fallback_used'] = True
                locals()['flags'] = flags
            else:
                temp_columns = available_temp_sensors
            
            # Filter for available pressure sensors
            available_pressure_sensors = [col for col in sensor_selection.sensors if col in pressure_columns]
            if available_pressure_sensors:
                pressure_columns = available_pressure_sensors
            
            if sensor_selection.require_at_least and len(available_temp_sensors) < sensor_selection.require_at_least:
                warnings.append(f"Only {len(available_temp_sensors)} temperature sensors available, {sensor_selection.require_at_least} required")
        
        # Combine temperature sensor readings (min_of_set for conservative sterilization validation)
        sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MIN_OF_SET
        require_at_least = sensor_selection.require_at_least if sensor_selection else None
        
        try:
            combined_temp = combine_sensor_readings(
                normalized_df, temp_columns, sensor_mode, require_at_least
            )
        except DecisionError as e:
            reasons.append(f"Temperature sensor combination failed: {str(e)}")
            return DecisionResult(
                pass_=False,
                job_id=spec.job.job_id,
                target_temp_C=121.0,
                conservative_threshold_C=119.0,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=0.0,
                min_temp_C=0.0,
                reasons=reasons,
                warnings=warnings
            )
        
        # Combine pressure sensor readings if available
        combined_pressure = None
        if pressure_columns:
            try:
                combined_pressure = combine_sensor_readings(
                    normalized_df, pressure_columns, SensorMode.MIN_OF_SET  # Use min pressure for conservative validation
                )
            except DecisionError as e:
                warnings.append(f"Pressure sensor combination failed: {str(e)}")
        else:
            warnings.append("No pressure sensors detected - validation will proceed without pressure monitoring")
            flags = locals().get('flags', {})
            flags['fallback_used'] = True
            locals()['flags'] = flags
        
        # Validate autoclave sterilization cycle
        cycle_metrics = validate_autoclave_cycle(
            combined_temp, normalized_df[timestamp_col], combined_pressure
        )

        # Enforce required parameters per spec
        require_pressure = bool(getattr(spec, 'parameter_requirements', None) and getattr(spec.parameter_requirements, 'require_pressure', False))
        require_fo = bool(getattr(spec, 'parameter_requirements', None) and getattr(spec.parameter_requirements, 'require_fo', False))

        if require_pressure and combined_pressure is None:
            cycle_metrics['pressure_valid'] = False
            cycle_metrics['reasons'].append("Pressure data required by specification but not provided")
        
        # Determine overall pass/fail status
        pass_decision = (
            cycle_metrics['temperature_range_valid'] and
            cycle_metrics['hold_time_valid'] and
            cycle_metrics['fo_value_valid'] and
            cycle_metrics['pressure_valid']
        )

        # Determine status with required parameters enforcement
        status = 'PASS' if pass_decision else 'FAIL'
        if require_pressure and combined_pressure is None:
            status = 'INDETERMINATE'
        if require_fo and not cycle_metrics.get('fo_value_valid', False):
            status = 'FAIL'  # Fo invalid is a hard fail
        
        # Add success reasons if passed
        if pass_decision:
            reasons.append(f"Temperature maintained in sterilization range (119-123°C) for {cycle_metrics['sterilization_hold_time_s']/60:.1f}min")
            reasons.append(f"Fo value {cycle_metrics['fo_value']:.1f} ≥ 12 minutes equivalent at 121°C")
            if cycle_metrics['pressure_valid'] and combined_pressure is not None:
                reasons.append(f"Pressure maintained above 15 psi during sterilization")
            reasons.append("Autoclave sterilization requirements met")
        else:
            # Add failure reasons
            reasons.extend(cycle_metrics['reasons'])
        
        # Check data quality warnings
        total_duration_h = cycle_metrics['total_duration_s'] / 3600
        if total_duration_h > 4:
            warnings.append(f"Sterilization cycle duration ({total_duration_h:.1f}h) exceeds typical autoclave timeline")
        
        if cycle_metrics['max_temp_C'] > 130.0:
            warnings.append(f"Maximum temperature ({cycle_metrics['max_temp_C']:.1f}°C) may damage heat-sensitive materials")
        
        return DecisionResult(
            pass_=pass_decision,
            status=status,
            job_id=spec.job.job_id,
            target_temp_C=121.0,  # Standard autoclave temperature
            conservative_threshold_C=119.0,  # Minimum acceptable temperature
            actual_hold_time_s=cycle_metrics['sterilization_hold_time_s'],
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=cycle_metrics['max_temp_C'],
            min_temp_C=cycle_metrics['min_temp_C'],
            reasons=reasons,
            warnings=warnings,
            flags=locals().get('flags', {})
        )
    
    except Exception as e:
        logger.error(f"Autoclave sterilization validation failed: {e}")
        raise DecisionError(f"Autoclave sterilization validation failed: {str(e)}")


# Usage example in comments:
"""
Example usage for autoclave sterilization validation:

from core.metrics_autoclave import validate_autoclave_sterilization
from core.models import SpecV1
import pandas as pd

# Load autoclave specification
spec_data = {
    "version": "1.0",
    "industry": "autoclave",
    "job": {"job_id": "pharma_sterilization_001"},
    "spec": {
        "method": "OVEN_AIR",
        "target_temp_C": 121.0,
        "hold_time_s": 900,  # 15 minutes
        "sensor_uncertainty_C": 0.5
    },
    "data_requirements": {
        "max_sample_period_s": 10.0,
        "allowed_gaps_s": 30.0
    },
    "sensor_selection": {
        "mode": "min_of_set",
        "require_at_least": 2
    }
}
spec = SpecV1(**spec_data)

# Load normalized sterilization data (with temperature and pressure columns)
normalized_df = pd.read_csv("autoclave_sterilization_data.csv")

# Validate autoclave sterilization
result = validate_autoclave_sterilization(normalized_df, spec)

print(f"Autoclave Sterilization Job {result.job_id}: {'PASS' if result.pass_ else 'FAIL'}")
print(f"Sterilization validation: {result.reasons}")
if result.warnings:
    print(f"Warnings: {result.warnings}")
"""