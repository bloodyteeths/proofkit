"""
ProofKit Decision Algorithm

Implements the decision algorithm for powder-coat cure validation according to
ROADMAP M2 requirements and CLAUDE.md principles. Processes normalized CSV data
against specifications to determine pass/fail status with detailed reasoning.

Example usage:
    from core.decide import make_decision
    from core.models import SpecV1
    
    # Load normalized data and spec
    spec = SpecV1(**spec_data)
    normalized_df = pd.read_csv("normalized.csv")
    
    # Make decision
    result = make_decision(normalized_df, spec)
    print(f"Decision: {'PASS' if result.pass_ else 'FAIL'}")
    print(f"Hold time: {result.actual_hold_time_s:.1f}s")
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from core.models import SpecV1, DecisionResult, SensorMode

logger = logging.getLogger(__name__)


class DecisionError(Exception):
    """Raised when decision algorithm encounters fatal errors."""
    pass


def calculate_conservative_threshold(target_temp_C: float, sensor_uncertainty_C: float) -> float:
    """
    Calculate conservative threshold = target + sensor_uncertainty.
    
    Args:
        target_temp_C: Target temperature in Celsius
        sensor_uncertainty_C: Sensor uncertainty in Celsius
        
    Returns:
        Conservative threshold temperature in Celsius
    """
    return target_temp_C + sensor_uncertainty_C


def combine_sensor_readings(df: pd.DataFrame, temp_columns: List[str], 
                          mode: SensorMode, require_at_least: Optional[int] = None,
                          threshold_C: Optional[float] = None) -> pd.Series:
    """
    Combine multiple sensor readings according to the specified mode.
    
    Args:
        df: DataFrame with temperature data
        temp_columns: List of temperature column names
        mode: Sensor combination mode
        require_at_least: Minimum number of valid sensors required
        threshold_C: Threshold for majority_over_threshold mode
        
    Returns:
        Series of combined temperature readings (PMT)
        
    Raises:
        DecisionError: If insufficient valid sensors or invalid mode
    """
    if not temp_columns:
        raise DecisionError("No temperature columns provided for sensor combination")
    
    # Extract temperature data
    temp_data = df[temp_columns].copy()
    
    # Check minimum sensor requirement
    if require_at_least is not None:
        valid_sensors_per_sample = temp_data.notna().sum(axis=1)
        insufficient_samples = valid_sensors_per_sample < require_at_least
        if insufficient_samples.any():
            count = insufficient_samples.sum()
            raise DecisionError(f"Insufficient valid sensors: {count} samples have < {require_at_least} sensors")
    
    if mode == SensorMode.MIN_OF_SET:
        # Take minimum reading across all sensors
        return temp_data.min(axis=1, skipna=True)
    
    elif mode == SensorMode.MEAN_OF_SET:
        # Take mean reading across all sensors
        return temp_data.mean(axis=1, skipna=True)
    
    elif mode == SensorMode.MAJORITY_OVER_THRESHOLD:
        if threshold_C is None:
            raise DecisionError("threshold_C required for majority_over_threshold mode")
        
        # Count sensors above threshold for each sample
        above_threshold = temp_data >= threshold_C
        sensors_above = above_threshold.sum(axis=1)
        total_sensors = temp_data.notna().sum(axis=1)
        
        # Majority decision: if >50% of sensors are above threshold, use min of those above
        # Otherwise, use max of all sensors (conservative approach)
        majority_above = sensors_above > (total_sensors / 2)
        
        result = pd.Series(index=df.index, dtype=float)
        
        for idx in df.index:
            if majority_above.iloc[idx]:
                # Use minimum of sensors above threshold
                above_mask = above_threshold.iloc[idx]
                result.iloc[idx] = temp_data.iloc[idx][above_mask].min()
            else:
                # Use maximum of all sensors (most conservative)
                result.iloc[idx] = temp_data.iloc[idx].max()
        
        return result
    
    else:
        raise DecisionError(f"Unknown sensor combination mode: {mode}")


def detect_temperature_columns(df: pd.DataFrame) -> List[str]:
    """
    Detect temperature columns in the DataFrame.
    
    Args:
        df: Input DataFrame
        
    Returns:
        List of temperature column names
    """
    import re
    
    temp_patterns = [
        r'.*temp.*', r'.*temperature.*', r'.*pmt.*', r'.*sensor.*',
        r'.*°[cf].*', r'.*deg[cf].*', r'.*_c$', r'.*_f$'
    ]
    
    temp_columns = []
    
    for col in df.columns:
        if col.lower() == 'timestamp' or 'time' in col.lower():
            continue
            
        col_lower = col.lower()
        if any(re.match(pattern, col_lower) for pattern in temp_patterns):
            # Verify it's numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                temp_columns.append(col)
    
    return temp_columns


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
    
    # Apply hysteresis: once above threshold, stay "above" until below (threshold - hysteresis)
    above_threshold = np.zeros(len(temperature_series), dtype=bool)
    currently_above = False
    
    for i, temp in enumerate(temperature_series):
        if not currently_above:
            # Not currently above - check if we cross threshold
            if temp >= threshold_C:
                currently_above = True
                above_threshold[i] = True
            else:
                above_threshold[i] = False
        else:
            # Currently above - check if we fall below hysteresis point
            if temp < (threshold_C - hysteresis_C):
                currently_above = False
                above_threshold[i] = False
            else:
                above_threshold[i] = True
    
    # Find continuous intervals above threshold
    intervals = []
    start_idx = None
    
    for i, is_above in enumerate(above_threshold):
        if is_above and start_idx is None:
            # Start of interval
            start_idx = i
        elif not is_above and start_idx is not None:
            # End of interval
            intervals.append((start_idx, i - 1))
            start_idx = None
    
    # Handle case where we end while still above threshold
    if start_idx is not None:
        intervals.append((start_idx, len(above_threshold) - 1))
    
    # Find longest interval
    if not intervals:
        return 0.0, -1, -1
    
    longest_duration = 0.0
    longest_start = -1
    longest_end = -1
    
    for start_idx, end_idx in intervals:
        start_time = time_series.iloc[start_idx]
        end_time = time_series.iloc[end_idx]
        duration = (end_time - start_time).total_seconds()
        
        if duration > longest_duration:
            longest_duration = duration
            longest_start = start_idx
            longest_end = end_idx
    
    return longest_duration, longest_start, longest_end


def calculate_cumulative_hold_time(temperature_series: pd.Series, time_series: pd.Series,
                                 threshold_C: float, max_total_dips_s: int) -> Tuple[float, List[Tuple[int, int]]]:
    """
    Calculate cumulative hold time above threshold allowing for brief dips.
    
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
    
    above_threshold = temperature_series >= threshold_C
    intervals_above = []
    intervals_below = []
    
    # Find all intervals above and below threshold
    current_state = above_threshold.iloc[0]
    start_idx = 0
    
    for i in range(1, len(above_threshold)):
        if above_threshold.iloc[i] != current_state:
            # State change
            if current_state:
                # Was above, now below
                intervals_above.append((start_idx, i - 1))
            else:
                # Was below, now above
                intervals_below.append((start_idx, i - 1))
            
            start_idx = i
            current_state = above_threshold.iloc[i]
    
    # Handle final interval
    if current_state:
        intervals_above.append((start_idx, len(above_threshold) - 1))
    else:
        intervals_below.append((start_idx, len(above_threshold) - 1))
    
    # Calculate total time below threshold
    total_dip_time = 0.0
    for start_idx, end_idx in intervals_below:
        start_time = time_series.iloc[start_idx]
        end_time = time_series.iloc[end_idx]
        dip_duration = (end_time - start_time).total_seconds()
        total_dip_time += dip_duration
    
    # If total dips exceed limit, only count time above until limit exceeded
    if total_dip_time > max_total_dips_s:
        # Need to find partial intervals that fit within dip limit
        # This is a simplified approach - could be more sophisticated
        cumulative_hold = 0.0
        used_dip_time = 0.0
        
        # Sort all intervals by start time
        all_intervals = [(start, end, True) for start, end in intervals_above] + \
                       [(start, end, False) for start, end in intervals_below]
        all_intervals.sort(key=lambda x: x[0])
        
        valid_intervals_above = []
        
        for start_idx, end_idx, is_above in all_intervals:
            if is_above:
                # Above threshold interval
                start_time = time_series.iloc[start_idx]
                end_time = time_series.iloc[end_idx]
                duration = (end_time - start_time).total_seconds()
                cumulative_hold += duration
                valid_intervals_above.append((start_idx, end_idx))
            else:
                # Below threshold interval - check if we can afford it
                start_time = time_series.iloc[start_idx]
                end_time = time_series.iloc[end_idx]
                duration = (end_time - start_time).total_seconds()
                
                if used_dip_time + duration <= max_total_dips_s:
                    used_dip_time += duration
                else:
                    # Exceeded dip allowance - stop counting
                    break
        
        return cumulative_hold, valid_intervals_above
    else:
        # All dips are within allowance
        total_hold_time = 0.0
        for start_idx, end_idx in intervals_above:
            start_time = time_series.iloc[start_idx]
            end_time = time_series.iloc[end_idx]
            duration = (end_time - start_time).total_seconds()
            total_hold_time += duration
        
        return total_hold_time, intervals_above


