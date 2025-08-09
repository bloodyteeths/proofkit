"""
Independent Concrete Window Calculator

Simple reference implementation for concrete curing window validation.
Calculates percentage of time within temperature range during 24-hour windows.
Used for differential verification against the main engine.

Example usage:
    from validation.independent.concrete_window import calculate_curing_compliance
    
    curing_result = calculate_curing_compliance(
        timestamps=df['timestamp'].values,
        temperatures=df['temperature'].values,
        min_temp_C=10.0,
        max_temp_C=35.0,
        window_hours=24
    )
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta


def calculate_curing_compliance(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_temp_C: float = 10.0,
    max_temp_C: float = 35.0,
    window_hours: float = 24.0,
    min_compliance_pct: float = 95.0
) -> Dict[str, Any]:
    """
    Calculate concrete curing compliance within temperature windows.
    
    Args:
        timestamps: Array of timestamps (datetime objects or seconds since epoch)
        temperatures: Array of temperature values in Celsius
        min_temp_C: Minimum acceptable curing temperature
        max_temp_C: Maximum acceptable curing temperature
        window_hours: Window duration in hours for compliance calculation
        min_compliance_pct: Minimum required compliance percentage
        
    Returns:
        Dict with curing compliance analysis
    """
    if len(timestamps) != len(temperatures):
        raise ValueError("Timestamps and temperatures must have same length")
        
    if len(timestamps) == 0:
        return {
            'overall_pass': False,
            'windows': [],
            'total_windows': 0,
            'compliant_windows': 0,
            'failed_windows': 0,
            'overall_compliance_pct': 0.0,
            'errors': ["No data provided"]
        }
    
    # Convert to pandas DataFrame for easier handling
    df = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps),
        'temperature': temperatures
    })
    
    # Remove NaN temperatures
    df_clean = df.dropna(subset=['temperature']).sort_values('timestamp')
    
    if len(df_clean) == 0:
        return {
            'overall_pass': False,
            'windows': [],
            'total_windows': 0,
            'compliant_windows': 0,
            'failed_windows': 0,
            'overall_compliance_pct': 0.0,
            'errors': ["All temperature values are NaN"]
        }
    
    # Calculate window duration in seconds
    window_seconds = window_hours * 3600
    
    # Generate sliding windows
    start_time = df_clean['timestamp'].min()
    end_time = df_clean['timestamp'].max()
    total_duration = (end_time - start_time).total_seconds()
    
    if total_duration < window_seconds:
        # Single window covering entire dataset
        windows = [_analyze_single_window(
            df_clean, start_time, end_time, min_temp_C, max_temp_C, 
            min_compliance_pct, window_id=0
        )]
    else:
        # Multiple overlapping windows (every 12 hours for 24-hour windows)
        window_step_hours = window_hours / 2  # 50% overlap
        window_step_seconds = window_step_hours * 3600
        
        windows = []
        window_id = 0
        current_start = start_time
        
        while current_start + pd.Timedelta(seconds=window_seconds) <= end_time:
            current_end = current_start + pd.Timedelta(seconds=window_seconds)
            
            # Get data within this window
            window_data = df_clean[
                (df_clean['timestamp'] >= current_start) & 
                (df_clean['timestamp'] <= current_end)
            ]
            
            if len(window_data) > 0:
                window_result = _analyze_single_window(
                    window_data, current_start, current_end,
                    min_temp_C, max_temp_C, min_compliance_pct, window_id
                )
                windows.append(window_result)
            
            current_start += pd.Timedelta(seconds=window_step_seconds)
            window_id += 1
    
    # Calculate overall statistics
    total_windows = len(windows)
    compliant_windows = sum(1 for w in windows if w['compliant'])
    failed_windows = total_windows - compliant_windows
    
    if total_windows > 0:
        overall_compliance_pct = sum(w['compliance_pct'] for w in windows) / total_windows
        overall_pass = compliant_windows >= (total_windows * 0.8)  # 80% of windows must pass
    else:
        overall_compliance_pct = 0.0
        overall_pass = False
    
    return {
        'overall_pass': overall_pass,
        'windows': windows,
        'total_windows': total_windows,
        'compliant_windows': compliant_windows,
        'failed_windows': failed_windows,
        'overall_compliance_pct': overall_compliance_pct,
        'window_hours': window_hours,
        'temp_range': f"[{min_temp_C}, {max_temp_C}]°C",
        'min_compliance_pct': min_compliance_pct,
        'errors': []
    }


def _analyze_single_window(
    window_data: pd.DataFrame,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    min_temp_C: float,
    max_temp_C: float,
    min_compliance_pct: float,
    window_id: int
) -> Dict[str, Any]:
    """Analyze a single curing window."""
    if len(window_data) < 2:
        return {
            'window_id': window_id,
            'start_time': start_time,
            'end_time': end_time,
            'duration_s': (end_time - start_time).total_seconds(),
            'compliance_pct': 0.0,
            'compliant': False,
            'total_measurements': len(window_data),
            'in_range_measurements': 0,
            'min_temp_C': np.nan,
            'max_temp_C': np.nan,
            'avg_temp_C': np.nan,
            'total_time_s': 0.0,
            'in_range_time_s': 0.0,
            'errors': ["Insufficient data in window"]
        }
    
    # Sort by timestamp
    window_sorted = window_data.sort_values('timestamp')
    timestamps = window_sorted['timestamp'].values
    temperatures = window_sorted['temperature'].values
    
    # Calculate time-weighted compliance
    total_time_s = 0.0
    in_range_time_s = 0.0
    
    for i in range(len(timestamps) - 1):
        # Time interval between measurements
        time_diff_s = (timestamps[i + 1] - timestamps[i]).total_seconds()
        
        # Use temperature at start of interval
        temp = temperatures[i]
        is_in_range = (min_temp_C <= temp <= max_temp_C)
        
        total_time_s += time_diff_s
        if is_in_range:
            in_range_time_s += time_diff_s
    
    # Calculate compliance percentage
    if total_time_s > 0:
        compliance_pct = (in_range_time_s / total_time_s) * 100.0
    else:
        compliance_pct = 0.0
    
    # Count measurements in range
    in_range_measurements = len(window_sorted[
        (window_sorted['temperature'] >= min_temp_C) & 
        (window_sorted['temperature'] <= max_temp_C)
    ])
    
    return {
        'window_id': window_id,
        'start_time': start_time,
        'end_time': end_time,
        'duration_s': (end_time - start_time).total_seconds(),
        'compliance_pct': compliance_pct,
        'compliant': compliance_pct >= min_compliance_pct,
        'total_measurements': len(window_sorted),
        'in_range_measurements': in_range_measurements,
        'min_temp_C': float(temperatures.min()),
        'max_temp_C': float(temperatures.max()),
        'avg_temp_C': float(temperatures.mean()),
        'total_time_s': total_time_s,
        'in_range_time_s': in_range_time_s,
        'errors': []
    }


def calculate_strength_gain_estimation(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    placement_temp_C: float = 20.0,
    maturity_factor: float = 13.65
) -> Dict[str, Any]:
    """
    Estimate concrete strength gain using maturity method.
    
    Maturity = sum((T_avg - T_datum) * time_interval) where:
    - T_avg is average concrete temperature during time interval
    - T_datum is datum temperature (-10°C for Type I cement)
    - time_interval is in hours
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values in Celsius
        placement_temp_C: Initial placement temperature
        maturity_factor: Factor for strength estimation (varies by mix design)
        
    Returns:
        Dict with maturity and estimated strength
    """
    if len(timestamps) != len(temperatures):
        raise ValueError("Timestamps and temperatures must have same length")
        
    if len(timestamps) < 2:
        return {
            'total_maturity_C_h': 0.0,
            'estimated_strength_pct': 0.0,
            'avg_temp_C': np.nan,
            'duration_hours': 0.0,
            'errors': ["Insufficient data for maturity calculation"]
        }
    
    # Convert to pandas for easier handling
    df = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps),
        'temperature': temperatures
    })
    
    # Remove NaN values and sort
    df_clean = df.dropna(subset=['temperature']).sort_values('timestamp')
    
    if len(df_clean) < 2:
        return {
            'total_maturity_C_h': 0.0,
            'estimated_strength_pct': 0.0,
            'avg_temp_C': np.nan,
            'duration_hours': 0.0,
            'errors': ["All temperature values are NaN"]
        }
    
    # Datum temperature for Type I cement
    datum_temp_C = -10.0
    
    # Calculate maturity using temperature-time areas
    total_maturity = 0.0
    timestamps_clean = df_clean['timestamp'].values
    temperatures_clean = df_clean['temperature'].values
    
    for i in range(len(timestamps_clean) - 1):
        # Time interval in hours
        time_diff_h = (timestamps_clean[i + 1] - timestamps_clean[i]).total_seconds() / 3600
        
        # Average temperature during interval
        avg_temp_C = (temperatures_clean[i] + temperatures_clean[i + 1]) / 2.0
        
        # Maturity contribution (temperature above datum times time)
        if avg_temp_C > datum_temp_C:
            maturity_increment = (avg_temp_C - datum_temp_C) * time_diff_h
            total_maturity += maturity_increment
    
    # Estimate strength as percentage of 28-day strength
    # Using simplified relationship: Strength% = Maturity / (Maturity + maturity_factor)
    if total_maturity > 0:
        estimated_strength_pct = (total_maturity / (total_maturity + maturity_factor)) * 100
    else:
        estimated_strength_pct = 0.0
    
    total_duration_hours = (timestamps_clean[-1] - timestamps_clean[0]).total_seconds() / 3600
    
    return {
        'total_maturity_C_h': total_maturity,
        'estimated_strength_pct': min(estimated_strength_pct, 100.0),
        'avg_temp_C': float(temperatures_clean.mean()),
        'min_temp_C': float(temperatures_clean.min()),
        'max_temp_C': float(temperatures_clean.max()),
        'duration_hours': total_duration_hours,
        'datum_temp_C': datum_temp_C,
        'maturity_factor': maturity_factor,
        'errors': []
    }


def validate_concrete_curing(
    timestamps: np.ndarray,
    temperatures: np.ndarray,
    min_temp_C: float = 10.0,
    max_temp_C: float = 35.0,
    window_hours: float = 24.0,
    min_compliance_pct: float = 95.0,
    required_strength_pct: float = 50.0,
    curing_days: int = 7
) -> Dict[str, Any]:
    """
    Complete concrete curing validation.
    
    Args:
        timestamps: Array of timestamps
        temperatures: Array of temperature values
        min_temp_C: Minimum acceptable curing temperature
        max_temp_C: Maximum acceptable curing temperature
        window_hours: Window duration for compliance checks
        min_compliance_pct: Minimum required compliance per window
        required_strength_pct: Required strength percentage
        curing_days: Target curing period in days
        
    Returns:
        Dict with complete curing validation results
    """
    # Calculate window compliance
    compliance_result = calculate_curing_compliance(
        timestamps, temperatures, min_temp_C, max_temp_C, 
        window_hours, min_compliance_pct
    )
    
    # Calculate maturity and strength estimation
    maturity_result = calculate_strength_gain_estimation(timestamps, temperatures)
    
    # Determine pass/fail status
    temperature_pass = compliance_result['overall_pass']
    strength_pass = maturity_result['estimated_strength_pct'] >= required_strength_pct
    
    # Check curing duration
    if len(timestamps) >= 2:
        total_duration_days = (
            pd.to_datetime(timestamps[-1]) - pd.to_datetime(timestamps[0])
        ).total_seconds() / (24 * 3600)
        duration_pass = total_duration_days >= curing_days
    else:
        total_duration_days = 0.0
        duration_pass = False
    
    overall_pass = temperature_pass and strength_pass and duration_pass
    
    reasons = []
    if not temperature_pass:
        failed_pct = (compliance_result['failed_windows'] / 
                     max(1, compliance_result['total_windows']) * 100)
        reasons.append(f"Temperature compliance failed: {failed_pct:.1f}% of windows failed")
    
    if not strength_pass:
        reasons.append(
            f"Insufficient strength development: {maturity_result['estimated_strength_pct']:.1f}% "
            f"< required {required_strength_pct}%"
        )
    
    if not duration_pass:
        reasons.append(f"Insufficient curing duration: {total_duration_days:.1f} days < {curing_days} days")
    
    if overall_pass:
        reasons.append(
            f"Curing successful: {compliance_result['overall_compliance_pct']:.1f}% temp compliance, "
            f"{maturity_result['estimated_strength_pct']:.1f}% strength in {total_duration_days:.1f} days"
        )
    
    return {
        'pass': overall_pass,
        'temperature_pass': temperature_pass,
        'strength_pass': strength_pass,
        'duration_pass': duration_pass,
        'compliance_pct': compliance_result['overall_compliance_pct'],
        'estimated_strength_pct': maturity_result['estimated_strength_pct'],
        'total_maturity_C_h': maturity_result['total_maturity_C_h'],
        'curing_duration_days': total_duration_days,
        'compliant_windows': compliance_result['compliant_windows'],
        'total_windows': compliance_result['total_windows'],
        'min_temp_C': maturity_result.get('min_temp_C', np.nan),
        'max_temp_C': maturity_result.get('max_temp_C', np.nan),
        'avg_temp_C': maturity_result.get('avg_temp_C', np.nan),
        'requirements': {
            'min_temp_C': min_temp_C,
            'max_temp_C': max_temp_C,
            'window_hours': window_hours,
            'min_compliance_pct': min_compliance_pct,
            'required_strength_pct': required_strength_pct,
            'curing_days': curing_days
        },
        'reasons': reasons,
        'errors': compliance_result.get('errors', []) + maturity_result.get('errors', []),
        'window_details': compliance_result.get('windows', [])
    }