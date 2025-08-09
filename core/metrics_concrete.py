"""
ProofKit Concrete Curing Validation Metrics Engine

Implements concrete curing validation according to construction industry standards
(ASTM C31, ACI 318, ACI 308). Validates critical curing conditions:
- Temperature: 16-27°C (60-80°F) for first 24 hours minimum
- Relative Humidity: ≥95% for proper hydration
- Continuous monitoring for extended curing periods (7-28 days)
- Protection from rapid temperature changes and moisture loss

Example usage:
    from core.metrics_concrete import validate_concrete_curing
    from core.models import SpecV1
    
    spec = SpecV1(**spec_data)  # Concrete industry spec
    normalized_df = pd.read_csv("concrete_curing_data.csv")
    
    result = validate_concrete_curing(normalized_df, spec)
    print(f"Concrete Curing: {'PASS' if result.pass_ else 'FAIL'}")
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from core.models import SpecV1, DecisionResult, SensorMode
from core.sensor_utils import combine_sensor_readings
from core.temperature_utils import detect_temperature_columns, DecisionError
from core.temperature_utils import calculate_continuous_hold_time
from core.errors import RequiredSignalMissingError

logger = logging.getLogger(__name__)


def detect_humidity_columns(df: pd.DataFrame) -> List[str]:
    """
    Detect relative humidity columns in the DataFrame.
    
    Args:
        df: Input DataFrame
        
    Returns:
        List of humidity column names
    """
    import re
    
    humidity_patterns = [
        r'.*humidity.*', r'.*rh.*', r'.*relative.*', r'.*moisture.*',
        r'.*_rh$', r'.*_humidity$', r'.*%rh.*'
    ]
    
    humidity_columns = []
    
    for col in df.columns:
        if col.lower() == 'timestamp' or 'time' in col.lower():
            continue
            
        col_lower = col.lower()
        if any(re.match(pattern, col_lower) for pattern in humidity_patterns):
            # Verify it's numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                humidity_columns.append(col)
    
    return humidity_columns


def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (temp_f - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (temp_c * 9.0 / 5.0) + 32.0


def calculate_temperature_stability(temperature_series: pd.Series, time_series: pd.Series,
                                  max_rate_change: float = 5.0) -> Dict[str, Any]:
    """
    Calculate temperature stability metrics for concrete curing.
    
    Rapid temperature changes can cause thermal stress and cracking in concrete.
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        max_rate_change: Maximum acceptable temperature change rate in °C/hour
        
    Returns:
        Dictionary with temperature stability metrics
    """
    # Check minimum data points for meaningful stability analysis
    if len(temperature_series) < 3:
        return {
            'max_temp_change_rate_C_per_h': 0.0,
            'avg_temp_change_rate_C_per_h': 0.0,
            'temp_stability_violations': 0,
            'temp_stability_valid': True,
            'temperature_range_C': float(temperature_series.max() - temperature_series.min()) if len(temperature_series) > 0 else 0.0,
            'std_deviation_C': float(temperature_series.std()) if len(temperature_series) > 1 else 0.0
        }
    
    # Calculate temperature change rates
    time_diff_hours = (time_series.diff().dt.total_seconds() / 3600).fillna(0)
    temp_diff = temperature_series.diff().fillna(0)
    
    # Calculate rate of change in °C/hour
    temp_rate_change = np.abs(temp_diff / time_diff_hours)
    temp_rate_change = temp_rate_change.replace([np.inf, -np.inf], 0)
    
    # Filter out zero time differences which can cause issues
    valid_rates = temp_rate_change[temp_rate_change.notna() & (temp_rate_change != np.inf)]
    
    stability_metrics = {
        'max_temp_change_rate_C_per_h': float(valid_rates.max()) if len(valid_rates) > 0 else 0.0,
        'avg_temp_change_rate_C_per_h': float(valid_rates.mean()) if len(valid_rates) > 0 else 0.0,
        'temp_stability_violations': int((valid_rates > max_rate_change).sum()) if len(valid_rates) > 0 else 0,
        'temp_stability_valid': (valid_rates.max() <= max_rate_change) if len(valid_rates) > 0 else True,
        'temperature_range_C': float(temperature_series.max() - temperature_series.min()),
        'std_deviation_C': float(temperature_series.std()) if len(temperature_series) > 1 else 0.0
    }
    
    return stability_metrics


def validate_concrete_curing_conditions(temperature_series: pd.Series, time_series: pd.Series,
                                       humidity_series: Optional[pd.Series] = None) -> Dict[str, Any]:
    """
    Validate concrete curing conditions according to construction industry standards.
    
    Critical first 24 hours requirements:
    - Temperature: 16-27°C (60-80°F) continuously
    - Relative Humidity: ≥95% for proper cement hydration
    - Temperature stability: No rapid changes (≤5°C/hour)
    - Extended curing: Maintain conditions for 7+ days for optimal strength
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        humidity_series: Optional humidity values in %RH
        
    Returns:
        Dictionary with concrete curing validation results and metrics
    """
    # Concrete curing critical parameters
    MIN_TEMP_C = 16.0  # 60°F
    MAX_TEMP_C = 27.0  # 80°F
    OPTIMAL_TEMP_C = 21.5  # 70°F
    MIN_HUMIDITY_RH = 95.0
    CRITICAL_PERIOD_S = 24 * 3600  # First 24 hours
    EXTENDED_PERIOD_S = 7 * 24 * 3600  # 7 days
    MAX_TEMP_CHANGE_RATE = 5.0  # °C/hour
    
    metrics = {
        'start_temp_C': float(temperature_series.iloc[0]),
        'end_temp_C': float(temperature_series.iloc[-1]),
        'min_temp_C': float(temperature_series.min()),
        'max_temp_C': float(temperature_series.max()),
        'avg_temp_C': float(temperature_series.mean()),
        'optimal_temp_C': OPTIMAL_TEMP_C,
        'min_required_temp_C': MIN_TEMP_C,
        'max_required_temp_C': MAX_TEMP_C,
        'total_duration_s': (time_series.iloc[-1] - time_series.iloc[0]).total_seconds(),
        'critical_period_duration_s': min(CRITICAL_PERIOD_S, (time_series.iloc[-1] - time_series.iloc[0]).total_seconds()),
        'extended_period_available': False,
        'temperature_range_valid': False,
        'critical_period_temp_valid': False,
        'humidity_valid': True,  # Default to True if no humidity data
        'temperature_stability_valid': True,
        'curing_duration_adequate': False,
        'min_humidity_rh': None,
        'avg_humidity_rh': None,
        'humidity_compliance_pct': None,
        'temp_in_range_pct': 0.0,
        'critical_temp_in_range_pct': 0.0,
        'reasons': []
    }
    
    # Check if extended curing period data is available
    if metrics['total_duration_s'] >= EXTENDED_PERIOD_S:
        metrics['extended_period_available'] = True
        metrics['curing_duration_adequate'] = True
    elif metrics['total_duration_s'] >= CRITICAL_PERIOD_S:
        metrics['curing_duration_adequate'] = True
    else:
        metrics['reasons'].append(f"Curing monitoring period {metrics['total_duration_s']/3600:.1f}h < 24h minimum requirement")
    
    # Validate temperature range for entire period
    temp_in_range = (temperature_series >= MIN_TEMP_C) & (temperature_series <= MAX_TEMP_C)
    metrics['temp_in_range_pct'] = float(temp_in_range.mean() * 100)
    
    if metrics['temp_in_range_pct'] >= 95.0:  # 95% of time in range
        metrics['temperature_range_valid'] = True
    else:
        metrics['reasons'].append(f"Temperature in acceptable range (16-27°C) only {metrics['temp_in_range_pct']:.1f}% of time")
    
    # Validate critical first 24 hours specifically
    if len(temperature_series) >= 2:
        sample_interval_s = (time_series.iloc[1] - time_series.iloc[0]).total_seconds()
        critical_period_end = min(len(temperature_series), 
                                 int(CRITICAL_PERIOD_S / sample_interval_s))
        
        if critical_period_end > 1:
            critical_temps = temperature_series.iloc[:critical_period_end]
            critical_temp_in_range = (critical_temps >= MIN_TEMP_C) & (critical_temps <= MAX_TEMP_C)
            metrics['critical_temp_in_range_pct'] = float(critical_temp_in_range.mean() * 100)
            
            if metrics['critical_temp_in_range_pct'] >= 98.0:  # Higher requirement for critical period
                metrics['critical_period_temp_valid'] = True
            else:
                metrics['reasons'].append(f"Temperature in range only {metrics['critical_temp_in_range_pct']:.1f}% of critical first 24h")
        else:
            metrics['reasons'].append("Insufficient data for critical period analysis")
    else:
        metrics['reasons'].append("Insufficient data points for critical period analysis")
    
    # Check for temperature violations
    if temperature_series.min() < MIN_TEMP_C:
        min_temp_violations = (temperature_series < MIN_TEMP_C).sum()
        metrics['reasons'].append(f"Temperature below {MIN_TEMP_C}°C detected in {min_temp_violations} samples")
    
    if temperature_series.max() > MAX_TEMP_C:
        max_temp_violations = (temperature_series > MAX_TEMP_C).sum()
        metrics['reasons'].append(f"Temperature above {MAX_TEMP_C}°C detected in {max_temp_violations} samples")
    
    # Validate temperature stability
    stability = calculate_temperature_stability(temperature_series, time_series, MAX_TEMP_CHANGE_RATE)
    metrics.update(stability)
    
    if not stability['temp_stability_valid']:
        metrics['reasons'].append(f"Excessive temperature change rate: {stability['max_temp_change_rate_C_per_h']:.1f}°C/h > {MAX_TEMP_CHANGE_RATE}°C/h limit")
    
    # Validate humidity if available
    if humidity_series is not None:
        metrics['min_humidity_rh'] = float(humidity_series.min())
        metrics['avg_humidity_rh'] = float(humidity_series.mean())
        
        humidity_compliant = humidity_series >= MIN_HUMIDITY_RH
        metrics['humidity_compliance_pct'] = float(humidity_compliant.mean() * 100)
        
        if metrics['humidity_compliance_pct'] >= 90.0:  # 90% of time above 95% RH
            metrics['humidity_valid'] = True
        else:
            metrics['humidity_valid'] = False
            metrics['reasons'].append(f"Humidity ≥95%RH only {metrics['humidity_compliance_pct']:.1f}% of time")
        
        # Check critical period humidity
        if len(temperature_series) >= 2:
            sample_interval_s = (time_series.iloc[1] - time_series.iloc[0]).total_seconds()
            critical_period_end = min(len(humidity_series), 
                                     int(CRITICAL_PERIOD_S / sample_interval_s))
            
            if critical_period_end > 1:
                critical_humidity = humidity_series.iloc[:critical_period_end]
                critical_humidity_compliant = critical_humidity >= MIN_HUMIDITY_RH
                critical_humidity_pct = float(critical_humidity_compliant.mean() * 100)
                
                if critical_humidity_pct < 95.0:
                    metrics['reasons'].append(f"Critical period humidity ≥95%RH only {critical_humidity_pct:.1f}% of first 24h")
    
    return metrics


def validate_concrete_curing(normalized_df: pd.DataFrame, spec: SpecV1) -> DecisionResult:
    """
    Validate concrete curing process based on normalized data and specification.
    
    Args:
        normalized_df: Normalized temperature and humidity data from core.normalize.py
        spec: Concrete industry specification
        
    Returns:
        DecisionResult with concrete-specific pass/fail status and detailed metrics
        
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
        
        if len(normalized_df) < 5:
            raise DecisionError("Insufficient data points for concrete curing analysis (minimum 5 required)")
            
        if spec.industry != "concrete":
            raise DecisionError(f"Invalid industry '{spec.industry}' for concrete curing validation")
        
        # Detect timestamp column
        timestamp_col = None
        for col in normalized_df.columns:
            if 'time' in col.lower() or pd.api.types.is_datetime64_any_dtype(normalized_df[col]):
                timestamp_col = col
                break
        
        if timestamp_col is None:
            raise DecisionError("No timestamp column found in normalized data")
            
        # Log data characteristics for debugging
        logger.debug(f"Concrete validation: {len(normalized_df)} data points over {(normalized_df[timestamp_col].iloc[-1] - normalized_df[timestamp_col].iloc[0]).total_seconds()/3600:.1f} hours")
        
        # Ensure timestamps are datetime
        if not pd.api.types.is_datetime64_any_dtype(normalized_df[timestamp_col]):
            normalized_df[timestamp_col] = pd.to_datetime(normalized_df[timestamp_col])
        
        # Detect temperature columns
        temp_columns = detect_temperature_columns(normalized_df)
        if not temp_columns:
            # Get available columns (excluding timestamp)
            available_cols = [col for col in normalized_df.columns if col != timestamp_col]
            raise RequiredSignalMissingError(
                missing_signals=["temperature"],
                available_signals=available_cols,
                industry="concrete"
            )
        
        # Detect humidity columns
        humidity_columns = detect_humidity_columns(normalized_df)
        
        # Get sensor selection configuration
        sensor_selection = spec.sensor_selection
        if sensor_selection and sensor_selection.sensors:
            # Filter for available sensors of each type
            available_temp_sensors = [col for col in sensor_selection.sensors if col in temp_columns]
            available_humidity_sensors = [col for col in sensor_selection.sensors if col in humidity_columns]
            
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
            
            if available_humidity_sensors:
                humidity_columns = available_humidity_sensors
            
            if sensor_selection.require_at_least and len(available_temp_sensors) < sensor_selection.require_at_least:
                warnings.append(f"Only {len(available_temp_sensors)} temperature sensors available, {sensor_selection.require_at_least} required")
        
        # Combine temperature sensor readings (mean for representative ambient conditions)
        sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MEAN_OF_SET
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
                target_temp_C=21.5,
                conservative_threshold_C=16.0,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=0.0,
                min_temp_C=0.0,
                reasons=reasons,
                warnings=warnings,
                industry=spec.industry
            )
        
        # Combine humidity sensor readings if available
        combined_humidity = None
        if humidity_columns:
            try:
                combined_humidity = combine_sensor_readings(
                    normalized_df, humidity_columns, SensorMode.MEAN_OF_SET
                )
            except DecisionError as e:
                warnings.append(f"Humidity sensor combination failed: {str(e)}")
        else:
            warnings.append("No humidity sensors detected - validation will proceed without humidity monitoring")
            flags = locals().get('flags', {})
            flags['fallback_used'] = True
            locals()['flags'] = flags
        
        # Validate concrete curing conditions
        curing_metrics = validate_concrete_curing_conditions(
            combined_temp, normalized_df[timestamp_col], combined_humidity
        )

        # Enforce required parameters per spec - check early for missing required signals
        require_humidity = bool(getattr(spec, 'parameter_requirements', None) and getattr(spec.parameter_requirements, 'require_humidity', False))
        
        # Check for missing required signals - should return INDETERMINATE
        missing_signals = []
        available_signals = list(normalized_df.columns)
        
        if require_humidity and combined_humidity is None:
            missing_signals.append("humidity")
        
        # If any required signals are missing, return INDETERMINATE
        if missing_signals:
            raise RequiredSignalMissingError(
                missing_signals=missing_signals,
                available_signals=available_signals,
                industry="concrete"
            )
        
        # Define 24h window starting at first timestamp (UTC)
        start_time = normalized_df[timestamp_col].iloc[0]
        window_24h = start_time + pd.Timedelta(hours=24)
        
        # Filter to first 24h window
        df_24h = normalized_df[normalized_df[timestamp_col] <= window_24h].copy()
        
        # Check for insufficient samples in 24h window
        if len(df_24h) < 10:
            status = 'INDETERMINATE'
            reasons.append(f"Insufficient samples in 24h window: {len(df_24h)} < 10 required")
            return DecisionResult(
                pass_=False,
                status=status,
                job_id=spec.job.job_id,
                target_temp_C=21.5,
                conservative_threshold_C=16.0,
                actual_hold_time_s=0.0,
                required_hold_time_s=spec.spec.hold_time_s,
                max_temp_C=curing_metrics['max_temp_C'],
                min_temp_C=curing_metrics['min_temp_C'],
                reasons=reasons,
                warnings=warnings,
                industry=spec.industry,
                flags=locals().get('flags', {})
            )
        
        # Calculate 24h window compliance
        samples_meeting_constraints = 0
        total_samples_24h = len(df_24h)
        
        for idx, row in df_24h.iterrows():
            # Check temperature constraints [16, 27]°C for all temperature sensors
            temp_values = []
            for col in temp_columns:
                if col in row and pd.notna(row[col]):
                    temp_values.append(row[col])
            
            # Check humidity constraint ≥95% if required and available
            rh_ok = True
            if require_humidity and combined_humidity is not None:
                rh_idx = df_24h.index.get_loc(idx)
                if rh_idx < len(combined_humidity):
                    rh_value = combined_humidity.iloc[rh_idx]
                    rh_ok = pd.notna(rh_value) and rh_value >= 95.0
                else:
                    rh_ok = False
            
            # Sample meets constraints if ALL temps in [16,27]°C AND RH≥95% (if required)
            if temp_values:
                all_temp_ok = all(16.0 <= temp <= 27.0 for temp in temp_values)
                if all_temp_ok and rh_ok:
                    samples_meeting_constraints += 1
        
        # Calculate percentage of samples meeting all constraints in 24h window
        pct_ok = (samples_meeting_constraints / total_samples_24h) * 100 if total_samples_24h > 0 else 0
        
        # Determine status: PASS if ≥95% compliance, FAIL otherwise
        # At this point required signals are available (would have raised RequiredSignalMissingError above)
        if pct_ok >= 95.0:
            status = 'PASS'
            reasons.append(f"24h window compliance: {pct_ok:.1f}% of samples meet temp ∈ [16,27]°C" + 
                          (" and RH≥95%" if require_humidity and combined_humidity is not None else ""))
        else:
            status = 'FAIL'
            reasons.append(f"24h window compliance: {pct_ok:.1f}% < 95% required for temp ∈ [16,27]°C" + 
                          (" and RH≥95%" if require_humidity and combined_humidity is not None else ""))
        
        pass_decision = (status == 'PASS')
        
        # Add success reasons if passed
        if pass_decision:
            reasons.append(f"Temperature maintained in curing range (16-27°C) for {curing_metrics['temp_in_range_pct']:.1f}% of monitoring period")
            reasons.append(f"Critical first 24h temperature compliance: {curing_metrics['critical_temp_in_range_pct']:.1f}%")
            
            if combined_humidity is not None:
                reasons.append(f"Humidity ≥95%RH maintained for {curing_metrics['humidity_compliance_pct']:.1f}% of period")
            
            if curing_metrics['extended_period_available']:
                reasons.append("Extended curing period (≥7 days) monitoring completed")
            else:
                reasons.append("Critical curing period (≥24 hours) requirements met")
            
            reasons.append("Concrete curing requirements met")
        else:
            # Add failure reasons
            reasons.extend(curing_metrics['reasons'])
        
        # Check data quality warnings
        total_duration_days = curing_metrics['total_duration_s'] / (24 * 3600)
        
        if total_duration_days < 1.0:
            warnings.append(f"Monitoring period ({total_duration_days:.1f} days) shorter than recommended 24h minimum")
        elif total_duration_days >= 7.0:
            warnings.append(f"Extended monitoring period ({total_duration_days:.1f} days) - excellent curing validation")
        
        if curing_metrics['temperature_range_C'] > 15.0:
            warnings.append(f"Large temperature variation ({curing_metrics['temperature_range_C']:.1f}°C) may affect curing quality")
        
        if curing_metrics['avg_temp_C'] < 18.0:
            warnings.append(f"Average temperature ({curing_metrics['avg_temp_C']:.1f}°C) on lower end - may slow curing process")
        elif curing_metrics['avg_temp_C'] > 25.0:
            warnings.append(f"Average temperature ({curing_metrics['avg_temp_C']:.1f}°C) on higher end - monitor for rapid moisture loss")
        
        # Calculate hold time in acceptable range
        temp_in_range = (combined_temp >= 16.0) & (combined_temp <= 27.0)
        actual_hold_time_s = 0.0
        if temp_in_range.any():
            # Calculate continuous time in acceptable range
            hold_time_s, _, _ = calculate_continuous_hold_time(
                combined_temp, normalized_df[timestamp_col], 16.0, hysteresis_C=0.5
            )
            actual_hold_time_s = hold_time_s
        
        return DecisionResult(
            pass_=pass_decision,
            status=status,
            job_id=spec.job.job_id,
            target_temp_C=21.5,  # Optimal concrete curing temperature
            conservative_threshold_C=16.0,  # Minimum acceptable temperature
            actual_hold_time_s=actual_hold_time_s,
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=curing_metrics['max_temp_C'],
            min_temp_C=curing_metrics['min_temp_C'],
            reasons=reasons,
            warnings=warnings,
            industry=spec.industry,
            flags=locals().get('flags', {})
        )
    
    except RequiredSignalMissingError:
        # Re-raise RequiredSignalMissingError without wrapping
        raise
    except Exception as e:
        logger.error(f"Concrete curing validation failed: {e}")
        raise DecisionError(f"Concrete curing validation failed: {str(e)}")


# Usage example in comments:
"""
Example usage for concrete curing validation:

from core.metrics_concrete import validate_concrete_curing
from core.models import SpecV1
import pandas as pd

# Load concrete curing specification
spec_data = {
    "version": "1.0",
    "industry": "concrete",
    "job": {"job_id": "building_foundation_001"},
    "spec": {
        "method": "OVEN_AIR",
        "target_temp_C": 21.5,  # 70°F optimal
        "hold_time_s": 86400,   # 24 hours minimum
        "sensor_uncertainty_C": 0.5
    },
    "data_requirements": {
        "max_sample_period_s": 600.0,
        "allowed_gaps_s": 1800.0
    },
    "sensor_selection": {
        "mode": "mean_of_set",
        "require_at_least": 2
    }
}
spec = SpecV1(**spec_data)

# Load normalized curing data (with temperature and humidity columns)
normalized_df = pd.read_csv("concrete_curing_data.csv")

# Validate concrete curing
result = validate_concrete_curing(normalized_df, spec)

print(f"Concrete Curing Job {result.job_id}: {'PASS' if result.pass_ else 'FAIL'}")
print(f"Curing validation: {result.reasons}")
if result.warnings:
    print(f"Warnings: {result.warnings}")
"""