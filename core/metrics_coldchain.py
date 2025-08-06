"""
ProofKit Cold Chain Validation Metrics Engine

Implements cold chain validation according to pharmaceutical and vaccine storage standards
(USP 797, CDC Vaccine Storage Guidelines, WHO PQS standards). Validates critical storage conditions:
- Temperature: 2-8°C (35.6-46.4°F) for refrigerated products
- Temperature stability: ≥95% of samples per day within range
- Alarm thresholds: Outside range for >30 minutes triggers alarm
- Data logging: Continuous monitoring with ≤15 minute intervals

Example usage:
    from core.metrics_coldchain import validate_coldchain_storage
    from core.models import SpecV1
    
    spec = SpecV1(**spec_data)  # Coldchain industry spec
    normalized_df = pd.read_csv("vaccine_storage_data.csv")
    
    result = validate_coldchain_storage(normalized_df, spec)
    print(f"Cold Chain Storage: {'PASS' if result.pass_ else 'FAIL'}")
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging

from core.models import SpecV1, DecisionResult, SensorMode
# Note: This module uses its own combine_sensor_readings due to different parameters

logger = logging.getLogger(__name__)


class DecisionError(Exception):
    """Exception raised when decision algorithm encounters an error."""
    pass


def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (temp_f - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (temp_c * 9.0 / 5.0) + 32.0


def detect_temperature_columns(df: pd.DataFrame) -> List[str]:
    """
    Detect temperature columns in the normalized DataFrame.
    
    Args:
        df: Normalized DataFrame
        
    Returns:
        List of column names that appear to be temperature columns
    """
    temp_columns = []
    for col in df.columns:
        col_lower = col.lower()
        if any(keyword in col_lower for keyword in ['temp', 'temperature']):
            temp_columns.append(col)
    return temp_columns


def combine_sensor_readings(df: pd.DataFrame, temp_columns: List[str], 
                          sensor_mode: SensorMode, require_at_least: Optional[int] = None,
                          threshold_C: float = 5.0) -> pd.Series:
    """
    Combine multiple sensor readings according to the specified mode.
    
    Args:
        df: DataFrame with temperature data
        temp_columns: List of temperature column names
        sensor_mode: How to combine sensor readings
        require_at_least: Minimum number of sensors required
        threshold_C: Threshold temperature for mode calculations
        
    Returns:
        Combined temperature series
        
    Raises:
        DecisionError: If sensor combination fails
    """
    if not temp_columns:
        raise DecisionError("No temperature columns available for sensor combination")
        
    if require_at_least and len(temp_columns) < require_at_least:
        raise DecisionError(f"Only {len(temp_columns)} sensors available, {require_at_least} required")
    
    # Get temperature data
    temp_data = df[temp_columns]
    
    # Handle sensor combination modes
    if sensor_mode == SensorMode.AVERAGE:
        return temp_data.mean(axis=1)
    elif sensor_mode == SensorMode.MINIMUM:
        return temp_data.min(axis=1)
    elif sensor_mode == SensorMode.MAXIMUM:
        return temp_data.max(axis=1)
    elif sensor_mode == SensorMode.MEDIAN:
        return temp_data.median(axis=1)
    elif sensor_mode == SensorMode.MAJORITY_OVER_THRESHOLD:
        # Conservative approach: use median if available, otherwise average
        if len(temp_columns) >= 3:
            return temp_data.median(axis=1)
        else:
            return temp_data.mean(axis=1)
    else:
        # Default to average
        return temp_data.mean(axis=1)


def identify_temperature_excursions(temperature_series: pd.Series, time_series: pd.Series,
                                  min_temp_c: float = 2.0, max_temp_c: float = 8.0,
                                  alarm_threshold_minutes: int = 30) -> Dict[str, Any]:
    """
    Identify temperature excursions outside acceptable cold chain range.
    
    An excursion is defined as temperature outside 2-8°C range for more than
    the alarm threshold duration (typically 30 minutes).
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        min_temp_c: Minimum acceptable temperature (default 2°C)
        max_temp_c: Maximum acceptable temperature (default 8°C)
        alarm_threshold_minutes: Minutes outside range before alarm (default 30)
        
    Returns:
        Dictionary with excursion analysis results
    """
    alarm_threshold_s = alarm_threshold_minutes * 60
    
    # Identify samples outside acceptable range
    outside_range = (temperature_series < min_temp_c) | (temperature_series > max_temp_c)
    
    excursion_metrics = {
        'total_samples': len(temperature_series),
        'samples_outside_range': int(outside_range.sum()),
        'samples_in_range': int((~outside_range).sum()),
        'compliance_percentage': float((~outside_range).mean() * 100),
        'excursion_events': [],
        'total_excursion_time_s': 0.0,
        'max_excursion_duration_s': 0.0,
        'alarm_events': 0,
        'total_alarm_time_s': 0.0,
        'temperature_below_range_s': 0.0,
        'temperature_above_range_s': 0.0,
        'max_low_temp_c': None,
        'max_high_temp_c': None
    }
    
    if outside_range.any():
        # Find excursion periods
        excursion_start = None
        
        for i, is_outside in enumerate(outside_range):
            if is_outside and excursion_start is None:
                # Start of excursion
                excursion_start = i
            elif not is_outside and excursion_start is not None:
                # End of excursion
                excursion_end = i - 1
                
                # Calculate excursion duration
                start_time = time_series.iloc[excursion_start]
                end_time = time_series.iloc[excursion_end]
                duration_s = (end_time - start_time).total_seconds()
                
                # Get temperature range during excursion
                excursion_temps = temperature_series.iloc[excursion_start:excursion_end+1]
                min_excursion_temp = float(excursion_temps.min())
                max_excursion_temp = float(excursion_temps.max())
                
                excursion_event = {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration_s': duration_s,
                    'min_temp_c': min_excursion_temp,
                    'max_temp_c': max_excursion_temp,
                    'is_alarm': duration_s >= alarm_threshold_s,
                    'below_range': min_excursion_temp < min_temp_c,
                    'above_range': max_excursion_temp > max_temp_c
                }
                
                excursion_metrics['excursion_events'].append(excursion_event)
                excursion_metrics['total_excursion_time_s'] += duration_s
                excursion_metrics['max_excursion_duration_s'] = max(
                    excursion_metrics['max_excursion_duration_s'], duration_s
                )
                
                # Track alarm events (excursions > threshold)
                if excursion_event['is_alarm']:
                    excursion_metrics['alarm_events'] += 1
                    excursion_metrics['total_alarm_time_s'] += duration_s
                
                # Track time below/above range
                if excursion_event['below_range']:
                    excursion_metrics['temperature_below_range_s'] += duration_s
                    if excursion_metrics['max_low_temp_c'] is None or min_excursion_temp < excursion_metrics['max_low_temp_c']:
                        excursion_metrics['max_low_temp_c'] = min_excursion_temp
                
                if excursion_event['above_range']:
                    excursion_metrics['temperature_above_range_s'] += duration_s
                    if excursion_metrics['max_high_temp_c'] is None or max_excursion_temp > excursion_metrics['max_high_temp_c']:
                        excursion_metrics['max_high_temp_c'] = max_excursion_temp
                
                excursion_start = None
        
        # Handle case where excursion continues to end of data
        if excursion_start is not None:
            start_time = time_series.iloc[excursion_start]
            end_time = time_series.iloc[-1]
            duration_s = (end_time - start_time).total_seconds()
            
            excursion_temps = temperature_series.iloc[excursion_start:]
            min_excursion_temp = float(excursion_temps.min())
            max_excursion_temp = float(excursion_temps.max())
            
            excursion_event = {
                'start_time': start_time,
                'end_time': end_time,
                'duration_s': duration_s,
                'min_temp_c': min_excursion_temp,
                'max_temp_c': max_excursion_temp,
                'is_alarm': duration_s >= alarm_threshold_s,
                'below_range': min_excursion_temp < min_temp_c,
                'above_range': max_excursion_temp > max_temp_c
            }
            
            excursion_metrics['excursion_events'].append(excursion_event)
            excursion_metrics['total_excursion_time_s'] += duration_s
            
            if excursion_event['is_alarm']:
                excursion_metrics['alarm_events'] += 1
                excursion_metrics['total_alarm_time_s'] += duration_s
    
    return excursion_metrics


def calculate_daily_compliance(temperature_series: pd.Series, time_series: pd.Series,
                             min_temp_c: float = 2.0, max_temp_c: float = 8.0,
                             required_compliance: float = 95.0) -> Dict[str, Any]:
    """
    Calculate daily compliance with cold chain temperature requirements.
    
    Cold chain standards typically require ≥95% of samples per day to be within range.
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        min_temp_c: Minimum acceptable temperature
        max_temp_c: Maximum acceptable temperature
        required_compliance: Required daily compliance percentage
        
    Returns:
        Dictionary with daily compliance analysis
    """
    # Create DataFrame for easier daily grouping
    df = pd.DataFrame({
        'timestamp': time_series,
        'temperature': temperature_series
    })
    
    # Add date column for daily grouping
    df['date'] = df['timestamp'].dt.date
    
    # Calculate compliance for each day
    df['in_range'] = (df['temperature'] >= min_temp_c) & (df['temperature'] <= max_temp_c)
    
    daily_compliance = df.groupby('date').agg({
        'in_range': ['count', 'sum', 'mean'],
        'temperature': ['min', 'max', 'mean', 'std']
    }).round(3)
    
    # Flatten column names
    daily_compliance.columns = [f"{col[1]}_{col[0]}" if col[1] else col[0] for col in daily_compliance.columns]
    daily_compliance = daily_compliance.rename(columns={
        'sum_in_range': 'samples_in_range',
        'count_in_range': 'total_samples',
        'mean_in_range': 'compliance_pct'
    })
    
    # Convert compliance to percentage
    daily_compliance['compliance_pct'] *= 100
    
    # Identify non-compliant days
    non_compliant_days = daily_compliance[daily_compliance['compliance_pct'] < required_compliance]
    
    compliance_metrics = {
        'total_days': len(daily_compliance),
        'compliant_days': len(daily_compliance[daily_compliance['compliance_pct'] >= required_compliance]),
        'non_compliant_days': len(non_compliant_days),
        'overall_compliance_pct': float(daily_compliance['compliance_pct'].mean()),
        'worst_day_compliance_pct': float(daily_compliance['compliance_pct'].min()),
        'best_day_compliance_pct': float(daily_compliance['compliance_pct'].max()),
        'daily_compliance_data': daily_compliance.to_dict('index'),
        'non_compliant_dates': non_compliant_days.index.tolist(),
        'days_meeting_requirement': len(daily_compliance[daily_compliance['compliance_pct'] >= required_compliance]) >= len(daily_compliance)
    }
    
    return compliance_metrics


def validate_coldchain_storage_conditions(temperature_series: pd.Series, time_series: pd.Series) -> Dict[str, Any]:
    """
    Validate cold chain storage conditions according to pharmaceutical standards.
    
    Requirements:
    - Temperature: 2-8°C (35.6-46.4°F) continuously
    - Daily compliance: ≥95% of samples within range per day
    - Alarm threshold: <30 minutes outside range acceptable
    - Data logging: Continuous monitoring preferred
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        
    Returns:
        Dictionary with cold chain validation results and metrics
    """
    # Cold chain critical parameters
    MIN_TEMP_C = 2.0
    MAX_TEMP_C = 8.0
    REQUIRED_DAILY_COMPLIANCE = 95.0  # 95% of samples per day
    ALARM_THRESHOLD_MINUTES = 30
    MAX_ACCEPTABLE_EXCURSION_TIME_S = 2 * 3600  # 2 hours total per day
    
    metrics = {
        'start_temp_C': float(temperature_series.iloc[0]),
        'end_temp_C': float(temperature_series.iloc[-1]),
        'min_temp_C': float(temperature_series.min()),
        'max_temp_C': float(temperature_series.max()),
        'avg_temp_C': float(temperature_series.mean()),
        'target_min_temp_C': MIN_TEMP_C,
        'target_max_temp_C': MAX_TEMP_C,
        'total_duration_s': (time_series.iloc[-1] - time_series.iloc[0]).total_seconds(),
        'monitoring_days': 0.0,
        'temperature_range_valid': False,
        'daily_compliance_valid': False,
        'excursion_control_valid': False,
        'alarm_events_acceptable': False,
        'data_logging_adequate': False,
        'overall_compliance_pct': 0.0,
        'excursion_summary': {},
        'daily_compliance_summary': {},
        'reasons': []
    }
    
    metrics['monitoring_days'] = metrics['total_duration_s'] / (24 * 3600)
    
    # Analyze temperature excursions
    excursion_analysis = identify_temperature_excursions(
        temperature_series, time_series, MIN_TEMP_C, MAX_TEMP_C, ALARM_THRESHOLD_MINUTES
    )
    metrics['excursion_summary'] = excursion_analysis
    metrics['overall_compliance_pct'] = excursion_analysis['compliance_percentage']
    
    # Validate overall temperature compliance (≥95% in range)
    if excursion_analysis['compliance_percentage'] >= REQUIRED_DAILY_COMPLIANCE:
        metrics['temperature_range_valid'] = True
    else:
        metrics['reasons'].append(
            f"Overall temperature compliance {excursion_analysis['compliance_percentage']:.1f}% < {REQUIRED_DAILY_COMPLIANCE}% requirement"
        )
    
    # Validate alarm events (should be minimal)
    if excursion_analysis['alarm_events'] == 0:
        metrics['alarm_events_acceptable'] = True
    elif excursion_analysis['total_alarm_time_s'] <= MAX_ACCEPTABLE_EXCURSION_TIME_S:
        metrics['alarm_events_acceptable'] = True
        metrics['reasons'].append(
            f"Temperature excursions detected but within acceptable limits: {excursion_analysis['alarm_events']} events, "
            f"{excursion_analysis['total_alarm_time_s']/3600:.1f}h total"
        )
    else:
        metrics['reasons'].append(
            f"Excessive temperature excursions: {excursion_analysis['alarm_events']} alarm events, "
            f"{excursion_analysis['total_alarm_time_s']/3600:.1f}h total > {MAX_ACCEPTABLE_EXCURSION_TIME_S/3600}h limit"
        )
    
    # Analyze daily compliance if monitoring period ≥ 1 day
    if metrics['monitoring_days'] >= 1.0:
        daily_analysis = calculate_daily_compliance(
            temperature_series, time_series, MIN_TEMP_C, MAX_TEMP_C, REQUIRED_DAILY_COMPLIANCE
        )
        metrics['daily_compliance_summary'] = daily_analysis
        
        if daily_analysis['days_meeting_requirement'] and daily_analysis['overall_compliance_pct'] >= REQUIRED_DAILY_COMPLIANCE:
            metrics['daily_compliance_valid'] = True
        else:
            metrics['reasons'].append(
                f"Daily compliance failure: {daily_analysis['non_compliant_days']} of {daily_analysis['total_days']} days "
                f"below {REQUIRED_DAILY_COMPLIANCE}% requirement"
            )
    else:
        # For periods < 1 day, use overall compliance
        metrics['daily_compliance_valid'] = metrics['temperature_range_valid']
    
    # Validate excursion control
    if excursion_analysis['alarm_events'] <= 1 and excursion_analysis['total_alarm_time_s'] <= MAX_ACCEPTABLE_EXCURSION_TIME_S:
        metrics['excursion_control_valid'] = True
    else:
        metrics['reasons'].append("Poor excursion control - multiple or prolonged temperature deviations")
    
    # Validate data logging frequency
    if len(temperature_series) >= 2:
        avg_interval_s = metrics['total_duration_s'] / (len(temperature_series) - 1)
        if avg_interval_s <= 15 * 60:  # ≤15 minute intervals
            metrics['data_logging_adequate'] = True
        else:
            metrics['reasons'].append(f"Data logging interval {avg_interval_s/60:.1f}min > 15min recommended maximum")
    
    # Check for critical temperature violations
    if metrics['min_temp_C'] < -2.0:  # Freezing risk
        metrics['reasons'].append(f"Critical low temperature {metrics['min_temp_C']:.1f}°C detected - product may be damaged")
    elif metrics['min_temp_C'] < MIN_TEMP_C:
        metrics['reasons'].append(f"Temperature below range: minimum {metrics['min_temp_C']:.1f}°C")
    
    if metrics['max_temp_C'] > 15.0:  # Significant temperature abuse
        metrics['reasons'].append(f"Critical high temperature {metrics['max_temp_C']:.1f}°C detected - product efficacy may be compromised")
    elif metrics['max_temp_C'] > MAX_TEMP_C:
        metrics['reasons'].append(f"Temperature above range: maximum {metrics['max_temp_C']:.1f}°C")
    
    return metrics


def validate_coldchain_storage(normalized_df: pd.DataFrame, spec: SpecV1) -> DecisionResult:
    """
    Validate cold chain storage process based on normalized data and specification.
    
    Args:
        normalized_df: Normalized temperature data from core.normalize.py
        spec: Cold chain industry specification
        
    Returns:
        DecisionResult with cold chain-specific pass/fail status and detailed metrics
        
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
            raise DecisionError("Insufficient data points for cold chain storage analysis")
            
        if spec.industry != "coldchain":
            raise DecisionError(f"Invalid industry '{spec.industry}' for cold chain storage validation")
        
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
        
        # Combine sensor readings (majority_over_threshold for conservative cold chain validation)
        sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MAJORITY_OVER_THRESHOLD
        require_at_least = sensor_selection.require_at_least if sensor_selection else None
        
        try:
            combined_temp = combine_sensor_readings(
                normalized_df, temp_columns, sensor_mode, require_at_least, threshold_C=5.0  # Mid-range threshold
            )
        except DecisionError as e:
            reasons.append(f"Temperature sensor combination failed: {str(e)}")
            return DecisionResult(
                pass_=False,
                job_id=spec.job.job_id,
                target_temp_C=5.0,
                conservative_threshold_C=2.0,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=0.0,
                min_temp_C=0.0,
                reasons=reasons,
                warnings=warnings
            )
        
        # Validate cold chain storage conditions
        storage_metrics = validate_coldchain_storage_conditions(combined_temp, normalized_df[timestamp_col])
        
        # Determine overall pass/fail status
        pass_decision = (
            storage_metrics['temperature_range_valid'] and
            storage_metrics['daily_compliance_valid'] and
            storage_metrics['excursion_control_valid'] and
            storage_metrics['data_logging_adequate'] and
            storage_metrics['alarm_events_acceptable']
        )
        
        # Add success reasons if passed
        if pass_decision:
            reasons.append(f"Temperature maintained in cold chain range (2-8°C) for {storage_metrics['overall_compliance_pct']:.1f}% of monitoring period")
            
            if storage_metrics['monitoring_days'] >= 1.0:
                daily_summary = storage_metrics['daily_compliance_summary']
                reasons.append(f"Daily compliance: {daily_summary['compliant_days']} of {daily_summary['total_days']} days met ≥95% requirement")
            
            excursion_summary = storage_metrics['excursion_summary']
            if excursion_summary['alarm_events'] == 0:
                reasons.append("No significant temperature excursions detected")
            else:
                reasons.append(f"Temperature excursions within acceptable limits: {excursion_summary['alarm_events']} events")
            
            reasons.append("Cold chain storage requirements met")
        else:
            # Add failure reasons
            reasons.extend(storage_metrics['reasons'])
        
        # Check data quality warnings
        monitoring_days = storage_metrics['monitoring_days']
        
        if monitoring_days < 1.0:
            warnings.append(f"Monitoring period ({monitoring_days:.1f} days) shorter than recommended daily validation")
        elif monitoring_days >= 30.0:
            warnings.append(f"Extended monitoring period ({monitoring_days:.1f} days) - excellent cold chain validation")
        
        excursion_summary = storage_metrics['excursion_summary']
        if excursion_summary['excursion_events']:
            total_excursions = len(excursion_summary['excursion_events'])
            max_duration_min = excursion_summary['max_excursion_duration_s'] / 60
            warnings.append(f"{total_excursions} temperature excursion events detected (max duration: {max_duration_min:.1f}min)")
        
        # Calculate hold time in acceptable range
        temp_in_range = (combined_temp >= 2.0) & (combined_temp <= 8.0)
        actual_hold_time_s = 0.0
        if temp_in_range.any():
            # Calculate cumulative time in range (allowing brief excursions)
            time_diffs = normalized_df[timestamp_col].diff().dt.total_seconds().fillna(0)
            time_in_range = temp_in_range * time_diffs
            actual_hold_time_s = float(time_in_range.sum())
        
        return DecisionResult(
            pass_=pass_decision,
            job_id=spec.job.job_id,
            target_temp_C=5.0,  # Mid-range cold chain temperature
            conservative_threshold_C=2.0,  # Minimum acceptable temperature
            actual_hold_time_s=actual_hold_time_s,
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=storage_metrics['max_temp_C'],
            min_temp_C=storage_metrics['min_temp_C'],
            reasons=reasons,
            warnings=warnings
        )
    
    except Exception as e:
        logger.error(f"Cold chain storage validation failed: {e}")
        raise DecisionError(f"Cold chain storage validation failed: {str(e)}")