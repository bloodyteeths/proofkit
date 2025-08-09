"""
ProofKit Powder Coating Cure Validation Metrics Engine

Implements powder coating cure validation according to industry standards.
Validates cure process requirements:
- Target temperature achievement with sensor uncertainty
- Hold time requirements (continuous or cumulative)
- Ramp rate validation if specified
- Time to threshold validation

Example usage:
    from core.metrics_powder import validate_powder_coating_cure
    from core.models import SpecV1
    
    spec = SpecV1(**spec_data)  # Powder industry spec
    normalized_df = pd.read_csv("cure_data.csv")
    
    result = validate_powder_coating_cure(normalized_df, spec)
    print(f"Powder Cure: {'PASS' if result.pass_ else 'FAIL'}")
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from core.models import SpecV1, DecisionResult, SensorMode
from core.sensor_utils import combine_sensor_readings
from core.temperature_utils import detect_temperature_columns, DecisionError
from core.normalize import DataQualityError
from core.errors import RequiredSignalMissingError

logger = logging.getLogger(__name__)


def calculate_conservative_threshold(target_temp_C: float, sensor_uncertainty_C: float) -> float:
    """
    Calculate conservative threshold = target + sensor_uncertainty.
    
    Args:
        target_temp_C: Target temperature in Celsius
        sensor_uncertainty_C: Sensor uncertainty in Celsius
        
    Returns:
        Conservative threshold temperature in Celsius
    """
    # For powder coating, use target + sensor_uncertainty (conservative approach)
    return target_temp_C + sensor_uncertainty_C


def calculate_ramp_rate(temperature_series: pd.Series, time_series: pd.Series) -> pd.Series:
    """
    Calculate temperature ramp rate using central differences.
    
    Args:
        temperature_series: Temperature values
        time_series: Timestamp values
        
    Returns:
        Series of ramp rates in °C/min
    """
    # Convert timestamps to seconds since start
    time_seconds = (time_series - time_series.iloc[0]).dt.total_seconds()
    
    # Calculate temperature and time differences using central differences
    temp_diff = temperature_series.diff()
    time_diff = time_seconds.diff()
    
    # Calculate rate in °C/second, then convert to °C/minute
    ramp_rate_per_sec = temp_diff / time_diff
    ramp_rate_per_min = ramp_rate_per_sec * 60
    
    return ramp_rate_per_min


def find_threshold_crossing_time(temperature_series: pd.Series, time_series: pd.Series, 
                                threshold_C: float) -> Optional[float]:
    """
    Find the first time when temperature reaches or exceeds threshold.
    
    Args:
        temperature_series: Temperature values
        time_series: Timestamp values
        threshold_C: Threshold temperature
        
    Returns:
        Time to threshold in seconds, or None if threshold never reached
    """
    above_threshold = temperature_series >= threshold_C
    first_above_idx = above_threshold.idxmax() if above_threshold.any() else None
    
    if first_above_idx is None or not above_threshold.iloc[first_above_idx]:
        return None
    
    # Calculate time from start to threshold crossing
    start_time = time_series.iloc[0]
    threshold_time = time_series.iloc[first_above_idx]
    time_to_threshold = (threshold_time - start_time).total_seconds()
    
    return time_to_threshold


def calculate_continuous_hold_time(temperature_series: pd.Series, time_series: pd.Series,
                                 threshold_C: float, hysteresis_C: float = 2.0) -> Tuple[float, int, int]:
    """
    Calculate the longest continuous hold time above threshold with hysteresis.
    Uses run-length encoding to find max contiguous duration above threshold - hysteresis.
    
    Args:
        temperature_series: Temperature values
        time_series: Timestamp values  
        threshold_C: Threshold temperature
        hysteresis_C: Hysteresis amount for threshold crossings
        
    Returns:
        Tuple of (longest_hold_time_s, start_idx, end_idx)
    """
    if len(temperature_series) < 2:
        return 0.0, -1, -1
    
    # Resample to fixed step (assumes normalized data is already uniform)
    # Create boolean mask for temp >= threshold - hysteresis
    hold_threshold = threshold_C - hysteresis_C
    above_hold_threshold = temperature_series >= hold_threshold
    
    # Convert to numpy for efficient run-length computation
    mask_array = above_hold_threshold.values
    
    # Run-length encoding to find contiguous True segments
    if not mask_array.any():
        return 0.0, -1, -1
    
    # Find run boundaries using diff
    boundaries = np.diff(np.concatenate([[False], mask_array, [False]]).astype(int))
    run_starts = np.where(boundaries == 1)[0]
    run_ends = np.where(boundaries == -1)[0]
    
    # Calculate durations for each run
    if len(run_starts) == 0:
        return 0.0, -1, -1
    
    max_duration = 0.0
    max_start_idx = -1
    max_end_idx = -1
    
    for start_idx, end_idx in zip(run_starts, run_ends):
        # end_idx is exclusive, so actual end is end_idx - 1
        actual_end_idx = end_idx - 1
        
        # Calculate duration including both endpoints
        start_time = time_series.iloc[start_idx]
        end_time = time_series.iloc[actual_end_idx]
        duration = (end_time - start_time).total_seconds()
        
        if duration > max_duration:
            max_duration = duration
            max_start_idx = start_idx
            max_end_idx = actual_end_idx
    
    return max_duration, max_start_idx, max_end_idx


def calculate_cumulative_hold_time(temperature_series: pd.Series, time_series: pd.Series,
                                 threshold_C: float, max_total_dips_s: int) -> Tuple[float, List[Tuple[int, int]]]:
    """
    Calculate cumulative hold time above threshold using sum-above-threshold with allowed dips.
    
    Args:
        temperature_series: Temperature values
        time_series: Timestamp values
        threshold_C: Threshold temperature
        max_total_dips_s: Maximum total time below threshold allowed
        
    Returns:
        Tuple of (cumulative_hold_time_s, intervals_list)
    """
    if len(temperature_series) < 2:
        return 0.0, []
    
    # Create boolean mask for temperatures above threshold
    above_threshold = temperature_series >= threshold_C
    
    # Calculate time intervals (assuming uniform sampling from normalizer)
    time_diffs = time_series.diff().dt.total_seconds().fillna(0)
    
    # Sum all time spent above threshold (cumulative approach)
    total_above_time = 0.0
    intervals_above = []
    
    # Track intervals for reporting
    current_interval_start = None
    
    for i in range(len(above_threshold)):
        if above_threshold.iloc[i]:
            # Point is above threshold
            if current_interval_start is None:
                current_interval_start = i
            
            # Add time contribution (except for first point)
            if i > 0:
                total_above_time += time_diffs.iloc[i]
        else:
            # Point is below threshold
            if current_interval_start is not None:
                # End current interval
                intervals_above.append((current_interval_start, i - 1))
                current_interval_start = None
    
    # Handle case where we end while above threshold
    if current_interval_start is not None:
        intervals_above.append((current_interval_start, len(above_threshold) - 1))
    
    # Calculate total dip time
    total_dip_time = 0.0
    for i in range(len(above_threshold)):
        if not above_threshold.iloc[i] and i > 0:
            total_dip_time += time_diffs.iloc[i]
    
    # If dips exceed allowance, reduce cumulative time proportionally
    if total_dip_time > max_total_dips_s:
        # Reduce cumulative time by excess dip amount
        excess_dip_time = total_dip_time - max_total_dips_s
        total_above_time = max(0.0, total_above_time - excess_dip_time)
    
    return total_above_time, intervals_above


def validate_powder_coating_cure(normalized_df: pd.DataFrame, spec: SpecV1) -> DecisionResult:
    """
    Validate powder coating cure process based on normalized data and specification.
    
    Args:
        normalized_df: Normalized temperature data from core.normalize.py
        spec: Powder coating industry specification
        
    Returns:
        DecisionResult with powder coating-specific pass/fail status and detailed metrics
        
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
            raise DecisionError("Insufficient data points for powder coating cure analysis")
            
        if spec.industry not in ["powder", "powder-coating"]:
            raise DecisionError(f"Invalid industry '{spec.industry}' for powder coating validation")
        
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
        
        # Detect temperature columns EARLY and check sensor requirements
        temp_columns = detect_temperature_columns(normalized_df)
        if not temp_columns:
            # For powder industry, missing temperature columns is an ERROR
            available_cols = [col for col in normalized_df.columns if col != timestamp_col]
            raise RequiredSignalMissingError(
                missing_signals=["temperature"],
                available_signals=available_cols,
                industry="powder"
            )
        
        # Check sensor requirements early for powder industry (before data point checks)
        sensor_selection = spec.sensor_selection
        if sensor_selection and sensor_selection.require_at_least:
            if len(temp_columns) < sensor_selection.require_at_least:
                raise RequiredSignalMissingError(
                    missing_signals=[f"{sensor_selection.require_at_least - len(temp_columns)} additional temperature sensors"],
                    available_signals=temp_columns,
                    industry="powder"
                )
        
        # Check for minimum data points needed for reliable decision
        required_hold_time_s = spec.spec.hold_time_s
        sample_period_s = 30.0  # Assume 30s intervals for normalized data
        min_points_needed = max(5, int(required_hold_time_s / sample_period_s) + 2)
        
        if len(normalized_df) < min_points_needed:
            reasons.append(f"Insufficient data points for reliable analysis: {len(normalized_df)} points, need at least {min_points_needed}")
            return DecisionResult(
                pass_=False,
                status="FAIL",  # For powder industry, insufficient data is FAIL not INDETERMINATE
                job_id=spec.job.job_id,
                target_temp_C=spec.spec.target_temp_C,
                conservative_threshold_C=calculate_conservative_threshold(
                    spec.spec.target_temp_C, spec.spec.sensor_uncertainty_C
                ),
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=0.0,
                min_temp_C=0.0,
                reasons=reasons,
                warnings=warnings,
                industry=spec.industry
            )
        
        # Handle specific sensor selection if provided
        if sensor_selection and sensor_selection.sensors:
            # Use specified sensors when present; warn if missing
            available_sensors = [col for col in sensor_selection.sensors if col in temp_columns]
            if not available_sensors:
                warnings.append(
                    f"Specified sensors not found: {sensor_selection.sensors}. Using auto-detected sensors: {temp_columns}"
                )
            else:
                temp_columns = available_sensors
        
        # Check for all-NaN sensors (sensor failure)
        all_nan_sensors = []
        for col in temp_columns:
            if normalized_df[col].isna().all():
                all_nan_sensors.append(col)
        
        if all_nan_sensors == temp_columns:
            # For powder industry, all sensor failure is an ERROR
            raise RequiredSignalMissingError(
                missing_signals=["functional temperature sensors (all NaN values detected)"],
                available_signals=temp_columns,
                industry="powder"
            )
        
        if all_nan_sensors:
            warnings.append(f"Sensor failure detected: {all_nan_sensors} have all NaN values")
            # Remove failed sensors
            temp_columns = [col for col in temp_columns if col not in all_nan_sensors]
        
        # Calculate conservative threshold
        # For powder coating, always use target + sensor_uncertainty as per CLAUDE.md
        conservative_threshold_C = calculate_conservative_threshold(
            spec.spec.target_temp_C, 
            spec.spec.sensor_uncertainty_C
        )
        
        # Combine sensor readings (typically MIN_OF_SET for powder coating conservative validation)
        sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MIN_OF_SET
        require_at_least = sensor_selection.require_at_least if sensor_selection else None
        
        try:
            combined_pmt = combine_sensor_readings(
                normalized_df, temp_columns, sensor_mode, require_at_least, conservative_threshold_C
            )
        except DecisionError as e:
            # For powder industry, sensor combination failure is an ERROR
            raise RequiredSignalMissingError(
                missing_signals=["combinable temperature sensors"],
                available_signals=temp_columns,
                industry="powder"
            )
        
        # Calculate basic metrics
        max_temp_C = float(combined_pmt.max())
        min_temp_C = float(combined_pmt.min())
        threshold_reached = (combined_pmt >= conservative_threshold_C).any()
        
        # Check if threshold was ever reached
        if not threshold_reached:
            reasons.append(f"Temperature never reached conservative threshold of {conservative_threshold_C:.1f}°C")
            reasons.append(f"Maximum temperature recorded: {max_temp_C:.1f}°C")
            
            return DecisionResult(
                pass_=False,
                status="FAIL",
                job_id=spec.job.job_id,
                target_temp_C=spec.spec.target_temp_C,
                conservative_threshold_C=conservative_threshold_C,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=max_temp_C,
                min_temp_C=min_temp_C,
                reasons=reasons,
                warnings=warnings
            )
        
        # Get logic configuration with defaults
        logic_continuous = True
        logic_max_dips = 0
        if spec.logic:
            logic_continuous = spec.logic.continuous
            logic_max_dips = spec.logic.max_total_dips_s
        
        # Validate preconditions if specified  
        precondition_failures = []
        if spec.preconditions:
            # Check ramp rate only if specified (avoid tripping PASS when not present)
            if hasattr(spec.preconditions, 'max_ramp_rate_C_per_min') and spec.preconditions.max_ramp_rate_C_per_min is not None:
                ramp_rates = calculate_ramp_rate(combined_pmt, normalized_df[timestamp_col])
                max_ramp_rate = ramp_rates.max()
                
                if max_ramp_rate > spec.preconditions.max_ramp_rate_C_per_min:
                    precondition_failures.append(f"Ramp rate too high: {max_ramp_rate:.1f}°C/min > {spec.preconditions.max_ramp_rate_C_per_min}°C/min")
            
            # Check time to threshold only if specified
            if hasattr(spec.preconditions, 'max_time_to_threshold_s') and spec.preconditions.max_time_to_threshold_s is not None:
                time_to_threshold = find_threshold_crossing_time(
                    combined_pmt, normalized_df[timestamp_col], conservative_threshold_C
                )
                
                if time_to_threshold is not None:
                    if time_to_threshold > spec.preconditions.max_time_to_threshold_s:
                        precondition_failures.append(f"Time to threshold too long: {time_to_threshold:.0f}s > {spec.preconditions.max_time_to_threshold_s}s")
        
        # Calculate hold time based on logic mode
        if logic_continuous:
            # Continuous hold logic
            actual_hold_time_s, start_idx, end_idx = calculate_continuous_hold_time(
                combined_pmt, normalized_df[timestamp_col], conservative_threshold_C
            )
            
            if actual_hold_time_s >= spec.spec.hold_time_s:
                reasons.append(f"Continuous hold time requirement met: {actual_hold_time_s:.0f}s ≥ {spec.spec.hold_time_s}s")
                hold_requirement_met = True
            else:
                reasons.append(f"Insufficient continuous hold time: {actual_hold_time_s:.0f}s < {spec.spec.hold_time_s}s")
                hold_requirement_met = False
        else:
            # Cumulative hold logic
            actual_hold_time_s, intervals = calculate_cumulative_hold_time(
                combined_pmt, normalized_df[timestamp_col], 
                conservative_threshold_C, logic_max_dips
            )
            
            if actual_hold_time_s >= spec.spec.hold_time_s:
                reasons.append(f"Cumulative hold time requirement met: {actual_hold_time_s:.0f}s ≥ {spec.spec.hold_time_s}s")
                hold_requirement_met = True
            else:
                reasons.append(f"Insufficient cumulative hold time: {actual_hold_time_s:.0f}s < {spec.spec.hold_time_s}s")
                hold_requirement_met = False
        
        # Add precondition failures to reasons
        reasons.extend(precondition_failures)
        
        # Determine overall pass/fail status
        pass_decision = hold_requirement_met and len(precondition_failures) == 0
        
        return DecisionResult(
            pass_=pass_decision,
            status="PASS" if pass_decision else "FAIL",
            job_id=spec.job.job_id,
            target_temp_C=spec.spec.target_temp_C,
            conservative_threshold_C=conservative_threshold_C,
            actual_hold_time_s=actual_hold_time_s,
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=max_temp_C,
            min_temp_C=min_temp_C,
            reasons=reasons,
            warnings=warnings,
            industry=spec.industry
        )
    
    except RequiredSignalMissingError:
        # Re-raise RequiredSignalMissingError without wrapping
        raise
    except DataQualityError:
        # Re-raise DataQualityError as-is since it's an expected error type
        raise
    except Exception as e:
        logger.error(f"Powder coating cure validation failed: {e}")
        raise DecisionError(f"Powder coating cure validation failed: {str(e)}")


