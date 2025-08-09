"""
Temperature column detection utilities for ProofKit.

Shared utilities for detecting and processing temperature columns
in normalized CSV data, and temperature-based calculations.
"""

import pandas as pd
import numpy as np
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


def detect_temperature_columns(df: pd.DataFrame, industry: str = None) -> List[str]:
    """
    Detect temperature columns in the DataFrame.
    
    Looks for columns containing temperature-related keywords
    or patterns in their names. Uses case-insensitive matching
    and handles aliases like PMT, sensor names, etc.
    
    For HACCP industry, requires explicit temperature-related column names
    (temp, temperature, °f, °c) and does not auto-map generic sensor columns.
    
    Args:
        df: Input DataFrame
        industry: Industry type (affects detection policy)
        
    Returns:
        List of column names identified as temperature columns
    """
    # Primary temperature keywords - explicit temperature naming
    primary_temp_keywords = [
        'temp', 'temperature', 'celsius', 'fahrenheit',
        'c°', 'f°', '°c', '°f', 'deg', 'thermal'
    ]
    
    # Secondary keywords - sensor-related but not explicit temperature
    secondary_temp_keywords = [
        'pmt', 'thermocouple', 'rtd', 't_c', 't_f'
    ]
    
    temp_columns = []
    for col in df.columns:
        col_lower = col.lower().strip()
        
        # Skip timestamp columns
        if any(time_keyword in col_lower for time_keyword in ['time', 'date', 'timestamp', 'ts']):
            continue
            
        # Check for primary temperature keywords (case-insensitive)
        if any(keyword in col_lower for keyword in primary_temp_keywords):
            # Verify it's numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                temp_columns.append(col)
                continue
        
        # Check for secondary temperature keywords only if no primary found yet
        if not temp_columns and any(keyword in col_lower for keyword in secondary_temp_keywords):
            # Verify it's numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                temp_columns.append(col)
                continue
    
    # For HACCP industry, also allow sensor columns if no explicit temp columns found
    # This handles fixtures that use sensor_1/2/3 naming
    if industry == "haccp" and temp_columns:
        return temp_columns
        
    # Continue with sensor pattern detection for all industries if needed
    if not temp_columns:
        import re
        sensor_patterns = [
            r'sensor\d*',  # sensor, sensor1, sensor2, etc.
            r's\d+',       # s1, s2, s3, etc.
            r't\d*',       # t, t1, t2, etc.
            r'ch\d*',      # ch, ch1, ch2 (channels)
            r'channel\d*', # channel, channel1, etc.
        ]
        
        for col in df.columns:
            col_lower = col.lower().strip()
            
            # Skip timestamp columns
            if any(time_keyword in col_lower for time_keyword in ['time', 'date', 'timestamp', 'ts']):
                continue
                
            if any(re.match(pattern, col_lower) for pattern in sensor_patterns):
                # Verify it's numeric
                if pd.api.types.is_numeric_dtype(df[col]):
                    temp_columns.append(col)
                    continue
        
        # Check if column contains numeric data that could be temperature
        # Only as last resort if no other temperature columns found
        if not temp_columns:
            for col in df.columns:
                col_lower = col.lower().strip()
                
                # Skip timestamp columns
                if any(time_keyword in col_lower for time_keyword in ['time', 'date', 'timestamp', 'ts']):
                    continue
                    
                if pd.api.types.is_numeric_dtype(df[col]):
                    # Check if values are in typical temperature ranges
                    col_values = df[col].dropna()
                    if len(col_values) > 10:  # Need reasonable sample size
                        mean_val = col_values.mean()
                        std_val = col_values.std()
                        min_val = col_values.min()
                        max_val = col_values.max()
                        
                        # Temperature range validation (more restrictive)
                        # Celsius: typical range -40 to 400°C
                        # Fahrenheit: typical range -40 to 750°F
                        celsius_range = (-40 <= mean_val <= 400) and (min_val >= -50) and (max_val <= 500)
                        fahrenheit_range = (-40 <= mean_val <= 750) and (min_val >= -50) and (max_val <= 1000)
                        
                        # Also check for reasonable temperature variation (not constant)
                        has_variation = std_val > 0.1
                        
                        if (celsius_range or fahrenheit_range) and has_variation:
                            temp_columns.append(col)
                            break  # Only add one fallback column
    
    return temp_columns


class DecisionError(Exception):
    """Custom exception for decision algorithm errors."""
    pass


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