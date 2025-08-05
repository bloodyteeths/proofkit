"""
ProofKit CSV Normalizer

Loads and normalizes CSV temperature data for powder-coat cure validation.
Handles metadata extraction, timezone conversion, temperature unit conversion,
resampling, and data quality validation according to M1 requirements.

Example usage:
    from core.normalize import load_csv_with_metadata, normalize_temperature_data
    
    # Load CSV with metadata extraction
    df, metadata = load_csv_with_metadata("temp_data.csv")
    
    # Normalize the data
    normalized_df = normalize_temperature_data(
        df, target_step_s=30.0, allowed_gaps_s=60.0
    )
    print(f"Normalized {len(normalized_df)} samples")
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List, Any, Union, Callable
from datetime import datetime, timezone
import pytz
import re
import warnings
from pathlib import Path
from io import StringIO


class NormalizationError(Exception):
    """Raised when CSV normalization fails quality checks."""
    pass


def load_csv_with_metadata(csv_path: str) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Load CSV file and extract metadata from comment lines.
    
    Metadata is extracted from lines starting with '#' in the format:
    # key: value
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        Tuple of (DataFrame, metadata_dict)
        
    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV format is invalid
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    metadata = {}
    data_lines = []
    
    # Read file line by line to extract metadata and data
    with open(csv_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # Extract metadata from comment lines
            if line.startswith('#'):
                match = re.match(r'#\s*([^:]+):\s*(.+)', line)
                if match:
                    key = match.group(1).strip()
                    value = match.group(2).strip()
                    metadata[key] = value
            else:
                data_lines.append(line)
    
    if not data_lines:
        raise ValueError("No data lines found in CSV file")
    
    # Parse CSV data
    csv_content = '\n'.join(data_lines)
    try:
        df = pd.read_csv(StringIO(csv_content))
    except Exception as e:
        raise ValueError(f"Failed to parse CSV data: {e}")
    
    if df.empty:
        raise ValueError("CSV file contains no data rows")
    
    return df, metadata


def detect_timestamp_format(df: pd.DataFrame) -> Tuple[str, str]:
    """
    Detect timestamp format and column in the DataFrame.
    
    Args:
        df: Input DataFrame
        
    Returns:
        Tuple of (format_type, column_name) where format_type is 'iso' or 'unix'
        
    Raises:
        ValueError: If no timestamp column is found
    """
    # Try to find timestamp column
    timestamp_col = detect_timestamp_column(df)
    
    # Sample first few values to determine format
    sample_values = df[timestamp_col].dropna().head(5)
    
    # Check if it's Unix timestamp (numeric)
    if pd.api.types.is_numeric_dtype(df[timestamp_col]):
        # Check if values are in Unix timestamp range (roughly 1970-2100)
        sample_numeric = sample_values.astype(float)
        if (sample_numeric >= 0).all() and (sample_numeric <= 4102444800).all():  # Unix timestamp range
            return "unix", timestamp_col
    
    # Try to parse as ISO datetime
    try:
        pd.to_datetime(sample_values)
        return "iso", timestamp_col
    except:
        pass
    
    # Default to ISO if we can't determine
    return "iso", timestamp_col


def detect_timestamp_column(df: pd.DataFrame) -> str:
    """
    Detect the timestamp column in the DataFrame.
    
    Args:
        df: Input DataFrame
        
    Returns:
        Name of the timestamp column
        
    Raises:
        ValueError: If no timestamp column is found
    """
    # Common timestamp column names
    timestamp_candidates = [
        'timestamp', 'time', 'datetime', 'date_time', 
        'ts', 't', 'sample_time', 'time_stamp'
    ]
    
    # Check for exact matches first
    for col in df.columns:
        if col.lower() in timestamp_candidates:
            return col
    
    # Check for columns containing timestamp-like patterns
    for col in df.columns:
        if any(candidate in col.lower() for candidate in timestamp_candidates):
            return col
    
    # If no obvious timestamp column, check first column
    first_col = df.columns[0]
    sample_values = df[first_col].dropna().head(5)
    
    # Try to parse first column as timestamps
    try:
        pd.to_datetime(sample_values)
        return first_col
    except:
        pass
    
    raise ValueError("No timestamp column found in CSV data")


def parse_timestamps(df: pd.DataFrame, timestamp_col: str, 
                    source_tz: Optional[str] = None) -> pd.Series:
    """
    Parse timestamp column and convert to UTC.
    
    Args:
        df: Input DataFrame
        timestamp_col: Name of timestamp column
        source_tz: Source timezone (if None, attempts auto-detection)
        
    Returns:
        Series of UTC timestamps
        
    Raises:
        ValueError: If timestamps cannot be parsed
    """
    try:
        # First attempt: pandas automatic parsing
        timestamps = pd.to_datetime(df[timestamp_col])
        
        # Handle timezone conversion
        if timestamps.dt.tz is None:
            if source_tz:
                # Apply specified timezone then convert to UTC
                tz = pytz.timezone(source_tz)
                timestamps = timestamps.dt.tz_localize(tz).dt.tz_convert('UTC')
            else:
                # Assume UTC if no timezone info
                timestamps = timestamps.dt.tz_localize('UTC')
        else:
            # Convert to UTC if in different timezone
            timestamps = timestamps.dt.tz_convert('UTC')
            
    except Exception as e:
        # Fallback: try Unix timestamp
        try:
            timestamps = pd.to_datetime(df[timestamp_col], unit='s', utc=True)
        except:
            raise ValueError(f"Unable to parse timestamps in column '{timestamp_col}': {e}")
    
    return timestamps


def detect_temperature_columns(df: pd.DataFrame) -> List[str]:
    """
    Detect temperature columns by name patterns.
    
    Args:
        df: Input DataFrame
        
    Returns:
        List of temperature column names
    """
    temp_patterns = [
        r'.*temp.*', r'.*temperature.*', r'.*pmt.*', r'.*sensor.*',
        r'.*°[cf].*', r'.*deg[cf].*', r'.*_c$', r'.*_f$'
    ]
    
    temp_columns = []
    
    for col in df.columns:
        col_lower = col.lower()
        if any(re.match(pattern, col_lower) for pattern in temp_patterns):
            # Verify it's numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                temp_columns.append(col)
    
    return temp_columns


def convert_fahrenheit_to_celsius(temps: Union[pd.Series, pd.DataFrame, float, List[str]]) -> Union[pd.Series, pd.DataFrame, float]:
    """
    Convert Fahrenheit temperature values to Celsius.
    
    Args:
        temps: Temperature values - can be Series, DataFrame with temp columns, or scalar
        
    Returns:
        Temperature values converted to Celsius
    """
    if isinstance(temps, pd.Series):
        # Convert Series F to C: (F - 32) * 5/9
        return (temps - 32) * 5 / 9
    elif isinstance(temps, (float, int)):
        # Convert scalar F to C
        return (temps - 32) * 5 / 9
    elif isinstance(temps, pd.DataFrame):
        # For backward compatibility - detect temp columns and convert
        temp_columns = detect_temperature_columns(temps)
        return _convert_fahrenheit_to_celsius_df(temps, temp_columns)
    else:
        raise ValueError(f"Unsupported type for temperature conversion: {type(temps)}")


def _convert_fahrenheit_to_celsius_df(df: pd.DataFrame, temp_columns: List[str]) -> pd.DataFrame:
    """
    Convert Fahrenheit temperature columns to Celsius.
    
    Args:
        df: Input DataFrame
        temp_columns: List of temperature column names
        
    Returns:
        DataFrame with temperatures converted to Celsius
    """
    df = df.copy()
    
    for col in temp_columns:
        col_lower = col.lower()
        # Check if column appears to be in Fahrenheit
        if any(indicator in col_lower for indicator in ['f', 'fahrenheit', '°f', 'degf']):
            # Convert F to C: (F - 32) * 5/9
            df[col] = (df[col] - 32) * 5 / 9
            
            # Rename column to indicate Celsius
            new_name = re.sub(r'[_\s]*[°]?f([_\s]|$)', r'_C\1', col, flags=re.IGNORECASE)
            if new_name != col:
                df = df.rename(columns={col: new_name})
    
    return df


def validate_data_quality(df: pd.DataFrame, timestamp_col: str,
                      max_sample_period_s: float, allowed_gaps_s: float) -> List[str]:
    """
    Validate data quality and return list of issues found.
    
    This is an alias for check_data_quality for backward compatibility.
    
    Args:
        df: Input DataFrame with timestamps
        timestamp_col: Name of timestamp column
        max_sample_period_s: Maximum allowed sampling period
        allowed_gaps_s: Maximum allowed gap duration
        
    Returns:
        List of quality issue descriptions
    """
    return check_data_quality(df, timestamp_col, max_sample_period_s, allowed_gaps_s)


def check_data_quality(df: pd.DataFrame, timestamp_col: str,
                      max_sample_period_s: float, allowed_gaps_s: float) -> List[str]:
    """
    Check data quality and return list of issues found.
    
    Args:
        df: Input DataFrame with timestamps
        timestamp_col: Name of timestamp column
        max_sample_period_s: Maximum allowed sampling period
        allowed_gaps_s: Maximum allowed gap duration
        
    Returns:
        List of quality issue descriptions
    """
    issues = []
    
    if len(df) < 2:
        issues.append("Insufficient data: need at least 2 samples")
        return issues
    
    # Calculate time differences
    time_diffs = df[timestamp_col].diff().dt.total_seconds()
    time_diffs = time_diffs.dropna()
    
    if len(time_diffs) == 0:
        issues.append("Unable to calculate sampling intervals")
        return issues
    
    # Check for negative time differences (non-monotonic)
    negative_diffs = time_diffs[time_diffs <= 0]
    if len(negative_diffs) > 0:
        issues.append(f"Non-monotonic timestamps detected: {len(negative_diffs)} occurrences")
    
    # Check maximum sampling period
    max_interval = time_diffs.max()
    if max_interval > max_sample_period_s:
        issues.append(f"Sampling period too large: {max_interval:.1f}s > {max_sample_period_s}s")
    
    # Check for data gaps exceeding allowed threshold
    large_gaps = time_diffs[time_diffs > allowed_gaps_s]
    if len(large_gaps) > 0:
        gap_count = len(large_gaps)
        max_gap = large_gaps.max()
        issues.append(f"Data gaps too large: {gap_count} gaps > {allowed_gaps_s}s (max: {max_gap:.1f}s)")
    
    # Check for duplicate timestamps
    duplicates = df[timestamp_col].duplicated().sum()
    if duplicates > 0:
        issues.append(f"Duplicate timestamps: {duplicates} occurrences")
    
    return issues


def resample_temperature_data(df: pd.DataFrame, timestamp_col: str,
                            target_step_s: float = 30.0) -> pd.DataFrame:
    """
    Resample temperature data to fixed time step.
    
    Args:
        df: Input DataFrame with timestamps
        timestamp_col: Name of timestamp column
        target_step_s: Target sampling period in seconds
        
    Returns:
        Resampled DataFrame
    """
    df = df.copy()
    df = df.set_index(timestamp_col)
    
    # Create regular time index
    start_time = df.index.min()
    end_time = df.index.max()
    freq = f'{int(target_step_s)}s'
    
    # Resample using forward fill for short gaps, interpolation for longer ones
    resampled = df.resample(freq).mean()
    
    # Forward fill small gaps (up to 2 target steps)
    max_fill_limit = 2
    resampled = resampled.ffill(limit=max_fill_limit)
    
    # Interpolate remaining NaN values
    resampled = resampled.interpolate(method='time', limit_direction='both')
    
    # Reset index to make timestamp a column again
    resampled = resampled.reset_index()
    
    return resampled


def normalize_temperature_data(df: pd.DataFrame, 
                             target_step_s: float = 30.0,
                             allowed_gaps_s: float = 60.0,
                             max_sample_period_s: float = 300.0,
                             source_timezone: Optional[str] = None,
                             tz_resolver: Optional[Callable[[str], str]] = None,
                             unit_resolver: Optional[Callable[[str], str]] = None) -> pd.DataFrame:
    """
    Normalize temperature data according to ProofKit requirements.
    
    Performs the following operations:
    1. Detect and parse timestamp column
    2. Convert timezone to UTC
    3. Detect temperature columns and convert °F to °C
    4. Check data quality
    5. Resample to fixed time step
    
    Args:
        df: Input DataFrame
        target_step_s: Target resampling period in seconds
        allowed_gaps_s: Maximum allowed gap duration
        max_sample_period_s: Maximum allowed sampling period
        source_timezone: Source timezone (if None, auto-detect)
        tz_resolver: Optional callable to resolve timezone names (default: None)
        unit_resolver: Optional callable to resolve temperature units (default: None)
        
    Returns:
        Normalized DataFrame
        
    Raises:
        NormalizationError: If data quality checks fail
    """
    if df.empty:
        raise NormalizationError("Input DataFrame is empty")
    
    # Detect timestamp column
    timestamp_col = detect_timestamp_column(df)
    
    # Parse and normalize timestamps to UTC
    resolved_timezone = source_timezone
    if tz_resolver and source_timezone:
        resolved_timezone = tz_resolver(source_timezone)
    utc_timestamps = parse_timestamps(df, timestamp_col, resolved_timezone)
    df = df.copy()
    df[timestamp_col] = utc_timestamps
    
    # Sort by timestamp
    df = df.sort_values(timestamp_col).reset_index(drop=True)
    
    # Detect and convert temperature columns
    temp_columns = detect_temperature_columns(df)
    if not temp_columns:
        raise NormalizationError("No temperature columns detected in CSV data")
    
    # Apply unit resolver if provided
    if unit_resolver:
        resolved_temp_columns = []
        for col in temp_columns:
            resolved_unit = unit_resolver(col)
            if resolved_unit.lower() in ['f', 'fahrenheit']:
                resolved_temp_columns.append(col)
            # Add to list regardless for processing
            resolved_temp_columns.append(col)
        # Remove duplicates while preserving order
        temp_columns = list(dict.fromkeys(resolved_temp_columns))
    
    df = _convert_fahrenheit_to_celsius_df(df, temp_columns)
    
    # Check data quality
    quality_issues = check_data_quality(df, timestamp_col, max_sample_period_s, allowed_gaps_s)
    if quality_issues:
        error_msg = "Data quality checks failed:\n" + "\n".join(f"- {issue}" for issue in quality_issues)
        raise NormalizationError(error_msg)
    
    # Resample to target step
    normalized_df = resample_temperature_data(df, timestamp_col, target_step_s)
    
    return normalized_df


# Usage example in comments:
"""
Example usage for ProofKit CSV normalization:

from core.normalize import load_csv_with_metadata, normalize_temperature_data
from pathlib import Path

# Load CSV with metadata
csv_file = Path("examples/cure_data.csv")
df, metadata = load_csv_with_metadata(csv_file)
print(f"Loaded {len(df)} samples with metadata: {metadata}")

# Normalize data according to spec requirements
normalized_df = normalize_temperature_data(
    df, 
    target_step_s=30.0,      # 30-second intervals
    allowed_gaps_s=60.0,     # Max 60s gaps allowed
    source_timezone="US/Eastern"  # Source timezone
)

print(f"Normalized to {len(normalized_df)} samples at 30s intervals")
"""