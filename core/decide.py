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
from typing import List, Tuple, Dict, Any, Optional, Callable
from datetime import datetime, timezone
import logging

from core.models import SpecV1, DecisionResult, SensorMode

logger = logging.getLogger(__name__)


# Industry-specific metric engine imports
try:
    from core.metrics_haccp import validate_haccp_cooling
    from core.metrics_autoclave import validate_autoclave_sterilization
    from core.metrics_sterile import validate_eto_sterilization
    from core.metrics_concrete import validate_concrete_curing
    from core.metrics_coldchain import validate_coldchain_storage
except ImportError as e:
    logger.warning(f"Failed to import industry-specific metrics engines: {e}")
    # Set to None so we can check for availability
    validate_haccp_cooling = None
    validate_autoclave_sterilization = None
    validate_eto_sterilization = None
    validate_concrete_curing = None
    validate_coldchain_storage = None


# Industry-specific metrics engine dispatch table
INDUSTRY_METRICS: Dict[str, Optional[Callable[[pd.DataFrame, SpecV1], DecisionResult]]] = {
    "powder": None,  # Uses default powder coat logic in make_decision
    "haccp": validate_haccp_cooling,
    "autoclave": validate_autoclave_sterilization,
    "sterile": validate_eto_sterilization,
    "concrete": validate_concrete_curing,
    "coldchain": validate_coldchain_storage,
}


class DecisionError(Exception):
    """Raised when decision algorithm encounters fatal errors."""
    pass


def validate_preconditions(df: pd.DataFrame, spec: SpecV1) -> Tuple[bool, List[str]]:
    """
    Validate preconditions for decision algorithm.
    
    Args:
        df: Normalized DataFrame with temperature data
        spec: Process specification
        
    Returns:
        Tuple of (all_valid, list_of_issues)
    """
    issues = []
    
    if df.empty:
        issues.append("DataFrame is empty")
        return False, issues
    
    if len(df) < 2:
        issues.append("Insufficient data points for analysis")
        return False, issues
    
    # Check for required columns
    timestamp_col = None
    for col in df.columns:
        if 'time' in col.lower() or pd.api.types.is_datetime64_any_dtype(df[col]):
            timestamp_col = col
            break
    
    if timestamp_col is None:
        issues.append("No timestamp column found")
        return False, issues
    
    # Check for temperature columns
    temp_columns = detect_temperature_columns(df)
    if not temp_columns:
        issues.append("No temperature columns found")
        return False, issues
    
    # Check sensor selection requirements
    if spec.sensor_selection and spec.sensor_selection.sensors:
        available_sensors = [col for col in spec.sensor_selection.sensors if col in temp_columns]
        if not available_sensors:
            issues.append(f"None of specified sensors found: {spec.sensor_selection.sensors}")
            return False, issues
        
        if (spec.sensor_selection.require_at_least and 
            len(available_sensors) < spec.sensor_selection.require_at_least):
            issues.append(f"Insufficient sensors: {len(available_sensors)} < {spec.sensor_selection.require_at_least}")
            return False, issues
    
    return len(issues) == 0, issues


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
        
        # Check if at least 'require_at_least' sensors are above threshold
        if require_at_least is not None:
            # Return boolean series: True if enough sensors are above threshold
            return sensors_above >= require_at_least
        else:
            # Majority decision: True if >50% of sensors are above threshold
            return sensors_above > (total_sensors / 2)
    
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