# Usage example in comments:
"""
Example usage for powder coating cure validation:

from core.metrics_powder import validate_powder_coating_cure
from core.models import SpecV1
import pandas as pd

# Load powder coating specification
spec_data = {
    "version": "1.0",
    "industry": "powder-coating",
    "job": {"job_id": "powder_batch_001"},
    "spec": {
        "method": "PMT",
        "target_temp_C": 180.0,
        "hold_time_s": 600,
        "sensor_uncertainty_C": 2.0
    },
    "data_requirements": {
        "max_sample_period_s": 30.0,
        "allowed_gaps_s": 60.0
    },
    "sensor_selection": {
        "mode": "min_of_set",
        "require_at_least": 1
    },
    "logic": {
        "continuous": True,
        "max_total_dips_s": 0
    },
    "preconditions": {
        "max_ramp_rate_C_per_min": 10.0,
        "max_time_to_threshold_s": 300
    }
}
spec = SpecV1(**spec_data)

# Load normalized cure data
normalized_df = pd.read_csv("powder_cure_data.csv")

# Validate powder coating cure
result = validate_powder_coating_cure(normalized_df, spec)

print(f"Powder Cure Job {result.job_id}: {'PASS' if result.pass_ else 'FAIL'}")
print(f"Hold time: {result.actual_hold_time_s:.0f}s / {result.required_hold_time_s}s")
print(f"Validation: {result.reasons}")
if result.warnings:
    print(f"Warnings: {result.warnings}")
"""