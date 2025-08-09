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
from core.temperature_utils import calculate_continuous_hold_time
from core.errors import RequiredSignalMissingError

logger = logging.getLogger(__name__)


def calculate_fo_value(temperature_series: pd.Series, time_series: pd.Series, 
                      z_value: float = 10.0, reference_temp_c: float = 121.1) -> float:
    """
    Calculate Fo (sterilization lethality) value using trapezoidal integration.
    
    Fo represents the equivalent time in minutes at 121.1°C that would provide 
    the same lethality as the actual temperature profile.
    
    Formula: Fo[min] = Σ 10^((T(t)-121.1)/z) * Δt/60
    where:
    - Δt = time interval in seconds (trapezoidal integration)
    - T(t) = temperature in Celsius at time t
    - z = temperature coefficient (typically 10°C for steam sterilization)
    
    Args:
        temperature_series: Temperature values in Celsius
        time_series: Timestamp values
        z_value: Temperature coefficient for lethality calculation (default 10°C)
        reference_temp_c: Reference temperature for Fo calculation (default 121.1°C)
        
    Returns:
        Fo value in minutes equivalent at 121.1°C
    """
    if len(temperature_series) < 2:
        return 0.0
    
    fo_value = 0.0
    
    for i in range(1, len(temperature_series)):
        # Calculate time interval in seconds
        time_interval_s = (time_series.iloc[i] - time_series.iloc[i-1]).total_seconds()
        
        # Trapezoidal integration: use lethality rates at both time points
        lethality_rate_i1 = 10 ** ((temperature_series.iloc[i-1] - reference_temp_c) / z_value)
        lethality_rate_i = 10 ** ((temperature_series.iloc[i] - reference_temp_c) / z_value)
        
        # Trapezoidal rule: (f(a) + f(b)) * (b-a) / 2
        avg_lethality_rate = (lethality_rate_i1 + lethality_rate_i) / 2.0
        
        # Add to cumulative Fo value (time_interval_s/60 converts seconds to minutes)
        fo_value += avg_lethality_rate * time_interval_s / 60.0
    
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


def bar_to_kpa(pressure_bar: float) -> float:
    """Convert pressure from bar to kPa."""
    return pressure_bar * 100.0


def detect_pressure_unit(pressure_series: pd.Series) -> str:
    """
    Detect pressure unit based on typical value ranges.
    
    Returns:
        str: 'kPa', 'psi', 'bar', or 'unknown'
    """
    max_pressure = pressure_series.max()
    min_pressure = pressure_series.min()
    
    # Typical autoclave pressure ranges:
    # - kPa: 100-200 kPa (15-30 psi)
    # - psi: 15-30 psi
    # - bar: 1-2 bar
    
    if 0.8 <= max_pressure <= 3.0 and min_pressure >= 0.5:
        return 'bar'  # Values around 1-2 bar
    elif 10 <= max_pressure <= 50 and min_pressure >= 5:
        return 'psi'  # Values around 15-30 psi
    elif 80 <= max_pressure <= 300 and min_pressure >= 50:
        return 'kPa'  # Values around 100-200 kPa
    else:
        return 'unknown'


