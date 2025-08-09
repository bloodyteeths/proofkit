"""
Shared sensor utility functions for metrics engines.
This module provides common sensor processing functions to avoid circular imports.
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from core.models import SensorMode
from core.temperature_utils import DecisionError


def combine_sensor_readings(df: pd.DataFrame, temp_columns: List[str], 
                          mode: SensorMode, require_at_least: Optional[int] = None,
                          threshold_C: Optional[float] = None) -> pd.Series:
    """
    Combine multiple sensor readings according to the specified mode.
    
    Args:
        df: DataFrame with temperature data
        temp_columns: List of temperature column names
        mode: Sensor combination mode
        require_at_least: Minimum number of valid sensors required
        threshold_C: Threshold for majority_over_threshold mode
        
    Returns:
        Series of combined temperature readings (PMT)
        
    Raises:
        DecisionError: If insufficient valid sensors or invalid mode
    """
    if not temp_columns:
        raise DecisionError("No temperature columns provided for sensor combination")
    
    # Extract temperature data
    temp_data = df[temp_columns].copy()
    
    # Check minimum sensor requirement
    if require_at_least is not None:
        valid_sensors_per_sample = temp_data.notna().sum(axis=1)
        insufficient_samples = valid_sensors_per_sample < require_at_least
        if insufficient_samples.any():
            count = insufficient_samples.sum()
            raise DecisionError(f"Insufficient valid sensors: {count} samples have < {require_at_least} sensors")
    
    if mode == SensorMode.MIN_OF_SET:
        # Take minimum reading across all sensors
        return temp_data.min(axis=1, skipna=True)
    
    elif mode == SensorMode.MEAN_OF_SET:
        # Take mean reading across all sensors
        return temp_data.mean(axis=1, skipna=True)
    
    elif mode == SensorMode.MAJORITY_OVER_THRESHOLD:
        if threshold_C is None:
            raise DecisionError("threshold_C required for majority_over_threshold mode")
        
        # Count sensors above threshold for each sample
        above_threshold = temp_data >= threshold_C
        sensors_above = above_threshold.sum(axis=1)
        total_sensors = temp_data.notna().sum(axis=1)
        
        # Check if at least 'require_at_least' sensors are above threshold
        if require_at_least is not None:
            # Return boolean series: True if enough sensors are above threshold
            return sensors_above >= require_at_least
        else:
            # Majority decision: True if >50% of sensors are above threshold
            return sensors_above > (total_sensors / 2)
    
    else:
        raise DecisionError(f"Unknown sensor combination mode: {mode}")


def combine_sensor_readings_legacy(
    sensor_data: List[Dict[str, Any]],
    combination_method: str = "average"
) -> pd.Series:
    """
    Legacy function for backward compatibility.
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