def calculate_boolean_hold_time(boolean_series: pd.Series, time_series: pd.Series,
                               continuous: bool = True, max_dips_s: int = 0) -> float:
    """
    Calculate hold time for boolean sensor combination results.
    
    Args:
        boolean_series: Boolean series where True indicates threshold met
        time_series: Timestamp values
        continuous: If True, calculate longest continuous True period
        max_dips_s: Maximum allowed False time for cumulative mode
        
    Returns:
        Hold time in seconds
    """
    if len(boolean_series) < 2:
        return 0.0
    
    if continuous:
        # Find longest continuous True period
        intervals = []
        start_idx = None
        
        for i, is_true in enumerate(boolean_series):
            if is_true and start_idx is None:
                start_idx = i
            elif not is_true and start_idx is not None:
                intervals.append((start_idx, i - 1))
                start_idx = None
        
        # Handle case where we end while True
        if start_idx is not None:
            intervals.append((start_idx, len(boolean_series) - 1))
        
        if not intervals:
            return 0.0
        
        # Find longest interval
        longest_duration = 0.0
        for start_idx, end_idx in intervals:
            start_time = time_series.iloc[start_idx]
            end_time = time_series.iloc[end_idx]
            duration = (end_time - start_time).total_seconds()
            longest_duration = max(longest_duration, duration)
        
        return longest_duration
    
    else:
        # Cumulative mode - sum all True periods if total False time <= max_dips_s
        false_intervals = []
        true_intervals = []
        
        current_state = boolean_series.iloc[0]
        start_idx = 0
        
        for i in range(1, len(boolean_series)):
            if boolean_series.iloc[i] != current_state:
                if current_state:
                    true_intervals.append((start_idx, i - 1))
                else:
                    false_intervals.append((start_idx, i - 1))
                start_idx = i
                current_state = boolean_series.iloc[i]
        
        # Handle final interval
        if current_state:
            true_intervals.append((start_idx, len(boolean_series) - 1))
        else:
            false_intervals.append((start_idx, len(boolean_series) - 1))
        
        # Calculate total False time
        total_false_time = 0.0
        for start_idx, end_idx in false_intervals:
            start_time = time_series.iloc[start_idx]
            end_time = time_series.iloc[end_idx]
            total_false_time += (end_time - start_time).total_seconds()
        
        # If False time exceeds limit, return 0
        if total_false_time > max_dips_s:
            return 0.0
        
        # Sum all True periods
        total_true_time = 0.0
        for start_idx, end_idx in true_intervals:
            start_time = time_series.iloc[start_idx]
            end_time = time_series.iloc[end_idx]
            total_true_time += (end_time - start_time).total_seconds()
        
        return total_true_time


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
    Make process validation decision based on normalized data and specification.
    
    Dispatches to industry-specific validation engines based on spec.industry.
    Falls back to default powder coat validation for unknown industries.
    
    Args:
        normalized_df: Normalized process data from core.normalize.py
        spec: Industry-specific process specification
        
    Returns:
        DecisionResult with pass/fail status and detailed metrics
        
    Raises:
        DecisionError: If decision cannot be made due to data issues
    """
    # Check for industry-specific validation engine
    industry = spec.industry.lower() if spec.industry else "powder"
    
    if industry in INDUSTRY_METRICS and INDUSTRY_METRICS[industry] is not None:
        # Use industry-specific validation engine
        logger.info(f"Using {industry} industry validation engine")
        try:
            return INDUSTRY_METRICS[industry](normalized_df, spec)
        except Exception as e:
            logger.error(f"Industry-specific validation failed for {industry}: {e}")
            # Fall back to default validation if industry-specific fails
            logger.info("Falling back to default powder coat validation")
    
    # Default powder coat validation logic (original make_decision implementation)
    logger.info(f"Using default powder coat validation for industry: {industry}")
    
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
        
        # Check for minimum data points needed for reliable decision
        # Need at least enough points for hold time analysis
        required_hold_time_s = spec.spec.hold_time_s
        sample_period_s = 30.0  # Assume 30s intervals for normalized data
        min_points_needed = max(5, int(required_hold_time_s / sample_period_s) + 2)
        
        if len(normalized_df) < min_points_needed:
            reasons.append(f"Insufficient data points for reliable analysis: {len(normalized_df)} points, need at least {min_points_needed}")
            return DecisionResult(
                pass_=False,
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
                warnings=warnings
            )
        
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
        
        # Check for sensor failure (all NaN values)
        all_nan_sensors = []
        for col in temp_columns:
            if normalized_df[col].isna().all():
                all_nan_sensors.append(col)
        
        if all_nan_sensors == temp_columns:
            raise DecisionError("All temperature sensors have failed (all NaN values)")
        
        if all_nan_sensors:
            warnings.append(f"Sensor failure detected: {all_nan_sensors} have all NaN values")
        
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
        
        # Handle different types of combined sensor results
        if combined_pmt.dtype == bool:
            # Boolean result from majority_over_threshold mode
            threshold_reached = combined_pmt.any()
            max_temp_C = 1.0 if combined_pmt.any() else 0.0  # Placeholder for boolean mode
            min_temp_C = 0.0 if not combined_pmt.all() else 1.0  # Placeholder for boolean mode
        else:
            # Numerical temperature values
            max_temp_C = float(combined_pmt.max())
            min_temp_C = float(combined_pmt.min())
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
            if combined_pmt.dtype == bool:
                # For boolean mode, calculate hold time based on True values
                actual_hold_time_s = calculate_boolean_hold_time(
                    combined_pmt, normalized_df[timestamp_col], continuous=True
                )
                start_idx, end_idx = -1, -1  # Not applicable for boolean mode
            else:
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
            if combined_pmt.dtype == bool:
                # For boolean mode, calculate hold time based on True values
                actual_hold_time_s = calculate_boolean_hold_time(
                    combined_pmt, normalized_df[timestamp_col], continuous=False, max_dips_s=logic_max_dips
                )
                intervals = []  # Not applicable for boolean mode
            else:
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