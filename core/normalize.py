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
import logging
from pathlib import Path
from io import StringIO
import csv
import codecs
import chardet
import json

logger = logging.getLogger(__name__)

# Import DataQualityError from core.errors
from core.errors import DataQualityError
from core.columns_map import normalize_column_names

# Import policy settings
from core.policy import should_fail_on_parser_warnings, is_safe_mode_enabled

# Parser configuration flags - now use policy defaults
FAIL_ON_PARSER_WARNINGS = should_fail_on_parser_warnings()  # Default: False (log only)
SAFE_MODE = is_safe_mode_enabled()  # Default: False (permissive)


class NormalizationError(Exception):
    """Raised when CSV normalization fails quality checks."""
    pass


class ParseWarning:
    """Container for parser warnings that can be elevated to errors."""
    
    def __init__(self, message: str, severity: str = 'warning', context: Optional[str] = None):
        self.message = message
        self.severity = severity  # 'warning', 'error', 'critical'
        self.context = context
        self.timestamp = datetime.now()
    
    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.message}" + (f" ({self.context})" if self.context else "")


class IndeterminateError(Exception):
    """Raised when parsing cannot determine data quality, requiring INDETERMINATE status."""
    
    def __init__(self, message: str, warnings: Optional[List[ParseWarning]] = None):
        super().__init__(message)
        self.warnings = warnings or []


