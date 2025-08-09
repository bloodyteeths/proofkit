"""
Independent Cold Chain Calculator

Simple reference implementation for cold chain temperature monitoring.
Used for differential verification against the main engine.

Example usage:
    from validation.independent.coldchain_daily import detect_excursions
    
    excursions = detect_excursions(
        timestamps=df['timestamp'].values,
        temperatures=df['temperature'].values,
        min_temp=2.0,
        max_temp=8.0
    )
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta
import pandas as pd


def detect_excursions(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_temp: float = 2.0,
    max_temp: float = 8.0,
    min_duration_s: float = 300.0
) -> List[Dict]:
    """
    Detect temperature excursions outside acceptable range.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        min_temp: Minimum acceptable temperature
        max_temp: Maximum acceptable temperature
        min_duration_s: Minimum duration to consider as excursion (default 5 minutes)
        
    Returns:
        List of excursion events with start, end, duration, and severity
    """
    if len(timestamps) != len(temperatures):
        raise ValueError("Timestamps and temperatures must have same length")
        
    if len(timestamps) < 2:
        return []
    
    # Convert timestamps to seconds since first measurement
    if isinstance(timestamps[0], datetime):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    elif isinstance(timestamps[0], pd.Timestamp):
        time_seconds = np.array([(t - timestamps[0]).total_seconds() for t in timestamps])
    else:
        # Assume already numeric (seconds since epoch)
        time_seconds = timestamps - timestamps[0]
    
    excursions = []
    current_excursion = None
    
    for i in range(len(temperatures)):
        temp = temperatures[i]
        time_s = time_seconds[i]
        timestamp = timestamps[i]
        
        # Check if temperature is outside acceptable range
        is_excursion = temp < min_temp or temp > max_temp
        
        if is_excursion and current_excursion is None:
            # Start of new excursion
            current_excursion = {
                'start_time': timestamp,
                'start_time_s': time_s,
                'start_temp': temp,
                'min_temp': temp,
                'max_temp': temp,
                'severity': 'low'
            }
            
        elif is_excursion and current_excursion is not None:
            # Continue existing excursion
            current_excursion['min_temp'] = min(current_excursion['min_temp'], temp)
            current_excursion['max_temp'] = max(current_excursion['max_temp'], temp)
            
            # Update severity based on temperature deviation
            deviation_high = max(0, temp - max_temp)
            deviation_low = max(0, min_temp - temp)
            max_deviation = max(deviation_high, deviation_low)
            
            if max_deviation > 10.0:
                current_excursion['severity'] = 'critical'
            elif max_deviation > 5.0:
                current_excursion['severity'] = 'high'
            elif max_deviation > 2.0:
                current_excursion['severity'] = 'medium'
                
        elif not is_excursion and current_excursion is not None:
            # End of excursion
            duration_s = time_s - current_excursion['start_time_s']
            
            # Only record excursions that meet minimum duration
            if duration_s >= min_duration_s:
                current_excursion['end_time'] = timestamp
                current_excursion['end_time_s'] = time_s
                current_excursion['duration_s'] = duration_s
                current_excursion['duration_minutes'] = duration_s / 60.0
                
                excursions.append(current_excursion)
            
            current_excursion = None
    
    # Handle case where excursion continues to end of data
    if current_excursion is not None:
        duration_s = time_seconds[-1] - current_excursion['start_time_s']
        if duration_s >= min_duration_s:
            current_excursion['end_time'] = timestamps[-1]
            current_excursion['end_time_s'] = time_seconds[-1]
            current_excursion['duration_s'] = duration_s
            current_excursion['duration_minutes'] = duration_s / 60.0
            
            excursions.append(current_excursion)
    
    return excursions


def calculate_mean_kinetic_temperature(
    timestamps: np.ndarray,
    temperatures: np.ndarray
) -> float:
    """
    Calculate Mean Kinetic Temperature (MKT) for stability assessment.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        
    Returns:
        Mean kinetic temperature in Celsius
    """
    if len(temperatures) < 2:
        return np.nan
    
    # Convert temperatures to Kelvin
    temps_k = temperatures + 273.15
    
    # Calculate average of 1/T
    inverse_temp_avg = np.mean(1.0 / temps_k)
    
    # Calculate MKT in Kelvin, then convert back to Celsius
    # MKT = -∆H/R / ln(Σ(e^(-∆H/RT)) / n)
    # Simplified approximation: MKT ≈ 1 / (average(1/T))
    mkt_k = 1.0 / inverse_temp_avg
    mkt_c = mkt_k - 273.15
    
    return mkt_c


def validate_cold_storage(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_temp: float = 2.0,
    max_temp: float = 8.0,
    max_excursion_duration_hours: float = 24.0,
    max_excursion_temp: float = 15.0
) -> bool:
    """
    Validate cold storage temperature compliance.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        min_temp: Minimum acceptable temperature
        max_temp: Maximum acceptable temperature
        max_excursion_duration_hours: Maximum allowed excursion duration
        max_excursion_temp: Maximum allowed excursion temperature
        
    Returns:
        True if storage conditions are compliant
    """
    try:
        # Detect excursions
        excursions = detect_excursions(timestamps, temperatures, min_temp, max_temp)
        
        # Check overall temperature range
        temp_min = np.min(temperatures)
        temp_max = np.max(temperatures)
        
        # Fail if any temperature exceeds critical limits
        if temp_min < -5.0 or temp_max > max_excursion_temp:
            return False
        
        # Check excursion durations and severity
        for excursion in excursions:
            duration_hours = excursion['duration_s'] / 3600.0
            
            # Critical excursions always fail
            if excursion['severity'] == 'critical':
                return False
                
            # Long excursions fail
            if duration_hours > max_excursion_duration_hours:
                return False
                
            # High severity excursions with moderate duration fail
            if excursion['severity'] == 'high' and duration_hours > 4.0:
                return False
        
        return True
        
    except Exception:
        return False


def calculate_temperature_uniformity(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    window_size_minutes: float = 60.0
) -> float:
    """
    Calculate temperature uniformity over rolling windows.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        window_size_minutes: Window size for uniformity calculation
        
    Returns:
        Average temperature standard deviation across all windows
    """
    if len(timestamps) < 3:
        return np.nan
    
    # Convert timestamps to minutes since start
    if isinstance(timestamps[0], datetime):
        time_minutes = np.array([(t - timestamps[0]).total_seconds() / 60.0 for t in timestamps])
    elif isinstance(timestamps[0], pd.Timestamp):
        time_minutes = np.array([(t - timestamps[0]).total_seconds() / 60.0 for t in timestamps])
    else:
        time_minutes = (timestamps - timestamps[0]) / 60.0
    
    # Calculate rolling standard deviations
    std_devs = []
    
    for i in range(len(time_minutes)):
        # Define window boundaries
        window_start = time_minutes[i] - window_size_minutes / 2
        window_end = time_minutes[i] + window_size_minutes / 2
        
        # Find points within window
        window_mask = (time_minutes >= window_start) & (time_minutes <= window_end)
        window_temps = temperatures[window_mask]
        
        if len(window_temps) >= 3:
            std_devs.append(np.std(window_temps))
    
    return np.mean(std_devs) if std_devs else np.nan


def calculate_daily_compliance(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_temp: float = 2.0,
    max_temp: float = 8.0
) -> Dict[str, float]:
    """
    Calculate daily compliance metrics for cold chain monitoring.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        min_temp: Minimum acceptable temperature
        max_temp: Maximum acceptable temperature
        
    Returns:
        Dict with compliance metrics
    """
    if len(timestamps) == 0 or len(temperatures) == 0:
        return {
            'overall_compliance_pct': 0.0,
            'total_excursions': 0,
            'total_excursion_duration_s': 0.0,
            'mean_kinetic_temperature_C': np.nan
        }
    
    # Detect excursions
    excursions = detect_excursions(timestamps, temperatures, min_temp, max_temp, min_duration_s=0.0)
    
    # Calculate total duration
    if isinstance(timestamps[0], datetime):
        total_duration_s = (timestamps[-1] - timestamps[0]).total_seconds()
    elif isinstance(timestamps[0], pd.Timestamp):
        total_duration_s = (timestamps[-1] - timestamps[0]).total_seconds()
    else:
        total_duration_s = timestamps[-1] - timestamps[0]
    
    # Calculate excursion time
    total_excursion_time_s = sum(exc['duration_s'] for exc in excursions)
    
    # Calculate compliance percentage
    if total_duration_s > 0:
        compliance_time_s = total_duration_s - total_excursion_time_s
        compliance_pct = (compliance_time_s / total_duration_s) * 100.0
    else:
        compliance_pct = 0.0
    
    # Calculate MKT
    mkt = calculate_mean_kinetic_temperature(timestamps, temperatures)
    
    return {
        'overall_compliance_pct': compliance_pct,
        'total_excursions': len(excursions),
        'total_excursion_duration_s': total_excursion_time_s,
        'mean_kinetic_temperature_C': mkt
    }