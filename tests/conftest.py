"""
ProofKit Test Configuration and Shared Fixtures

Provides pytest fixtures for temporary directories, example data paths,
and common test utilities used across the ProofKit test suite.

Example usage:
    def test_normalize_example(example_csv_path, temp_dir):
        # Use example data and temp directory
        pass
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any
import json
import pandas as pd
from datetime import datetime, timezone

from core.models import SpecV1


@pytest.fixture
def temp_dir():
    """
    Provide a temporary directory that is cleaned up after test.
    
    Returns:
        Path: Temporary directory path
    """
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def examples_dir():
    """
    Provide path to the examples directory.
    
    Returns:
        Path: Path to examples directory
    """
    return Path(__file__).parent.parent / "examples"


@pytest.fixture
def test_data_dir():
    """
    Provide path to the test data directory.
    
    Returns:
        Path: Path to tests/data directory
    """
    return Path(__file__).parent / "data"


@pytest.fixture
def example_csv_path(examples_dir):
    """
    Provide path to the ok_run.csv example file.
    
    Args:
        examples_dir: Examples directory fixture
        
    Returns:
        Path: Path to ok_run.csv
    """
    return examples_dir / "ok_run.csv"


@pytest.fixture
def gaps_csv_path(examples_dir):
    """
    Provide path to the gaps.csv example file.
    
    Args:
        examples_dir: Examples directory fixture
        
    Returns:
        Path: Path to gaps.csv
    """
    return examples_dir / "gaps.csv"


@pytest.fixture
def spec_example_path(examples_dir):
    """
    Provide path to the spec_example.json file.
    
    Args:
        examples_dir: Examples directory fixture
        
    Returns:
        Path: Path to spec_example.json
    """
    return examples_dir / "spec_example.json"


@pytest.fixture
def fahrenheit_csv_path(examples_dir):
    """
    Provide path to the Fahrenheit example CSV file.
    
    Args:
        examples_dir: Examples directory fixture
        
    Returns:
        Path: Path to Fahrenheit input CSV
    """
    return examples_dir / "powder_coat_cure_fahrenheit_input_356f_10min_pass.csv"


@pytest.fixture
def fahrenheit_spec_path(examples_dir):
    """
    Provide path to the Fahrenheit example spec file.
    
    Args:
        examples_dir: Examples directory fixture
        
    Returns:
        Path: Path to Fahrenheit spec JSON
    """
    return examples_dir / "powder_coat_cure_spec_fahrenheit_input_356f_10min.json"


@pytest.fixture
def example_spec_data() -> Dict[str, Any]:
    """
    Provide example specification data as dictionary.
    
    Returns:
        Dict containing valid SpecV1 data
    """
    return {
        "version": "1.0",
        "job": {
            "job_id": "test_batch_001"
        },
        "spec": {
            "method": "PMT",
            "target_temp_C": 180.0,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 2.0
        },
        "data_requirements": {
            "max_sample_period_s": 30.0,
            "allowed_gaps_s": 60.0
        },
        "sensor_selection": {
            "mode": "min_of_set",
            "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
            "require_at_least": 1
        },
        "logic": {
            "continuous": True,
            "max_total_dips_s": 0
        },
        "reporting": {
            "units": "C",
            "language": "en",
            "timezone": "UTC"
        }
    }


@pytest.fixture
def example_spec(example_spec_data) -> SpecV1:
    """
    Provide example SpecV1 instance.
    
    Args:
        example_spec_data: Spec data fixture
        
    Returns:
        SpecV1: Validated specification instance
    """
    return SpecV1(**example_spec_data)


@pytest.fixture
def simple_temp_data() -> pd.DataFrame:
    """
    Provide simple temperature DataFrame for testing.
    
    Returns:
        pd.DataFrame: Simple temperature data with 30s intervals
    """
    timestamps = pd.date_range(
        start="2024-01-15T10:00:00Z",
        periods=26,
        freq="30s",
        tz="UTC"
    )
    
    # Create temperature data that passes - ramps up to 182°C and holds
    # Conservative threshold = 180 + 2 = 182°C, so min_of_set must be >= 182°C
    # Need 600s hold time = 20 intervals, so ramp in 5 samples, hold for 21 samples
    temps_1 = [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 21
    temps_2 = [164.5, 169.5, 174.5, 178.5, 180.5] + [182.5] * 21
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "pmt_sensor_1": temps_1,
        "pmt_sensor_2": temps_2
    })


@pytest.fixture
def failing_temp_data() -> pd.DataFrame:
    """
    Provide temperature DataFrame that should fail validation.
    
    Returns:
        pd.DataFrame: Temperature data that fails hold time requirement
    """
    timestamps = pd.date_range(
        start="2024-01-15T10:00:00Z",
        periods=25,
        freq="30s",
        tz="UTC"
    )
    
    # Temperature data that doesn't reach target or hold long enough
    # Max temp is 180.5°C which is below conservative threshold of 182°C
    temps_1 = [165.0, 170.0, 175.0, 179.0, 181.0] + [175.0] * 20
    temps_2 = [164.5, 169.5, 174.5, 178.5, 180.5] + [174.5] * 20
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "pmt_sensor_1": temps_1,
        "pmt_sensor_2": temps_2
    })


@pytest.fixture
def fahrenheit_temp_data() -> pd.DataFrame:
    """
    Provide temperature DataFrame with Fahrenheit data.
    
    Returns:
        pd.DataFrame: Temperature data in Fahrenheit
    """
    timestamps = pd.date_range(
        start="2024-01-15T10:00:00Z",
        periods=26,
        freq="30s",
        tz="UTC"
    )
    
    # Temperature data in Fahrenheit: correspond to passing Celsius values
    # 183°C = 361.4°F, 182.5°C = 360.5°F (above 182°C threshold)
    temps_1_f = [329.0, 338.0, 347.0, 354.0, 358.0] + [361.4] * 21
    temps_2_f = [328.0, 337.0, 346.0, 353.0, 357.0] + [360.5] * 21
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "pmt_sensor_1_f": temps_1_f,
        "pmt_sensor_2_f": temps_2_f
    })


@pytest.fixture
def gaps_temp_data() -> pd.DataFrame:
    """
    Provide temperature DataFrame with data gaps.
    
    Returns:
        pd.DataFrame: Temperature data with missing timestamps (gaps)
    """
    # Create timestamps with gaps
    timestamps = []
    base_time = pd.Timestamp("2024-01-15T10:00:00Z")
    
    # Normal data for first 5 points (0-2 minutes)
    for i in range(5):
        timestamps.append(base_time + pd.Timedelta(seconds=i*30))
    
    # 90 second gap (skip 3 points)
    for i in range(8, 15):  # Resume at 4 minutes
        timestamps.append(base_time + pd.Timedelta(seconds=i*30))
    
    temps_1 = [165.0, 170.0, 175.0, 179.0, 181.0, 183.0, 183.0, 183.0, 183.0, 183.0, 183.0, 183.0]
    temps_2 = [164.5, 169.5, 174.5, 178.5, 180.5, 182.5, 182.5, 182.5, 182.5, 182.5, 182.5, 182.5]
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "pmt_sensor_1": temps_1,
        "pmt_sensor_2": temps_2
    })


@pytest.fixture
def unix_timestamp_data() -> pd.DataFrame:
    """
    Provide temperature DataFrame with UNIX timestamps.
    
    Returns:
        pd.DataFrame: Temperature data with UNIX timestamp column
    """
    # Start at 2024-01-15T10:00:00Z = 1705320000
    base_unix = 1705320000
    unix_times = [base_unix + i*30 for i in range(26)]
    
    temps_1 = [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 21
    temps_2 = [164.5, 169.5, 174.5, 178.5, 180.5] + [182.5] * 21
    
    return pd.DataFrame({
        "unix_timestamp": unix_times,
        "pmt_sensor_1": temps_1,
        "pmt_sensor_2": temps_2
    })


@pytest.fixture
def duplicate_timestamp_data() -> pd.DataFrame:
    """
    Provide temperature DataFrame with duplicate timestamps.
    
    Returns:
        pd.DataFrame: Temperature data with duplicate timestamp entries
    """
    timestamps = pd.date_range(
        start="2024-01-15T10:00:00Z",
        periods=20,
        freq="30s",
        tz="UTC"
    ).tolist()
    
    # Add duplicate timestamp
    timestamps.insert(10, timestamps[9])
    
    temps_1 = [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 16
    temps_2 = [164.5, 169.5, 174.5, 178.5, 180.5] + [182.5] * 16
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "pmt_sensor_1": temps_1,
        "pmt_sensor_2": temps_2
    })


@pytest.fixture
def non_monotonic_data() -> pd.DataFrame:
    """
    Provide temperature DataFrame with non-monotonic timestamps.
    
    Returns:
        pd.DataFrame: Temperature data with out-of-order timestamps
    """
    timestamps = pd.date_range(
        start="2024-01-15T10:00:00Z",
        periods=20,
        freq="30s",
        tz="UTC"
    ).tolist()
    
    # Swap two timestamps to make non-monotonic
    timestamps[5], timestamps[10] = timestamps[10], timestamps[5]
    
    temps_1 = [165.0, 170.0, 175.0, 179.0, 181.0] + [183.0] * 15
    temps_2 = [164.5, 169.5, 174.5, 178.5, 180.5] + [182.5] * 15
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "pmt_sensor_1": temps_1,
        "pmt_sensor_2": temps_2
    })


def create_temp_csv(df: pd.DataFrame, path: Path, metadata: Dict[str, str] = None) -> None:
    """
    Helper function to create CSV files with metadata headers.
    
    Args:
        df: DataFrame to save
        path: Path where to save CSV
        metadata: Optional metadata to include as comments
    """
    with open(path, 'w') as f:
        # Write metadata as comments
        if metadata:
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
        
        # Write CSV data
        df.to_csv(f, index=False)


def create_temp_spec(spec_data: Dict[str, Any], path: Path) -> None:
    """
    Helper function to create temporary spec JSON files.
    
    Args:
        spec_data: Specification data dictionary
        path: Path where to save JSON
    """
    with open(path, 'w') as f:
        json.dump(spec_data, f, indent=2)