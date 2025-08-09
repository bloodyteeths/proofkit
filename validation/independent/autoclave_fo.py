"""
Independent Autoclave F0 Calculator

Simple reference implementation for F0 value calculation in steam sterilization.
Used for differential verification against the main engine.

Example usage:
    from validation.independent.autoclave_fo import calculate_fo_value
    
    fo_value = calculate_fo_value(
        timestamps=df['timestamp'].values,
        temperatures=df['temperature'].values,
        reference_temp=121.0
    )
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from datetime import datetime
import pandas as pd


def calculate_fo_value(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    reference_temp: float = 121.0,
    z_value: float = 10.0
) -> float:
    """
    Calculate F0 value (equivalent sterilization time at reference temperature).
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        reference_temp: Reference temperature for F0 calculation (default 121°C)
        z_value: Z-value for thermal death time calculation (default 10°C)
        
    Returns:
        F0 value in minutes
    """
    if len(timestamps) != len(temperatures):
        raise ValueError("Timestamps and temperatures must have same length")
        
    if len(timestamps) < 2:
        return 0.0
    
    # Convert timestamps to seconds since first measurement
    if isinstance(timestamps[0], datetime):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    elif isinstance(timestamps[0], pd.Timestamp):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    else:
        # Assume already numeric (seconds since epoch)
        time_seconds = timestamps - timestamps[0]
    
    # Calculate lethal rate at each time point
    # L = 10^((T - T_ref) / z)
    lethal_rates = np.power(10, (temperatures - reference_temp) / z_value)
    
    # Integrate using trapezoidal rule to get F0 value
    fo_value = 0.0
    
    for i in range(1, len(time_seconds)):
        dt = time_seconds[i] - time_seconds[i-1]  # seconds
        avg_lethal_rate = (lethal_rates[i-1] + lethal_rates[i]) / 2
        
        # Add contribution to F0 (convert seconds to minutes)
        fo_value += avg_lethal_rate * dt / 60.0
    
    return fo_value


def calculate_sterilization_hold(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_temp: float = 121.0,
    hysteresis: float = 2.0
) -> float:
    """
    Calculate hold time at sterilization temperature.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        min_temp: Minimum sterilization temperature
        hysteresis: Hysteresis for temperature threshold
        
    Returns:
        Hold time in seconds
    """
    if len(timestamps) < 2:
        return 0.0
    
    # Convert timestamps to seconds
    if isinstance(timestamps[0], datetime):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    elif isinstance(timestamps[0], pd.Timestamp):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    else:
        time_seconds = timestamps - timestamps[0]
    
    # Apply hysteresis logic for sterilization temperature
    above_threshold = np.zeros(len(temperatures), dtype=bool)
    current_state = False
    
    for i in range(len(temperatures)):
        temp = temperatures[i]
        
        if current_state:
            # Currently at sterilization temp - need to drop below (min_temp - hysteresis)
            if temp < min_temp - hysteresis:
                current_state = False
        else:
            # Currently below sterilization temp - need to rise above min_temp
            if temp >= min_temp:
                current_state = True
                
        above_threshold[i] = current_state
    
    # Calculate longest continuous hold
    max_hold = 0.0
    current_hold_start = None
    
    for i in range(len(above_threshold)):
        if above_threshold[i] and current_hold_start is None:
            # Start of sterilization hold
            current_hold_start = time_seconds[i]
        elif not above_threshold[i] and current_hold_start is not None:
            # End of sterilization hold
            hold_duration = time_seconds[i-1] - current_hold_start
            max_hold = max(max_hold, hold_duration)
            current_hold_start = None
    
    # Check if we ended while still in hold
    if current_hold_start is not None:
        hold_duration = time_seconds[-1] - current_hold_start
        max_hold = max(max_hold, hold_duration)
    
    return max_hold


def validate_sterilization_cycle(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_fo: float = 8.0,
    min_temp: float = 121.0,
    min_hold_time: float = 900.0
) -> bool:
    """
    Validate complete sterilization cycle.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        min_fo: Minimum F0 value required
        min_temp: Minimum sterilization temperature
        min_hold_time: Minimum hold time in seconds
        
    Returns:
        True if cycle passes validation
    """
    try:
        # Calculate F0 value
        fo_value = calculate_fo_value(timestamps, temperatures, min_temp)
        
        # Calculate hold time
        hold_time = calculate_sterilization_hold(timestamps, temperatures, min_temp)
        
        # Check both criteria
        fo_pass = fo_value >= min_fo
        hold_pass = hold_time >= min_hold_time
        
        return fo_pass and hold_pass
        
    except Exception:
        return False


def calculate_fo_metrics(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    reference_temp: float = 121.0,
    z_value: float = 10.0
) -> Dict[str, float]:
    """
    Calculate F0 value and related metrics for autoclave validation.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        reference_temp: Reference temperature for F0 calculation (default 121°C)
        z_value: Z-value for thermal death time calculation (default 10°C)
        
    Returns:
        Dict with F0 value and sterilization metrics
    """
    if len(timestamps) == 0 or len(temperatures) == 0:
        return {
            'fo_value': 0.0,
            'hold_time_s': 0.0,
            'max_temp_C': np.nan,
            'min_temp_C': np.nan,
            'sterilization_pass': False
        }
    
    fo_value = calculate_fo_value(timestamps, temperatures, reference_temp, z_value)
    hold_time = calculate_sterilization_hold(timestamps, temperatures, reference_temp)
    
    return {
        'fo_value': fo_value,
        'hold_time_s': hold_time,
        'max_temp_C': float(np.max(temperatures)),
        'min_temp_C': float(np.min(temperatures)),
        'sterilization_pass': fo_value >= 8.0 and hold_time >= 900.0
    }