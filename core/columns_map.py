#!/usr/bin/env python3
"""
Column Mapping Adapter for CSV Headers

Simple mapping dictionary for common temperature sensor headers
across different industries and vendors.

Example usage:
    from core.columns_map import get_column_mapping
    mapping = get_column_mapping()
    normalized_df = df.rename(columns=mapping)
"""

from typing import Dict, Optional

# Common temperature column header variations
TEMPERATURE_MAPPINGS = {
    # Standard variations
    "temperature": "temperature",  # Base case
    "temp": "temperature",
    "t": "temperature", 
    "temp_c": "temperature",
    "temp_celsius": "temperature",
    "temperature_c": "temperature",
    "temperature_celsius": "temperature",
    
    # Industry-specific variations
    "oven_temp": "temperature",
    "chamber_temp": "temperature",
    "probe_temp": "temperature",
    "sensor_temp": "temperature",
    "thermocouple": "temperature",
    "pt100": "temperature",
    "rtd_temp": "temperature",
    
    # Vendor-specific variations
    "temp_deg_c": "temperature",
    "deg_c": "temperature",
    "celsius": "temperature",
    "temp_reading": "temperature",
    "temperature_value": "temperature",
    
    # Common vendor headers with parentheses and brackets
    "temp(c)": "temperature",
    "temp (c)": "temperature",
    "temperature(c)": "temperature",
    "temperature (c)": "temperature",
    "temperature [°c]": "temperature",
    "temperature [c]": "temperature",
    "temperature[°c]": "temperature",
    "temperature[c]": "temperature",
    "temp[°c]": "temperature",
    "temp[c]": "temperature",
    "temp [°c]": "temperature",
    "temp [c]": "temperature",
    
    # Multi-sensor variations
    "temp1": "temperature_1",
    "temp2": "temperature_2", 
    "temp3": "temperature_3",
    "t1": "temperature_1",
    "t2": "temperature_2",
    "t3": "temperature_3",
    "ch1": "temperature_1",
    "ch2": "temperature_2",
    "ch3": "temperature_3",
    "channel1": "temperature_1",
    "channel2": "temperature_2",
    "channel3": "temperature_3",
    "sensor1": "temperature_1",
    "sensor2": "temperature_2",
    "sensor3": "temperature_3",
    "sensor 1": "temperature_1",
    "sensor 2": "temperature_2",
    "sensor 3": "temperature_3",
    "probe1": "temperature_1",
    "probe2": "temperature_2",
    "probe3": "temperature_3",
    "probe 1": "temperature_1",
    "probe 2": "temperature_2",
    "probe 3": "temperature_3",
}

# Timestamp column header variations
TIMESTAMP_MAPPINGS = {
    "timestamp": "timestamp",  # Base case
    "time": "timestamp",
    "datetime": "timestamp", 
    "date_time": "timestamp",
    "date time": "timestamp",
    "time_stamp": "timestamp",
    "ts": "timestamp",
    "date": "timestamp",
    "utc_time": "timestamp",
    "local_time": "timestamp",
    "epoch": "timestamp",
    "unix_time": "timestamp",
    "sample_time": "timestamp",
    "log_time": "timestamp",
    "record_time": "timestamp",
}

# Pressure column variations (for autoclave)
PRESSURE_MAPPINGS = {
    "pressure": "pressure",  # Base case
    "press": "pressure",
    "p": "pressure",
    "p1": "pressure_1",
    "p2": "pressure_2",
    "pressure_bar": "pressure", 
    "pressure_psi": "pressure",
    "pressure(psi)": "pressure",
    "pressure (psi)": "pressure",
    "pressure(bar)": "pressure",
    "pressure (bar)": "pressure",
    "pressure_kpa": "pressure",
    "pressure(kpa)": "pressure",
    "pressure (kpa)": "pressure",
    "bar": "pressure",
    "psi": "pressure",
    "kpa": "pressure",
    "gauge_pressure": "pressure",
    "abs_pressure": "pressure",
    "absolute_pressure": "pressure",
}


# Humidity column variations (for environmental monitoring)
HUMIDITY_MAPPINGS = {
    "rh": "humidity",
    "%rh": "humidity",
    "humidity": "humidity",
    "relative_humidity": "humidity",
    "relative humidity": "humidity",
    "h1": "humidity_1",
    "h2": "humidity_2",
    "humid": "humidity",
    "humidity_percent": "humidity",
    "humidity(%)": "humidity",
    "humidity (%)": "humidity",
    "rh_percent": "humidity",
    "rh(%)": "humidity",
    "rh (%)": "humidity",
}


def get_column_mapping() -> Dict[str, str]:
    """
    Get the complete column mapping dictionary.
    
    Returns:
        Dict mapping common headers to standardized names
    """
    mapping = {}
    mapping.update(TEMPERATURE_MAPPINGS)
    mapping.update(TIMESTAMP_MAPPINGS) 
    mapping.update(PRESSURE_MAPPINGS)
    mapping.update(HUMIDITY_MAPPINGS)
    return mapping


def normalize_column_names(df_columns: list) -> Dict[str, str]:
    """
    Create mapping for actual DataFrame columns.
    
    Performs case-insensitive matching and handles common variations
    in spacing, punctuation, and special characters.
    
    Args:
        df_columns: List of column names from DataFrame
        
    Returns:
        Dict mapping original to standardized names
    """
    mapping = get_column_mapping()
    
    # Case-insensitive matching with enhanced normalization
    column_mapping = {}
    for col in df_columns:
        # Normalize column name for matching
        col_normalized = col.lower().strip()
        
        # Remove common variations in punctuation and spacing
        col_normalized = col_normalized.replace('_', ' ')  # temp_c -> temp c
        col_normalized = col_normalized.replace('-', ' ')  # temp-c -> temp c
        col_normalized = col_normalized.replace('.', '')   # temp.c -> tempc
        
        # Handle degree symbols
        col_normalized = col_normalized.replace('°', '')   # °c -> c
        col_normalized = col_normalized.replace('deg', '')  # degc -> c
        
        # Clean up extra spaces
        col_normalized = ' '.join(col_normalized.split())
        
        # Try exact match first
        if col_normalized in mapping:
            column_mapping[col] = mapping[col_normalized]
            continue
            
        # Try without spaces
        col_no_spaces = col_normalized.replace(' ', '')
        if col_no_spaces in mapping:
            column_mapping[col] = mapping[col_no_spaces]
            continue
            
        # Try original lowercase without modifications
        col_original = col.lower().strip()
        if col_original in mapping:
            column_mapping[col] = mapping[col_original]
    
    return column_mapping