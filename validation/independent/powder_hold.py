"""
Independent Powder Hold Calculator

Simple reference implementation for powder coating cure hold time calculation.
Used for differential verification against the main engine.

Example usage:
    from validation.independent.powder_hold import calculate_hold_time
    
    hold_time = calculate_hold_time(
        timestamps=df['timestamp'].values,
        temperatures=df['temperature'].values,
        threshold=180.0,
        hysteresis=2.0,
        continuous_only=True
    )
"""

import numpy as np
from typing import List, Tuple, Optional
from datetime import datetime
import pandas as pd


def calculate_hold_time(
    timestamps: np.ndarray,
    temperatures: np.ndarray, 
    threshold: float,
    hysteresis: float = 2.0,
    continuous_only: bool = True
) -> float:
    """
    Calculate hold time above threshold with hysteresis.
    
    Args:
        timestamps: Array of timestamps (datetime objects or seconds since epoch)
        temperatures: Array of temperature values in Celsius
        threshold: Temperature threshold in Celsius
        hysteresis: Hysteresis value in Celsius (default 2.0)
        continuous_only: If True, return longest continuous interval. 
                        If False, return cumulative time.
                        
    Returns:
        Hold time in seconds
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
    
    # Apply hysteresis logic
    above_threshold = np.zeros(len(temperatures), dtype=bool)
    current_state = False
    
    for i in range(len(temperatures)):
        temp = temperatures[i]
        
        if current_state:
            # Currently above threshold - need to drop below (threshold - hysteresis)
            if temp < threshold - hysteresis:
                current_state = False
        else:
            # Currently below threshold - need to rise above threshold
            if temp >= threshold:
                current_state = True
                
        above_threshold[i] = current_state
    
    if not np.any(above_threshold):
        return 0.0
        
    if continuous_only:
        return _calculate_longest_continuous_hold(time_seconds, above_threshold)
    else:
        return _calculate_cumulative_hold(time_seconds, above_threshold)


def _calculate_longest_continuous_hold(time_seconds: np.ndarray, above_threshold: np.ndarray) -> float:
    """Calculate longest continuous interval above threshold."""
    max_hold = 0.0
    current_hold_start = None
    
    for i in range(len(above_threshold)):
        if above_threshold[i] and current_hold_start is None:
            # Start of hold interval
            current_hold_start = time_seconds[i]
        elif not above_threshold[i] and current_hold_start is not None:
            # End of hold interval
            hold_duration = time_seconds[i-1] - current_hold_start
            max_hold = max(max_hold, hold_duration)
            current_hold_start = None
    
    # Check if we ended while still in hold
    if current_hold_start is not None:
        hold_duration = time_seconds[-1] - current_hold_start
        max_hold = max(max_hold, hold_duration)
        
    return max_hold


def _calculate_cumulative_hold(time_seconds: np.ndarray, above_threshold: np.ndarray) -> float:
    """Calculate cumulative time above threshold."""
    total_hold = 0.0
    current_hold_start = None
    
    for i in range(len(above_threshold)):
        if above_threshold[i] and current_hold_start is None:
            # Start of hold interval
            current_hold_start = time_seconds[i]
        elif not above_threshold[i] and current_hold_start is not None:
            # End of hold interval
            hold_duration = time_seconds[i-1] - current_hold_start
            total_hold += hold_duration
            current_hold_start = None
    
    # Check if we ended while still in hold
    if current_hold_start is not None:
        hold_duration = time_seconds[-1] - current_hold_start
        total_hold += hold_duration
        
    return total_hold


def calculate_ramp_rate(timestamps: np.ndarray, temperatures: np.ndarray) -> float:
    """
    Calculate maximum ramp rate using central differences.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        
    Returns:
        Maximum ramp rate in °C/min
    """
    if len(timestamps) < 3:
        return 0.0
        
    # Convert to seconds since start
    if isinstance(timestamps[0], datetime):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    elif isinstance(timestamps[0], pd.Timestamp):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    else:
        time_seconds = timestamps - timestamps[0]
    
    # Calculate central differences for interior points
    derivatives = []
    
    for i in range(1, len(temperatures) - 1):
        dt = time_seconds[i+1] - time_seconds[i-1]
        dtemp = temperatures[i+1] - temperatures[i-1]
        
        if dt > 0:
            derivative = dtemp / dt  # °C/s
            derivatives.append(derivative * 60)  # Convert to °C/min
    
    if not derivatives:
        return 0.0
        
    return max(derivatives)


def calculate_time_to_threshold(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    threshold: float
) -> float:
    """
    Calculate time from first sample to first threshold crossing.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        threshold: Temperature threshold
        
    Returns:
        Time to threshold in seconds, or -1 if never reached
    """
    # Find first crossing
    for i, temp in enumerate(temperatures):
        if temp >= threshold:
            if isinstance(timestamps[0], datetime):
                return (timestamps[i] - timestamps[0]).total_seconds()
            elif isinstance(timestamps[0], pd.Timestamp):
                return (timestamps[i] - timestamps[0]).total_seconds()
            else:
                return timestamps[i] - timestamps[0]
                
    return -1.0  # Never reached threshold