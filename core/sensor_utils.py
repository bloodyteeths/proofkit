"""
Shared sensor utility functions for metrics engines.
This module provides common sensor processing functions to avoid circular imports.
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np


def combine_sensor_readings(
    sensor_data: List[Dict[str, Any]],
    combination_method: str = "average"
) -> pd.Series:
    """
    Combine multiple sensor readings into a single series.
    
    Args:
        sensor_data: List of sensor data dictionaries
        combination_method: How to combine ("average", "min", "max")
    
    Returns:
        Combined temperature series
    """
    if not sensor_data:
        return pd.Series(dtype=float)
    
    # Convert all sensor data to Series
    series_list = []
    for sensor in sensor_data:
        if 'temperatures' in sensor and sensor['temperatures']:
            series_list.append(pd.Series(sensor['temperatures']))
    
    if not series_list:
        return pd.Series(dtype=float)
    
    # Align all series to same index
    df = pd.concat(series_list, axis=1)
    
    # Combine based on method
    if combination_method == "average":
        return df.mean(axis=1)
    elif combination_method == "min":
        return df.min(axis=1)
    elif combination_method == "max":
        return df.max(axis=1)
    else:
        return df.mean(axis=1)


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Float value
    """
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert a value to int.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Integer value
    """
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default