def make_decision(normalized_df: pd.DataFrame, spec: SpecV1) -> DecisionResult:
    """
    Make cure process decision based on normalized data and specification.
    
    Args:
        normalized_df: Normalized temperature data from core.normalize.py
        spec: Cure process specification
        
    Returns:
        DecisionResult with pass/fail status and detailed metrics
        
    Raises:
        DecisionError: If decision cannot be made due to data issues
    """
    try:
        # Initialize result tracking
        reasons = []
        warnings = []
        metrics = {}
        
        # Validate inputs
        if normalized_df.empty:
            raise DecisionError("Normalized DataFrame is empty")
        
        if len(normalized_df) < 2:
            raise DecisionError("Insufficient data points for decision analysis")
        
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
        
        # Get sensor selection configuration
        sensor_selection = spec.sensor_selection
        if sensor_selection and sensor_selection.sensors:
            # Use specified sensors
            available_sensors = [col for col in sensor_selection.sensors if col in temp_columns]
            if not available_sensors:
                raise DecisionError(f"None of specified sensors found in data: {sensor_selection.sensors}")
            temp_columns = available_sensors
            
            if sensor_selection.require_at_least and len(available_sensors) < sensor_selection.require_at_least:
                warnings.append(f"Only {len(available_sensors)} sensors available, {sensor_selection.require_at_least} required")
        
        # Calculate conservative threshold
        conservative_threshold_C = calculate_conservative_threshold(
            spec.spec.target_temp_C, 
            spec.spec.sensor_uncertainty_C
        )
        
        # Combine sensor readings
        sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MIN_OF_SET
        require_at_least = sensor_selection.require_at_least if sensor_selection else None
        
        try:
            combined_pmt = combine_sensor_readings(
                normalized_df, temp_columns, sensor_mode, require_at_least, conservative_threshold_C
            )
        except DecisionError as e:
            reasons.append(f"Sensor combination failed: {str(e)}")
            return DecisionResult(
                pass_=False,
                job_id=spec.job.job_id,
                target_temp_C=spec.spec.target_temp_C,
                conservative_threshold_C=conservative_threshold_C,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=0.0,
                min_temp_C=0.0,
                reasons=reasons,
                warnings=warnings
            )
        
        # Calculate basic metrics
        max_temp_C = float(combined_pmt.max())
        min_temp_C = float(combined_pmt.min())
        
        # Check if threshold is ever reached
        threshold_reached = (combined_pmt >= conservative_threshold_C).any()
        if not threshold_reached:
            reasons.append(f"Temperature never reached conservative threshold of {conservative_threshold_C:.1f}°C")
            reasons.append(f"Maximum temperature recorded: {max_temp_C:.1f}°C")
            
            return DecisionResult(
                pass_=False,
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
        if spec.logic:
            logic_continuous = spec.logic.continuous
            logic_max_dips = spec.logic.max_total_dips_s
        else:
            logic_continuous = True
            logic_max_dips = 0
        
        preconditions = spec.preconditions
        
        if preconditions:
            # Check ramp rate
            if preconditions.max_ramp_rate_C_per_min is not None:
                ramp_rates = calculate_ramp_rate(combined_pmt, normalized_df[timestamp_col])
                max_ramp_rate = ramp_rates.max()
                
                if max_ramp_rate > preconditions.max_ramp_rate_C_per_min:
                    reasons.append(f"Ramp rate too high: {max_ramp_rate:.1f}°C/min > {preconditions.max_ramp_rate_C_per_min}°C/min")
                
                metrics['max_ramp_rate_C_per_min'] = float(max_ramp_rate)
            
            # Check time to threshold
            if preconditions.max_time_to_threshold_s is not None:
                time_to_threshold = find_threshold_crossing_time(
                    combined_pmt, normalized_df[timestamp_col], conservative_threshold_C
                )
                
                if time_to_threshold is not None:
                    if time_to_threshold > preconditions.max_time_to_threshold_s:
                        reasons.append(f"Time to threshold too long: {time_to_threshold:.0f}s > {preconditions.max_time_to_threshold_s}s")
                    
                    metrics['time_to_threshold_s'] = time_to_threshold
        
        # Calculate hold time based on logic mode
        if logic_continuous:
            # Continuous hold logic
            actual_hold_time_s, start_idx, end_idx = calculate_continuous_hold_time(
                combined_pmt, normalized_df[timestamp_col], conservative_threshold_C
            )
            
            if actual_hold_time_s >= spec.spec.hold_time_s:
                reasons.append(f"Continuous hold time requirement met: {actual_hold_time_s:.0f}s ≥ {spec.spec.hold_time_s}s")
                pass_decision = len(reasons) == 1  # Only pass if this is the only reason (no precondition failures)
            else:
                reasons.append(f"Insufficient continuous hold time: {actual_hold_time_s:.0f}s < {spec.spec.hold_time_s}s")
                pass_decision = False
        else:
            # Cumulative hold logic
            actual_hold_time_s, intervals = calculate_cumulative_hold_time(
                combined_pmt, normalized_df[timestamp_col], 
                conservative_threshold_C, logic_max_dips
            )
            
            if actual_hold_time_s >= spec.spec.hold_time_s:
                reasons.append(f"Cumulative hold time requirement met: {actual_hold_time_s:.0f}s ≥ {spec.spec.hold_time_s}s")
                pass_decision = len([r for r in reasons if 'too high' in r or 'too long' in r]) == 0  # No precondition failures
            else:
                reasons.append(f"Insufficient cumulative hold time: {actual_hold_time_s:.0f}s < {spec.spec.hold_time_s}s")
                pass_decision = False
        
        # Add additional metrics
        metrics.update({
            'sensor_mode': sensor_mode.value,
            'sensors_used': temp_columns,
            'data_points': len(normalized_df),
            'duration_total_s': (normalized_df[timestamp_col].iloc[-1] - normalized_df[timestamp_col].iloc[0]).total_seconds()
        })
        
        return DecisionResult(
            pass_=pass_decision,
            job_id=spec.job.job_id,
            target_temp_C=spec.spec.target_temp_C,
            conservative_threshold_C=conservative_threshold_C,
            actual_hold_time_s=actual_hold_time_s,
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=max_temp_C,
            min_temp_C=min_temp_C,
            reasons=reasons,
            warnings=warnings
        )
    
    except Exception as e:
        logger.error(f"Decision algorithm failed: {e}")
        raise DecisionError(f"Decision algorithm failed: {str(e)}")


# Usage example in comments:
"""
Example usage for ProofKit decision algorithm:

from core.decide import make_decision
from core.models import SpecV1
import pandas as pd

# Load specification
spec_data = {
    "version": "1.0",
    "job": {"job_id": "batch_001"},
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
spec = SpecV1(**spec_data)

# Load normalized data
normalized_df = pd.read_csv("normalized.csv")

# Make decision
result = make_decision(normalized_df, spec)

print(f"Job {result.job_id}: {'PASS' if result.pass_ else 'FAIL'}")
print(f"Hold time: {result.actual_hold_time_s:.1f}s / {result.required_hold_time_s}s")
print(f"Reasons: {result.reasons}")
if result.warnings:
    print(f"Warnings: {result.warnings}")
"""