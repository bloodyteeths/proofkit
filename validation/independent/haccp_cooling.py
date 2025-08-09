"""
Independent HACCP Cooling Calculator

Simple reference implementation for HACCP cooling phase validation.
Used for differential verification against the main engine.

Example usage:
    from validation.independent.haccp_cooling import validate_cooling_phases
    
    phases = validate_cooling_phases(
        timestamps=df['timestamp'].values,
        temperatures=df['temperature'].values
    )
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime


def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (temp_f - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (temp_c * 9.0 / 5.0) + 32.0


def linear_interpolate_crossing_time(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    target_temp_C: float,
    direction: str = 'cooling'
) -> Optional[float]:
    """
    Find time when temperature crosses target using linear interpolation.
    
    Args:
        timestamps: Array of timestamps (datetime objects or seconds since epoch)
        temperatures: Array of temperature values in Celsius
        target_temp_C: Target temperature in Celsius
        direction: 'cooling' (decreasing) or 'heating' (increasing)
        
    Returns:
        Time in seconds from start when target is reached, or None if never reached
    """
    if len(timestamps) != len(temperatures):
        raise ValueError("Timestamps and temperatures must have same length")
        
    if len(timestamps) < 2:
        return None
        
    # Convert timestamps to seconds since first measurement
    if isinstance(timestamps[0], (datetime, pd.Timestamp)):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() 
                               for t in timestamps])
    else:
        time_seconds = timestamps - timestamps[0]
    
    for i in range(len(temperatures) - 1):
        temp_current = temperatures[i]
        temp_next = temperatures[i + 1]
        time_current = time_seconds[i]
        time_next = time_seconds[i + 1]
        
        if direction == 'cooling':
            # Check if we cross target going downward
            if temp_current >= target_temp_C >= temp_next:
                # Linear interpolation to find exact crossing time
                if abs(temp_current - temp_next) < 1e-10:
                    return time_current
                
                # Linear interpolation formula
                time_fraction = (target_temp_C - temp_current) / (temp_next - temp_current)
                crossing_time = time_current + (time_next - time_current) * time_fraction
                return crossing_time
                
        else:  # heating
            # Check if we cross target going upward
            if temp_current <= target_temp_C <= temp_next:
                # Linear interpolation to find exact crossing time
                if abs(temp_current - temp_next) < 1e-10:
                    return time_current
                
                time_fraction = (target_temp_C - temp_current) / (temp_next - temp_current)
                crossing_time = time_current + (time_next - time_current) * time_fraction
                return crossing_time
    
    return None


def validate_cooling_phases(
    timestamps: np.ndarray,
    temperatures: np.ndarray
) -> Dict[str, Any]:
    """
    Validate HACCP cooling phases according to FDA Food Code.
    
    Phase 1: Cool from 135°F (57.2°C) to 70°F (21.1°C) within 2 hours
    Phase 2: Cool from 135°F (57.2°C) to 41°F (5.0°C) within 6 hours total
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        
    Returns:
        Dict with phase validation results
    """
    # FDA Food Code temperature thresholds (converted to Celsius)
    temp_135f_c = fahrenheit_to_celsius(135.0)  # 57.2°C
    temp_70f_c = fahrenheit_to_celsius(70.0)    # 21.1°C
    temp_41f_c = fahrenheit_to_celsius(41.0)    # 5.0°C
    
    # Time limits
    phase1_limit_hours = 2.0
    phase2_limit_hours = 6.0
    
    phase1_limit_seconds = phase1_limit_hours * 3600
    phase2_limit_seconds = phase2_limit_hours * 3600
    
    result = {
        'phase1_pass': False,
        'phase2_pass': False,
        'phase1_actual_time_s': None,
        'phase2_actual_time_s': None,
        'phase1_required_time_s': phase1_limit_seconds,
        'phase2_required_time_s': phase2_limit_seconds,
        'start_temp_C': None,
        'end_temp_C': None,
        'min_temp_C': None,
        'max_temp_C': None,
        'errors': []
    }
    
    if len(temperatures) == 0:
        result['errors'].append("No temperature data provided")
        return result
    
    result['start_temp_C'] = float(temperatures[0])
    result['end_temp_C'] = float(temperatures[-1])
    result['min_temp_C'] = float(np.min(temperatures))
    result['max_temp_C'] = float(np.max(temperatures))
    
    # Check if we start at or above 135°F
    if temperatures[0] < temp_135f_c:
        result['errors'].append(f"Starting temperature {temperatures[0]:.1f}°C is below 135°F (57.2°C)")
        return result
    
    # Find time to reach 70°F (Phase 1 endpoint)
    time_to_70f = linear_interpolate_crossing_time(
        timestamps, temperatures, temp_70f_c, 'cooling'
    )
    
    if time_to_70f is not None:
        result['phase1_actual_time_s'] = time_to_70f
        if time_to_70f <= phase1_limit_seconds:
            result['phase1_pass'] = True
    
    # Find time to reach 41°F (Phase 2 endpoint)
    time_to_41f = linear_interpolate_crossing_time(
        timestamps, temperatures, temp_41f_c, 'cooling'
    )
    
    if time_to_41f is not None:
        result['phase2_actual_time_s'] = time_to_41f
        if time_to_41f <= phase2_limit_seconds:
            result['phase2_pass'] = True
    
    return result


def calculate_cooling_rate(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    start_temp_C: float,
    end_temp_C: float
) -> Optional[float]:
    """
    Calculate average cooling rate between two temperatures.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        start_temp_C: Starting temperature
        end_temp_C: Ending temperature
        
    Returns:
        Cooling rate in °C/hour, or None if temperatures not reached
    """
    start_time = linear_interpolate_crossing_time(
        timestamps, temperatures, start_temp_C, 'cooling'
    )
    end_time = linear_interpolate_crossing_time(
        timestamps, temperatures, end_temp_C, 'cooling'
    )
    
    if start_time is None or end_time is None:
        return None
    
    if end_time <= start_time:
        return None
    
    time_diff_hours = (end_time - start_time) / 3600
    temp_diff = start_temp_C - end_temp_C
    
    return temp_diff / time_diff_hours