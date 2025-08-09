"""
ProofKit HACCP Cooling Validation Metrics Engine

Implements HACCP (Hazard Analysis Critical Control Points) food safety cooling validation
according to FDA Food Code requirements. Validates critical cooling phases:
- Phase 1: 135°F to 70°F within 2 hours
- Phase 2: 135°F to 41°F within 6 hours total

Example usage:
    from core.metrics_haccp import validate_haccp_cooling
    from core.models import SpecV1
    
    spec = SpecV1(**spec_data)  # HACCP industry spec
    normalized_df = pd.read_csv("cooling_data.csv")
    
    result = validate_haccp_cooling(normalized_df, spec)
    print(f"HACCP Cooling: {'PASS' if result.pass_ else 'FAIL'}")
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from core.models import SpecV1, DecisionResult, SensorMode
from core.sensor_utils import combine_sensor_readings
from core.temperature_utils import detect_temperature_columns, DecisionError
from core.errors import RequiredSignalMissingError

logger = logging.getLogger(__name__)


def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (temp_f - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (temp_c * 9.0 / 5.0) + 32.0


def find_temperature_time(temperature_series: pd.Series, time_series: pd.Series, 
                         target_temp_C: float, direction: str = 'cooling') -> Optional[float]:
    """
    Find the time when temperature reaches a target during cooling or heating using linear interpolation.
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        target_temp_C: Target temperature in Celsius
        direction: 'cooling' (decreasing temp) or 'heating' (increasing temp)
        
    Returns:
        Time in seconds from start when target is reached, or None if never reached
    """
    start_time = time_series.iloc[0]
    
    for i in range(len(temperature_series) - 1):
        temp_current = temperature_series.iloc[i]
        temp_next = temperature_series.iloc[i + 1]
        time_current = time_series.iloc[i]
        time_next = time_series.iloc[i + 1]
        
        if direction == 'cooling':
            # Check if we cross the target going downward - use proper linear interpolation
            if temp_current >= target_temp_C >= temp_next:
                # Linear interpolation to find exact crossing time
                if abs(temp_current - temp_next) < 1e-10:  # Avoid division by zero
                    crossing_time = time_current
                else:
                    # Linear interpolation: time = t1 + (target - temp1) * (t2 - t1) / (temp2 - temp1)
                    time_fraction = (target_temp_C - temp_current) / (temp_next - temp_current)
                    crossing_time = time_current + pd.Timedelta(seconds=(time_next - time_current).total_seconds() * time_fraction)
                
                return (crossing_time - start_time).total_seconds()
        else:  # heating
            # Check if we cross the target going upward - use proper linear interpolation
            if temp_current <= target_temp_C <= temp_next:
                # Linear interpolation to find exact crossing time
                if abs(temp_current - temp_next) < 1e-10:  # Avoid division by zero
                    crossing_time = time_current
                else:
                    time_fraction = (target_temp_C - temp_current) / (temp_next - temp_current)
                    crossing_time = time_current + pd.Timedelta(seconds=(time_next - time_current).total_seconds() * time_fraction)
                
                return (crossing_time - start_time).total_seconds()
    
    return None


def validate_haccp_cooling_phases(temperature_series: pd.Series, time_series: pd.Series) -> Dict[str, Any]:
    """
    Validate HACCP cooling phases according to FDA Food Code.
    
    Phase 1: Cool from 135°F (57.2°C) to 70°F (21.1°C) within 2 hours
    Phase 2: Cool from 135°F (57.2°C) to 41°F (5.0°C) within 6 hours total
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        
    Returns:
        Dictionary with phase validation results and metrics
    """
    # HACCP critical temperatures in Celsius
    temp_135f_c = fahrenheit_to_celsius(135.0)  # 57.2°C
    temp_70f_c = fahrenheit_to_celsius(70.0)    # 21.1°C
    temp_41f_c = fahrenheit_to_celsius(41.0)    # 5.0°C
    
    # Time limits in seconds
    PHASE_1_LIMIT_S = 2 * 3600  # 2 hours
    PHASE_2_LIMIT_S = 6 * 3600  # 6 hours
    
    metrics = {
        'start_temp_C': float(temperature_series.iloc[0]),
        'end_temp_C': float(temperature_series.iloc[-1]),
        'min_temp_C': float(temperature_series.min()),
        'max_temp_C': float(temperature_series.max()),
        'total_duration_s': (time_series.iloc[-1] - time_series.iloc[0]).total_seconds(),
        'phase_1_pass': False,
        'phase_2_pass': False,
        'time_to_70f_s': None,
        'time_to_41f_s': None,
        'phase_1_time_limit_s': PHASE_1_LIMIT_S,
        'phase_2_time_limit_s': PHASE_2_LIMIT_S,
        'start_temp_valid': False,
        'cooling_rate_valid': True,
        'reasons': []
    }
    
    # Validate starting temperature (must be at or above 135°F)
    # Use small tolerance for floating point comparison
    if temperature_series.iloc[0] < (temp_135f_c - 0.1):
        metrics['reasons'].append(f"Starting temperature {celsius_to_fahrenheit(temperature_series.iloc[0]):.1f}°F < 135°F requirement")
        metrics['start_temp_valid'] = False
    else:
        metrics['start_temp_valid'] = True
    
    # Check if temperature ever increases (invalid for cooling)
    temp_diffs = temperature_series.diff()
    if temp_diffs.max() > 2.0:  # Allow small fluctuations (2°C tolerance)
        metrics['reasons'].append("Temperature increased during cooling process (heating detected)")
        metrics['cooling_rate_valid'] = False
    
    # Find time to reach 70°F (Phase 1 target)
    time_to_70f = find_temperature_time(temperature_series, time_series, temp_70f_c, 'cooling')
    if time_to_70f is not None:
        metrics['time_to_70f_s'] = time_to_70f
        if time_to_70f <= PHASE_1_LIMIT_S:
            metrics['phase_1_pass'] = True
        else:
            metrics['reasons'].append(f"exceeded 2h to 70°F (Phase 1 cooling took {time_to_70f/3600:.1f}h)")
    else:
        metrics['reasons'].append("Temperature never reached 70°F (Phase 1 target not achieved)")
    
    # Find time to reach 41°F (Phase 2 target)  
    time_to_41f = find_temperature_time(temperature_series, time_series, temp_41f_c, 'cooling')
    if time_to_41f is not None:
        metrics['time_to_41f_s'] = time_to_41f
        if time_to_41f <= PHASE_2_LIMIT_S:
            metrics['phase_2_pass'] = True
        else:
            metrics['reasons'].append(f"exceeded 6h to 41°F (Phase 2 cooling took {time_to_41f/3600:.1f}h)")
    else:
        metrics['reasons'].append("Temperature never reached 41°F (Phase 2 target not achieved)")
    
    return metrics


def validate_haccp_cooling(normalized_df: pd.DataFrame, spec: SpecV1) -> DecisionResult:
    """
    Validate HACCP cooling process based on normalized data and specification.
    
    Args:
        normalized_df: Normalized temperature data from core.normalize.py
        spec: HACCP industry specification
        
    Returns:
        DecisionResult with HACCP-specific pass/fail status and detailed metrics
        
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
            raise DecisionError("Insufficient data points for HACCP cooling analysis")
            
        if spec.industry != "haccp":
            raise DecisionError(f"Invalid industry '{spec.industry}' for HACCP cooling validation")
        
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
        
        # Detect temperature columns - this must be done first before any other processing
        # For HACCP, we require columns with explicit temperature naming (temp|temperature|°f|°c)
        temp_columns = detect_temperature_columns(normalized_df)
        if not temp_columns:
            # Get available columns (excluding timestamp)
            available_cols = [col for col in normalized_df.columns if col != timestamp_col]
            raise RequiredSignalMissingError(
                missing_signals=["temperature"],
                available_signals=available_cols,
                industry="haccp"
            )
        
        # Get sensor selection configuration
        sensor_selection = spec.sensor_selection
        if sensor_selection and sensor_selection.sensors:
            # Use specified sensors when present; otherwise warn and fallback to auto-detected
            available_sensors = [col for col in sensor_selection.sensors if col in temp_columns]
            if not available_sensors:
                warnings.append(
                    f"Specified sensors not found: {sensor_selection.sensors}. Using auto-detected sensors: {temp_columns}"
                )
            else:
                temp_columns = available_sensors
                if sensor_selection.require_at_least and len(available_sensors) < sensor_selection.require_at_least:
                    warnings.append(f"Only {len(available_sensors)} sensors available, {sensor_selection.require_at_least} required")
        
        # Combine sensor readings (typically mean for HACCP to get representative temperature)
        sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MEAN_OF_SET
        require_at_least = sensor_selection.require_at_least if sensor_selection else None
        
        try:
            combined_temp = combine_sensor_readings(
                normalized_df, temp_columns, sensor_mode, require_at_least
            )
        except DecisionError as e:
            reasons.append(f"Sensor combination failed: {str(e)}")
            return DecisionResult(
                pass_=False,
                job_id=spec.job.job_id,
                target_temp_C=spec.spec.target_temp_C,
                conservative_threshold_C=spec.spec.target_temp_C,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=0.0,
                min_temp_C=0.0,
                reasons=reasons,
                warnings=warnings,
                industry=spec.industry
            )
        
        # Validate HACCP cooling phases
        cooling_metrics = validate_haccp_cooling_phases(combined_temp, normalized_df[timestamp_col])
        
        # Determine overall pass/fail status - must pass ALL criteria
        # If ANY criteria fails, the overall result is FAIL
        pass_decision = (
            cooling_metrics['start_temp_valid'] and
            cooling_metrics['cooling_rate_valid'] and 
            cooling_metrics['phase_1_pass'] and
            cooling_metrics['phase_2_pass'] and
            len(cooling_metrics['reasons']) == 0  # No failure reasons
        )
        
        # Explicitly ensure that if any failure condition exists, we return FAIL
        # This prevents any accidental PASS when cooling violations occur
        if (not cooling_metrics['start_temp_valid'] or 
            not cooling_metrics['cooling_rate_valid'] or
            not cooling_metrics['phase_1_pass'] or 
            not cooling_metrics['phase_2_pass'] or
            cooling_metrics['reasons']):  # Any reasons in cooling_metrics indicates failure
            pass_decision = False
        
        # Add success reasons if passed
        if pass_decision:
            if cooling_metrics['time_to_70f_s'] is not None:
                reasons.append(f"Phase 1 cooling: 135°F to 70°F in {cooling_metrics['time_to_70f_s']/3600:.1f}h ≤ 2h")
            if cooling_metrics['time_to_41f_s'] is not None:
                reasons.append(f"Phase 2 cooling: 135°F to 41°F in {cooling_metrics['time_to_41f_s']/3600:.1f}h ≤ 6h")
            reasons.append("HACCP cooling requirements met")
        else:
            # Add failure reasons
            reasons.extend(cooling_metrics['reasons'])
        
        # Check data quality warnings
        total_duration_h = cooling_metrics['total_duration_s'] / 3600
        if total_duration_h > 8:
            warnings.append(f"Cooling process duration ({total_duration_h:.1f}h) exceeds typical HACCP timeline")
        
        if cooling_metrics['min_temp_C'] < fahrenheit_to_celsius(35.0):  # Below 35°F
            warnings.append(f"Minimum temperature ({celsius_to_fahrenheit(cooling_metrics['min_temp_C']):.1f}°F) below typical food storage range")
        
        # Calculate hold time metrics (time spent in target range)
        target_temp_c = fahrenheit_to_celsius(41.0)  # Final target is 41°F
        actual_hold_time_s = 0.0
        if cooling_metrics['time_to_41f_s'] is not None:
            # Time spent at or below 41°F
            below_41f = combined_temp <= target_temp_c
            if below_41f.any():
                first_below_idx = below_41f.idxmax()
                hold_start_time = normalized_df[timestamp_col].iloc[first_below_idx]
                hold_end_time = normalized_df[timestamp_col].iloc[-1]
                actual_hold_time_s = (hold_end_time - hold_start_time).total_seconds()
        
        return DecisionResult(
            pass_=pass_decision,
            status="PASS" if pass_decision else "FAIL",
            job_id=spec.job.job_id,
            target_temp_C=target_temp_c,  # 41°F target
            conservative_threshold_C=target_temp_c,  # No uncertainty adjustment for HACCP
            actual_hold_time_s=actual_hold_time_s,
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=cooling_metrics['max_temp_C'],
            min_temp_C=cooling_metrics['min_temp_C'],
            reasons=reasons,
            warnings=warnings,
            industry=spec.industry
        )
    
    except RequiredSignalMissingError:
        # Re-raise RequiredSignalMissingError as-is for proper handling
        raise
    except Exception as e:
        logger.error(f"HACCP cooling validation failed: {e}")
        raise DecisionError(f"HACCP cooling validation failed: {str(e)}")


# Usage example in comments:
"""
Example usage for HACCP cooling validation:

from core.metrics_haccp import validate_haccp_cooling
from core.models import SpecV1
import pandas as pd

# Load HACCP specification
spec_data = {
    "version": "1.0",
    "industry": "haccp",
    "job": {"job_id": "restaurant_cooling_001"},
    "spec": {
        "method": "OVEN_AIR",
        "target_temp_C": 5.0,  # 41°F target
        "hold_time_s": 3600,   # 1 hour hold at final temp
        "sensor_uncertainty_C": 1.0
    },
    "data_requirements": {
        "max_sample_period_s": 60.0,
        "allowed_gaps_s": 120.0
    },
    "sensor_selection": {
        "mode": "mean_of_set",
        "require_at_least": 1
    }
}
spec = SpecV1(**spec_data)

# Load normalized cooling data
normalized_df = pd.read_csv("haccp_cooling_data.csv")

# Validate HACCP cooling
result = validate_haccp_cooling(normalized_df, spec)

print(f"HACCP Cooling Job {result.job_id}: {'PASS' if result.pass_ else 'FAIL'}")
print(f"Phase validation: {result.reasons}")
if result.warnings:
    print(f"Warnings: {result.warnings}")
"""