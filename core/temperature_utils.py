"""
Temperature column detection utilities for ProofKit.

Shared utilities for detecting and processing temperature columns
in normalized CSV data.
"""

import pandas as pd
from typing import List
import logging

logger = logging.getLogger(__name__)


def detect_temperature_columns(df: pd.DataFrame) -> List[str]:
    """
    Detect temperature columns in the DataFrame.
    
    Looks for columns containing temperature-related keywords
    or patterns in their names.
    
    Args:
        df: Input DataFrame
        
    Returns:
        List of column names identified as temperature columns
    """
    temp_keywords = [
        'temp', 'temperature', 'celsius', 'fahrenheit',
        'c°', 'f°', '°c', '°f', 'deg', 'thermal'
    ]
    
    temp_columns = []
    for col in df.columns:
        col_lower = col.lower()
        # Skip timestamp columns
        if 'time' in col_lower or 'date' in col_lower:
            continue
        # Check for temperature keywords
        if any(keyword in col_lower for keyword in temp_keywords):
            temp_columns.append(col)
        # Check if column contains numeric data that could be temperature
        elif df[col].dtype in ['float64', 'int64']:
            # Check if values are in typical temperature ranges
            col_values = df[col].dropna()
            if len(col_values) > 0:
                mean_val = col_values.mean()
                # Common temperature ranges in C or F
                if -50 <= mean_val <= 500:  # Wide range for various applications
                    # Could be temperature, add if no other columns found
                    if not temp_columns:
                        temp_columns.append(col)
    
    return temp_columns


class DecisionError(Exception):
    """Custom exception for decision algorithm errors."""
    pass