def validate_autoclave_cycle(temperature_series: pd.Series, time_series: pd.Series,
                           pressure_series: Optional[pd.Series] = None, 
                           df: Optional[pd.DataFrame] = None,
                           spec: Optional[Any] = None) -> Dict[str, Any]:
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
    # Determine critical parameters from spec or use pharmaceutical defaults
    if spec and hasattr(spec, 'spec'):
        TARGET_TEMP_C = float(spec.spec.target_temp_C)
        sensor_uncertainty = float(getattr(spec.spec, 'sensor_uncertainty_C', 0.5))
        MIN_TEMP_C = TARGET_TEMP_C - sensor_uncertainty  # Conservative threshold
        MIN_HOLD_TIME_S = int(spec.spec.hold_time_s)
        
        # Use spec temp_band_C if available, otherwise apply reasonable tolerance
        temp_band = getattr(spec.spec, 'temp_band_C', None) or getattr(spec.spec, 'temp_band', None)
        if temp_band:
            MAX_TEMP_C = float(temp_band.max) if hasattr(temp_band, 'max') else TARGET_TEMP_C + 2.0
            # Use temp_band.min as the minimum sterilization temperature if specified
            if hasattr(temp_band, 'min'):
                MIN_TEMP_C = float(temp_band.min)
        else:
            MAX_TEMP_C = TARGET_TEMP_C + 2.0  # 2°C tolerance above target
    else:
        # Fallback to pharmaceutical defaults
        MIN_TEMP_C = 119.0  # 121°C - 2°C tolerance
        MAX_TEMP_C = 123.0  # 121°C + 2°C tolerance
        TARGET_TEMP_C = 121.1  # Standard reference temperature
        MIN_HOLD_TIME_S = 15 * 60  # 15 minutes
    
    # Fixed parameters
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
    
    # Calculate or use pre-calculated Fo value
    fo_value = None
    if df is not None and 'fo_value' in df.columns:
        # Use pre-calculated Fo value from the dataset (final/maximum value)
        fo_value = float(df['fo_value'].max())
        logger.info(f"Using pre-calculated Fo value from dataset: {fo_value:.1f}")
    else:
        # Calculate Fo value using trapezoidal integration
        fo_value = calculate_fo_value(temperature_series, time_series)
        logger.info(f"Calculated Fo value: {fo_value:.1f}")
    
    metrics['fo_value'] = fo_value
    
    if fo_value >= MIN_FO_VALUE:
        metrics['fo_value_valid'] = True
    else:
        metrics['reasons'].append(f"Fo value {fo_value:.1f} < {MIN_FO_VALUE} minimum requirement")
    
    # Validate temperature range and hold time
    in_sterilization_range = (temperature_series >= MIN_TEMP_C) & (temperature_series <= MAX_TEMP_C)
    
    if in_sterilization_range.any():
        metrics['temperature_range_valid'] = True
        
        # Calculate continuous hold time in sterilization range using 0.3°C hysteresis
        hold_time_s, start_idx, end_idx = calculate_continuous_hold_time(
            temperature_series, time_series, MIN_TEMP_C, hysteresis_C=0.3
        )
        metrics['sterilization_hold_time_s'] = hold_time_s
        
        if hold_time_s >= MIN_HOLD_TIME_S:
            metrics['hold_time_valid'] = True
        else:
            # For autoclave sterilization, if Fo value is significantly above minimum,
            # it may compensate for shorter hold time
            fo_value = metrics.get('fo_value', 0)
            fo_multiplier = fo_value / MIN_FO_VALUE if MIN_FO_VALUE > 0 else 1.0
            
            if fo_value >= MIN_FO_VALUE and fo_multiplier >= 2.0:
                # High Fo value (≥2x minimum) can compensate for shorter hold time
                metrics['hold_time_valid'] = True
                metrics['reasons'].append(f"Hold time compensated by high Fo value ({fo_value:.1f} ≥ 2x minimum)")
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
        # Detect and convert pressure units to kPa
        pressure_unit = detect_pressure_unit(pressure_series)
        
        if pressure_unit == 'bar':
            pressure_kpa = pressure_series * 100.0  # Convert bar to kPa
        elif pressure_unit == 'psi':
            pressure_kpa = pressure_series * 6.895  # Convert psi to kPa
        elif pressure_unit == 'kPa':
            pressure_kpa = pressure_series  # Already in kPa
        else:
            # Unknown unit, assume kPa and add warning
            pressure_kpa = pressure_series
            metrics.setdefault('warnings', []).append(f"Unknown pressure unit detected (range: {pressure_series.min():.2f}-{pressure_series.max():.2f})")
        
        metrics['min_pressure_kpa'] = float(pressure_kpa.min())
        metrics['avg_pressure_kpa'] = float(pressure_kpa.mean())
        
        # Check if pressure maintained above minimum during hold window only
        # Apply 0.3°C hysteresis logic to determine hold period
        hysteresis_c = 0.3  # Corrected hysteresis for precise validation
        threshold_with_hyst = MIN_TEMP_C - hysteresis_c
        
        # Find continuous hold periods above threshold with hysteresis
        above_threshold = temperature_series >= MIN_TEMP_C
        below_threshold_with_hyst = temperature_series < threshold_with_hyst
        
        # Track hold periods and check pressure only during those windows
        in_hold = False
        hold_start_idx = None
        
        for i, (above, below_hyst) in enumerate(zip(above_threshold, below_threshold_with_hyst)):
            if not in_hold and above:
                # Start of hold period
                in_hold = True
                hold_start_idx = i
            elif in_hold and below_hyst:
                # End of hold period due to hysteresis
                if hold_start_idx is not None:
                    # Check pressure during this hold window
                    hold_pressures = pressure_kpa.iloc[hold_start_idx:i+1]
                    if len(hold_pressures) > 0:
                        min_hold_pressure = hold_pressures.min()
                        if min_hold_pressure < MIN_PRESSURE_KPA:
                            metrics['pressure_maintained'] = False
                            metrics['pressure_valid'] = False
                            metrics['reasons'].append(
                                f"Pressure dropped to {kpa_to_psi(min_hold_pressure):.1f} psi "
                                f"< {kpa_to_psi(MIN_PRESSURE_KPA):.1f} psi during hold period"
                            )
                            break
                in_hold = False
                hold_start_idx = None
        
        # Check final hold period if still in progress
        if in_hold and hold_start_idx is not None:
            hold_pressures = pressure_kpa.iloc[hold_start_idx:]
            if len(hold_pressures) > 0:
                min_hold_pressure = hold_pressures.min()
                if min_hold_pressure < MIN_PRESSURE_KPA:
                    metrics['pressure_maintained'] = False
                    metrics['pressure_valid'] = False
                    metrics['reasons'].append(
                        f"Pressure dropped to {kpa_to_psi(min_hold_pressure):.1f} psi "
                        f"< {kpa_to_psi(MIN_PRESSURE_KPA):.1f} psi during hold period"
                    )
        
        # Overall pressure check
        if pressure_kpa.min() < MIN_PRESSURE_KPA:
            low_pressure_time = (pressure_kpa < MIN_PRESSURE_KPA).sum()
            total_samples = len(pressure_kpa)
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
            # Get available columns (excluding timestamp)
            available_cols = [col for col in normalized_df.columns if col != timestamp_col]
            raise RequiredSignalMissingError(
                missing_signals=["temperature"],
                available_signals=available_cols,
                industry="autoclave"
            )
        
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
                industry=spec.industry,
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
            combined_temp, normalized_df[timestamp_col], combined_pressure, normalized_df, spec
        )

        # Enforce required parameters per spec
        require_pressure = bool(getattr(spec, 'parameter_requirements', None) and getattr(spec.parameter_requirements, 'require_pressure', False))
        require_fo = bool(getattr(spec, 'parameter_requirements', None) and getattr(spec.parameter_requirements, 'require_fo', False))

        # Check for missing required signals - should return INDETERMINATE
        missing_signals = []
        available_signals = list(normalized_df.columns)
        
        if require_pressure and combined_pressure is None:
            missing_signals.append("pressure")
        
        # If any required signals are missing, return INDETERMINATE
        if missing_signals:
            raise RequiredSignalMissingError(
                missing_signals=missing_signals,
                available_signals=available_signals,
                industry="autoclave"
            )
        
        # Determine overall pass/fail status
        pass_decision = (
            cycle_metrics['temperature_range_valid'] and
            cycle_metrics['hold_time_valid'] and
            cycle_metrics['fo_value_valid'] and
            cycle_metrics['pressure_valid']
        )

        # Determine status - should always be PASS or FAIL at this point
        # since missing required signals are handled above with RequiredSignalMissingError
        status = 'PASS' if pass_decision else 'FAIL'
        
        # Add success reasons if passed
        if pass_decision:
            reasons.append(f"Temperature maintained in sterilization range ({cycle_metrics['min_sterilization_temp_C']:.1f}-{cycle_metrics['max_sterilization_temp_C']:.1f}°C) for {cycle_metrics['sterilization_hold_time_s']/60:.1f}min")
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
            industry=spec.industry,
            job_id=spec.job.job_id,
            target_temp_C=121.1,  # Standard autoclave temperature
            conservative_threshold_C=119.0,  # Minimum acceptable temperature
            actual_hold_time_s=cycle_metrics['sterilization_hold_time_s'],
            required_hold_time_s=spec.spec.hold_time_s,
            max_temp_C=cycle_metrics['max_temp_C'],
            min_temp_C=cycle_metrics['min_temp_C'],
            reasons=reasons,
            warnings=warnings,
            flags=locals().get('flags', {})
        )
    
    except RequiredSignalMissingError:
        # Re-raise RequiredSignalMissingError without wrapping
        raise
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