class NormalizedTrace:
    """Container for normalized data with trace information."""
    
    def __init__(self, dataframe: pd.DataFrame, trace_info: Dict[str, Any]):
        self.dataframe = dataframe
        self.trace = trace_info
    
    def to_json(self) -> str:
        """Export trace information as JSON."""
        return json.dumps(self.trace, indent=2, default=str)
    
    def save_trace(self, filepath: str) -> None:
        """Save trace information to JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_json())


def detect_encoding(file_path: str) -> str:
    """Detect file encoding, handling BOM and common encodings."""
    # Try to detect BOM first
    with open(file_path, 'rb') as f:
        raw_data = f.read(4)  # Read first 4 bytes
    
    # Check for BOM markers
    if raw_data.startswith(b'\xff\xfe\x00\x00'):  # UTF-32 LE
        return 'utf-32-le'
    elif raw_data.startswith(b'\x00\x00\xfe\xff'):  # UTF-32 BE
        return 'utf-32-be'
    elif raw_data.startswith(b'\xff\xfe'):  # UTF-16 LE
        return 'utf-16-le'
    elif raw_data.startswith(b'\xfe\xff'):  # UTF-16 BE
        return 'utf-16-be'
    elif raw_data.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
        return 'utf-8-sig'
    
    # Use chardet for other encodings
    try:
        with open(file_path, 'rb') as f:
            sample = f.read(10000)  # Read first 10KB for detection
        
        detected = chardet.detect(sample)
        encoding = detected.get('encoding', 'utf-8').lower()
        
        # Map common Windows encodings
        encoding_map = {
            'windows-1252': 'cp1252',
            'iso-8859-1': 'latin1',
            'ascii': 'utf-8'  # ASCII is subset of UTF-8
        }
        
        return encoding_map.get(encoding, encoding)
    except Exception:
        return 'utf-8'  # Fallback


def detect_delimiter(file_path: str, encoding: str = 'utf-8') -> str:
    """Auto-detect CSV delimiter (, ; \t |) with enhanced locale support."""
    # Order matters - semicolon first for European CSVs
    delimiters = [';', ',', '\t', '|']
    
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            # Read first 10 lines for better detection
            sample_lines = []
            for i, line in enumerate(f):
                if not line.startswith('#') and line.strip():  # Skip comments and empty lines
                    sample_lines.append(line)
                    if len(sample_lines) >= 10:
                        break
        
        if not sample_lines:
            return ','  # Default fallback
        
        sample = '\n'.join(sample_lines)
        
        # Use csv.Sniffer to detect delimiter
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample, delimiters=delimiters)
            detected = dialect.delimiter
            
            # Validate detection by checking consistency across lines
            if len(sample_lines) > 1:
                first_count = sample_lines[0].count(detected)
                if first_count > 0:
                    # Check if delimiter count is consistent
                    consistent = True
                    for line in sample_lines[1:3]:  # Check next 2 lines
                        if line.count(detected) != first_count:
                            consistent = False
                            break
                    
                    if consistent:
                        return detected
            else:
                return detected
        
        except csv.Error:
            pass
        
        # Enhanced fallback: count occurrences with consistency check
        delimiter_scores = {}
        for delimiter in delimiters:
            counts = [line.count(delimiter) for line in sample_lines if line.count(delimiter) > 0]
            if counts:
                # Score based on total count and consistency
                total_count = sum(counts)
                consistency = 1.0 if len(set(counts)) == 1 else 0.5  # Bonus for consistent counts
                delimiter_scores[delimiter] = total_count * consistency
        
        if delimiter_scores:
            best_delimiter = max(delimiter_scores, key=delimiter_scores.get)
            # Additional validation for European format detection
            if best_delimiter == ';' and any(',' in line for line in sample_lines):
                # Likely European format with semicolon delimiter and decimal commas
                logger.info("Detected European CSV format (semicolon delimiter, likely decimal commas)")
            return best_delimiter
        
    except Exception as e:
        logger.warning(f"Delimiter detection failed: {e}")
    
    return ','  # Default fallback


def normalize_decimal_separators(text: str) -> str:
    """Normalize decimal separators from European format (1.234,56) to US format (1,234.56).
    
    Enhanced version with better detection and handling of mixed formats.
    """
    lines = text.split('\n')
    normalized_lines = []
    
    for line in lines:
        # Skip header lines and non-data lines
        if not line.strip() or line.startswith('#') or not any(c.isdigit() for c in line):
            normalized_lines.append(line)
            continue
        
        # Count commas and dots to determine likely format
        comma_count = line.count(',')
        dot_count = line.count('.')
        
        # Determine if this looks like European format
        is_european_format = False
        
        # Check for European pattern: numbers with dots as thousands and commas as decimals
        # Pattern: 1.234,56 or 12.345,67
        european_pattern = r'\b(\d{1,3}(?:\.\d{3})+),(\d{1,9})\b'
        if re.search(european_pattern, line):
            is_european_format = True
        
        # If we have both commas and dots, but no clear European pattern,
        # check if commas appear after dots (European style)
        elif comma_count > 0 and dot_count > 0:
            # Look for patterns like "12.345,67" vs "12,345.67"
            # In European format, the last punctuation should be comma
            numbers = re.findall(r'\d+[.,]\d+(?:[.,]\d+)*', line)
            for num in numbers:
                if ',' in num and '.' in num:
                    if num.rfind(',') > num.rfind('.'):
                        is_european_format = True
                        break
        
        # Apply appropriate conversion
        if is_european_format:
            # European format: dots as thousands, commas as decimals
            # First handle complex European numbers (1.234.567,89) -> remove dots, replace comma with dot
            line = re.sub(r'\b(\d{1,3})(?:\.\d{3})+,(\d{1,9})\b', 
                         lambda m: m.group(0).replace('.', '').replace(',', '.'), line)
            # Then handle simple cases in European context (234,56 -> 234.56)
            line = re.sub(r'\b(\d+),(\d{1,9})\b', r'\1.\2', line)
        elif comma_count > 0 and dot_count == 0:
            # Only commas present, likely decimal separators
            line = re.sub(r'\b(\d+),(\d{1,9})\b', r'\1.\2', line)
        
        # Additional safety check: don't convert commas that are clearly field separators
        # This is a heuristic - if there are many commas and they separate non-numeric values,
        # they're probably field separators
        fields = line.split(',')
        if len(fields) > 3:  # More than 3 fields suggests comma is delimiter
            non_numeric_fields = sum(1 for field in fields if not re.match(r'^\s*\d+\.?\d*\s*$', field.strip()))
            if non_numeric_fields > 1:
                # Likely field separators, revert any changes
                normalized_lines.append(text.split('\n')[len(normalized_lines)])
                continue
        
        normalized_lines.append(line)
    
    return '\n'.join(normalized_lines)


def convert_excel_serial_dates(df: pd.DataFrame, timestamp_col: str) -> pd.Series:
    """Convert Excel serial dates to datetime objects with enhanced detection."""
    try:
        if not pd.api.types.is_numeric_dtype(df[timestamp_col]):
            return df[timestamp_col]
        
        sample_values = df[timestamp_col].dropna().head(10)
        if len(sample_values) == 0:
            return df[timestamp_col]
        
        # Enhanced Excel serial date detection
        # Excel dates since 1900: typically 25000+ (around 1968)
        # Excel dates for recent years: 40000+ (around 2009)
        # Upper bound: 100000 (around 2173)
        
        # Check if values are in typical Excel serial date range
        min_val = sample_values.min()
        max_val = sample_values.max()
        mean_val = sample_values.mean()
        
        is_excel_serial = False
        
        # Primary check: values in reasonable Excel date range
        if (min_val >= 25000 and max_val <= 100000 and 
            all(isinstance(val, (int, float)) and not pd.isna(val) for val in sample_values)):
            
            # Additional validation: check if differences make sense as days
            if len(sample_values) > 1:
                diffs = sample_values.diff().dropna()
                if len(diffs) > 0:
                    # Typical logging intervals: seconds to days
                    # For Excel serial dates, expect small fractional differences for sub-day intervals
                    # or integer differences for daily intervals
                    max_diff = diffs.max()
                    min_diff = diffs.min()
                    
                    # If differences are very small (< 1 day) or reasonable daily intervals
                    if (max_diff < 30 and min_diff >= 0) or (0.0001 < max_diff < 1):  # Sub-day or monthly max
                        is_excel_serial = True
            else:
                # Single value check - if in range, assume Excel
                is_excel_serial = True
        
        if is_excel_serial:
            logger.info(f"Detected Excel serial dates in column {timestamp_col} (range: {min_val:.1f} - {max_val:.1f})")
            
            # Convert Excel serial dates to datetime
            # Excel uses 1900-01-01 as day 1, but has leap year bug (treats 1900 as leap year)
            # pd.to_datetime with origin='1899-12-30' handles this correctly
            try:
                converted = pd.to_datetime(df[timestamp_col], origin='1899-12-30', unit='D', utc=True)
                
                # Sanity check: ensure converted dates are reasonable (1970-2100)
                sample_converted = converted.dropna().head(5)
                if len(sample_converted) > 0:
                    min_year = sample_converted.min().year
                    max_year = sample_converted.max().year
                    if 1970 <= min_year <= 2100 and 1970 <= max_year <= 2100:
                        return converted
                    else:
                        logger.warning(f"Excel conversion resulted in unreasonable dates: {min_year}-{max_year}")
                        
            except Exception as conv_error:
                logger.warning(f"Excel serial date conversion failed: {conv_error}")
    
    except Exception as e:
        logger.warning(f"Excel serial date detection failed: {e}")
    
    # Return original if conversion fails or detection is negative
    return df[timestamp_col]


def load_csv_with_metadata(csv_path: str, safe_mode: bool = None) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Load CSV file with robust parsing and extract metadata from comment lines.
    
    Features:
    - Auto-detects encoding (including BOM handling)
    - Auto-detects delimiter (, ; \t |)
    - Handles decimal comma formats (European)
    - Converts Excel serial dates
    - Extracts metadata from # comment lines
    - Parser warning handling with safe mode
    
    Args:
        csv_path: Path to the CSV file
        safe_mode: Enable conservative parsing (default: use global SAFE_MODE)
        
    Returns:
        Tuple of (DataFrame, metadata_dict)
        
    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV format is invalid
        IndeterminateError: If safe mode enabled and parser warnings detected
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    if safe_mode is None:
        safe_mode = is_safe_mode_enabled()
    
    parse_warnings = []
    
    # Detect encoding and delimiter
    encoding = detect_encoding(str(csv_path))
    delimiter = detect_delimiter(str(csv_path), encoding)
    
    logger.debug(f"Detected encoding: {encoding}, delimiter: {repr(delimiter)}")
    
    metadata = {}
    data_lines = []
    
    # Read file line by line to extract metadata and data
    try:
        with open(csv_path, 'r', encoding=encoding) as f:
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
    except UnicodeDecodeError as e:
        logger.warning(f"Encoding {encoding} failed, trying latin1 fallback: {e}")
        parse_warnings.append(ParseWarning(
            f"Primary encoding {encoding} failed, using latin1 fallback",
            severity='warning',
            context='encoding_fallback'
        ))
        
        # Fallback to latin1 which can read any byte sequence
        with open(csv_path, 'r', encoding='latin1') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
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
    
    # Normalize decimal separators before parsing
    csv_content = '\n'.join(data_lines)
    csv_content = normalize_decimal_separators(csv_content)
    
    # Parse CSV data with detected delimiter
    try:
        df = pd.read_csv(StringIO(csv_content), delimiter=delimiter)
    except Exception as e:
        # Fallback: try with default comma delimiter
        logger.warning(f"Failed with delimiter {repr(delimiter)}, trying comma: {e}")
        parse_warnings.append(ParseWarning(
            f"Delimiter {repr(delimiter)} failed, using comma fallback",
            severity='warning',
            context='delimiter_fallback'
        ))
        
        try:
            df = pd.read_csv(StringIO(csv_content), delimiter=',')
        except Exception as e2:
            parse_warnings.append(ParseWarning(
                f"CSV parsing failed with multiple delimiters",
                severity='critical',
                context='parse_failure'
            ))
            raise ValueError(f"Failed to parse CSV data with multiple delimiters: {e}, {e2}")
    
    if df.empty:
        raise ValueError("CSV file contains no data rows")
    
    # Apply column name mapping for common variations
    column_mapping = normalize_column_names(df.columns.tolist())
    if column_mapping:
        logger.debug(f"Applying column mapping: {column_mapping}")
        df = df.rename(columns=column_mapping)
        metadata['_column_mapping'] = column_mapping
    
    # Check for parser warnings and handle according to mode
    if parse_warnings and (should_fail_on_parser_warnings() or safe_mode):
        critical_warnings = [w for w in parse_warnings if w.severity == 'critical']
        warning_warnings = [w for w in parse_warnings if w.severity == 'warning']
        
        if critical_warnings or (safe_mode and warning_warnings):
            warning_messages = [str(w) for w in parse_warnings]
            if safe_mode:
                raise IndeterminateError(
                    f"Parser warnings detected in safe mode: {'; '.join(warning_messages)}",
                    warnings=parse_warnings
                )
            else:
                raise ValueError(f"Parser errors detected: {'; '.join([str(w) for w in critical_warnings])}")
    
    # Store parsing information in metadata
    metadata['_parsing_info'] = {
        'detected_encoding': encoding,
        'detected_delimiter': delimiter,
        'decimal_normalized': True,
        'original_columns': list(df.columns),
        'original_shape': df.shape,
        'parser_warnings': [str(w) for w in parse_warnings] if parse_warnings else []
    }
    
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
    # Detect if it's Unix timestamp first
    if pd.api.types.is_numeric_dtype(df[timestamp_col]):
        sample_values = df[timestamp_col].dropna().head(5)
        if len(sample_values) > 0:
            sample_numeric = sample_values.astype(float)
            # Check if values are in Unix timestamp range (1970-2100)
            if (sample_numeric >= 0).all() and (sample_numeric <= 4102444800).all():
                try:
                    return pd.to_datetime(df[timestamp_col], unit='s', utc=True)
                except Exception as e:
                    logger.warning(f"Failed to parse as Unix timestamps: {e}")
    
    # Try Excel serial date conversion first
    excel_timestamps = convert_excel_serial_dates(df, timestamp_col)
    if not excel_timestamps.equals(df[timestamp_col]):
        # Excel conversion succeeded
        return excel_timestamps
    
    try:
        # Try pandas automatic parsing for ISO/string timestamps
        timestamps = pd.to_datetime(df[timestamp_col], utc=True)
        
        # Handle timezone conversion for mixed timezone cases
        if timestamps.dt.tz is None:
            if source_tz:
                # Apply specified timezone then convert to UTC
                try:
                    tz = pytz.timezone(source_tz)
                    timestamps = timestamps.dt.tz_localize(tz).dt.tz_convert('UTC')
                except Exception as e:
                    logger.warning(f"Failed to apply timezone {source_tz}: {e}, assuming UTC")
                    timestamps = timestamps.dt.tz_localize('UTC')
            else:
                # Assume UTC if no timezone info
                timestamps = timestamps.dt.tz_localize('UTC')
        else:
            # Convert to UTC if in different timezone
            timestamps = timestamps.dt.tz_convert('UTC')
            
    except Exception as e:
        # Fallback: try Unix timestamp as last resort
        try:
            timestamps = pd.to_datetime(df[timestamp_col], unit='s', utc=True)
        except Exception as e2:
            raise ValueError(f"Unable to parse timestamps in column '{timestamp_col}': ISO parsing failed ({e}), Unix parsing failed ({e2})")
    
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
        
        # More comprehensive Fahrenheit detection
        fahrenheit_indicators = [
            'f', 'fahrenheit', '°f', 'degf', '_f', 'temp_f', 'temperature_f'
        ]
        
        # Check if column appears to be in Fahrenheit
        is_fahrenheit = any(indicator in col_lower for indicator in fahrenheit_indicators)
        
        # Also check by value range - if mean > 80 and max > 200, likely Fahrenheit
        if not is_fahrenheit:
            col_values = df[col].dropna()
            if len(col_values) > 5:
                mean_val = col_values.mean()
                max_val = col_values.max()
                min_val = col_values.min()
                
                # Heuristic: if mean > 80 and max > 200, likely Fahrenheit for cure processes
                # Also if min > 32 (freezing point) and mean > 100, likely F
                if ((mean_val > 80 and max_val > 200) or 
                    (min_val > 32 and mean_val > 100 and max_val > 300)):
                    is_fahrenheit = True
        
        if is_fahrenheit:
            # Convert F to C: (F - 32) * 5/9
            df[col] = (df[col] - 32) * 5 / 9
            
            # Rename column to indicate Celsius (more robust)
            new_name = col
            for pattern, replacement in [
                (r'[_\s]*[°]?f([_\s]|$)', r'_C\1'),
                (r'fahrenheit', 'celsius'),
                (r'degf', 'degc'),
            ]:
                new_name = re.sub(pattern, replacement, new_name, flags=re.IGNORECASE)
            
            if new_name != col and new_name not in df.columns:
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
        issues.append(f"Data gaps too large: {gap_count} gaps > {allowed_gaps_s:.1f}s (max: {max_gap:.1f}s)")
    
    # Check for duplicate timestamps
    duplicates = df[timestamp_col].duplicated().sum()
    if duplicates > 0:
        issues.append(f"Duplicate timestamps detected: {duplicates} occurrences")
    
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
    
    # Calculate current sampling interval to determine if resampling is needed
    if len(df) >= 2:
        # Calculate median interval to handle irregular sampling
        time_diffs = df[timestamp_col].diff().dt.total_seconds().dropna()
        if len(time_diffs) > 0:
            current_interval_s = time_diffs.median()
            
            # If current interval is less than or equal to target, preserve original data
            # This prevents downsampling good data
            if current_interval_s <= target_step_s:
                logger.debug(f"Current interval ({current_interval_s}s) ≤ target ({target_step_s}s), preserving original data")
                return df
            
            # If current interval matches target closely, preserve original cadence
            if abs(current_interval_s - target_step_s) / target_step_s < 0.15:  # Within 15%
                logger.debug(f"Current interval ({current_interval_s}s) matches target ({target_step_s}s), preserving original cadence")
                return df
            
            # If target is much smaller than current, only resample if we have sufficient data density
            if target_step_s < current_interval_s * 0.5:
                logger.warning(f"Target step ({target_step_s}s) much smaller than data interval ({current_interval_s}s), keeping original resolution")
                return df
    
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


def normalize_csv_data(csv_path: Union[str, Path], spec: Any, **kwargs) -> pd.DataFrame:
    """
    Legacy wrapper for CSV data normalization with spec.
    
    Args:
        csv_path: Path to CSV file
        spec: Specification object with normalization parameters
        **kwargs: Additional normalization parameters
        
    Returns:
        Normalized DataFrame
        
    Raises:
        NormalizationError: If normalization fails
    """
    # Load CSV file
    df, metadata = load_csv_with_metadata(str(csv_path))
    
    # Extract parameters from spec if available
    target_step_s = getattr(spec, 'sampling_period_s', kwargs.get('target_step_s', 30.0))
    allowed_gaps_s = kwargs.get('allowed_gaps_s', 60.0)
    max_sample_period_s = kwargs.get('max_sample_period_s', 300.0)
    industry = getattr(spec, 'industry', kwargs.get('industry', None))
    
    return normalize_temperature_data(
        df,
        target_step_s=target_step_s,
        allowed_gaps_s=allowed_gaps_s,
        max_sample_period_s=max_sample_period_s,
        industry=industry,
        **kwargs
    )


def normalize_dataframe(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Legacy wrapper for DataFrame normalization.
    
    Args:
        df: Input DataFrame
        **kwargs: Normalization parameters
        
    Returns:
        Normalized DataFrame
        
    Raises:
        NormalizationError: If normalization fails
    """
    return normalize_temperature_data(df, **kwargs)


def normalize_temperature_data(df: pd.DataFrame, 
                             target_step_s: float = 30.0,
                             allowed_gaps_s: float = 60.0,
                             max_sample_period_s: float = 300.0,
                             source_timezone: Optional[str] = None,
                             tz_resolver: Optional[Callable[[str], str]] = None,
                             unit_resolver: Optional[Callable[[str], str]] = None,
                             industry: Optional[str] = None,
                             return_trace: bool = False) -> Union[pd.DataFrame, NormalizedTrace]:
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
        industry: Industry type for industry-specific validation (default: None)
        return_trace: If True, return NormalizedTrace with processing info (default: False)
        
    Returns:
        Normalized DataFrame or NormalizedTrace if return_trace=True
        
    Raises:
        NormalizationError: If data quality checks fail
        DataQualityError: If industry-specific data quality issues are found
    """
    if df.empty:
        raise NormalizationError("Input DataFrame is empty")
    
    # Initialize trace information
    trace = {
        'original_shape': df.shape,
        'original_columns': list(df.columns),
        'processing_steps': [],
        'parameters': {
            'target_step_s': target_step_s,
            'allowed_gaps_s': allowed_gaps_s,
            'max_sample_period_s': max_sample_period_s,
            'source_timezone': source_timezone,
            'industry': industry
        },
        'quality_checks': [],
        'conversions': []
    }
    
    # Detect timestamp column
    timestamp_col = detect_timestamp_column(df)
    trace['processing_steps'].append(f'Detected timestamp column: {timestamp_col}')
    
    # Parse and normalize timestamps to UTC
    resolved_timezone = source_timezone
    if tz_resolver and source_timezone:
        resolved_timezone = tz_resolver(source_timezone)
        trace['conversions'].append(f'Resolved timezone: {source_timezone} -> {resolved_timezone}')
    
    utc_timestamps = parse_timestamps(df, timestamp_col, resolved_timezone)
    df = df.copy()
    df[timestamp_col] = utc_timestamps
    trace['processing_steps'].append(f'Converted timestamps to UTC (source_tz: {resolved_timezone})')
    
    # Sort by timestamp and remove duplicates
    df = df.sort_values(timestamp_col).reset_index(drop=True)
    
    # Check for duplicate timestamps before removal
    initial_len = len(df)
    duplicate_count = df[timestamp_col].duplicated().sum()
    
    # Industry-specific handling for duplicate timestamps
    if duplicate_count > 0 and industry == "powder":
        raise DataQualityError(
            "Duplicate timestamps not allowed",
            quality_issues=[f"Found {duplicate_count} duplicate timestamps"]
        )
    
    # Only remove true identical timestamps, not near-duplicates
    # Calculate time differences to identify true duplicates (≤0.1s difference)
    df_sorted = df.sort_values(timestamp_col).reset_index(drop=True)
    time_diffs = df_sorted[timestamp_col].diff().dt.total_seconds().fillna(float('inf'))
    
    # Keep rows where time difference > 0.1s (not true duplicates)
    duplicate_mask = time_diffs <= 0.1
    true_duplicates = duplicate_mask.sum()
    
    if true_duplicates > 0:
        if industry == "powder":
            raise DataQualityError(
                "Duplicate timestamps not allowed",
                quality_issues=[f"Found {true_duplicates} true duplicate timestamps (≤0.1s apart)"]
            )
        # Remove only true duplicates (≤0.1s apart)
        df = df_sorted[~duplicate_mask].reset_index(drop=True)
        logger.warning(f"Removed {true_duplicates} true duplicate timestamp rows during normalization")
    else:
        df = df_sorted
    
    # Detect and convert temperature columns
    temp_columns = detect_temperature_columns(df)
    if not temp_columns:
        raise NormalizationError("No temperature columns detected in CSV data")
    
    trace['processing_steps'].append(f'Detected temperature columns: {temp_columns}')
    
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
    
    # Track conversions before applying them
    original_temp_stats = {}
    for col in temp_columns:
        original_temp_stats[col] = {
            'mean': df[col].mean(),
            'min': df[col].min(),
            'max': df[col].max()
        }
    
    df = _convert_fahrenheit_to_celsius_df(df, temp_columns)
    
    # Record which columns were converted
    for col in temp_columns:
        new_stats = {
            'mean': df[col].mean() if col in df.columns else None,
            'min': df[col].min() if col in df.columns else None,
            'max': df[col].max() if col in df.columns else None
        }
        # Check if values changed significantly (indicating F->C conversion)
        if col in original_temp_stats and new_stats['mean'] is not None:
            original_mean = original_temp_stats[col]['mean']
            if abs(original_mean - new_stats['mean']) > 10:  # Significant change
                trace['conversions'].append(f'Converted {col} from Fahrenheit to Celsius')
    
    trace['processing_steps'].append('Applied temperature unit conversions')
    
    # Check data quality - but be more lenient for industry-specific data
    quality_issues = check_data_quality(df, timestamp_col, max_sample_period_s, allowed_gaps_s)
    trace['quality_checks'] = quality_issues.copy()
    
    # Filter out certain quality issues for concrete industry that are acceptable
    if industry == "concrete":
        # Concrete monitoring often has longer intervals (5-15 minutes), which is acceptable
        filtered_issues = []
        for issue in quality_issues:
            if "gaps too large" in issue.lower() and "300.0s" in issue:
                # 5-minute gaps are acceptable for concrete curing monitoring
                logger.info(f"Concrete industry: ignoring acceptable gap issue: {issue}")
                continue
            filtered_issues.append(issue)
        quality_issues = filtered_issues
    
    if quality_issues:
        trace['processing_steps'].append(f'Data quality issues found: {len(quality_issues)}')
        error_msg = "Data quality checks failed:\n" + "\n".join(f"- {issue}" for issue in quality_issues)
        raise NormalizationError(error_msg)
    
    trace['processing_steps'].append('Data quality checks passed')
    
    # Resample to target step
    pre_resample_count = len(df)
    normalized_df = resample_temperature_data(df, timestamp_col, target_step_s)
    post_resample_count = len(normalized_df)
    
    trace['processing_steps'].append(f'Resampled data: {pre_resample_count} -> {post_resample_count} samples')
    trace['final_shape'] = normalized_df.shape
    trace['final_columns'] = list(normalized_df.columns)
    
    if return_trace:
        return NormalizedTrace(normalized_df, trace)
    
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