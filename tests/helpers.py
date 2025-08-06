"""
ProofKit Test Helper Utilities

Provides utility functions for testing ProofKit components including
ZIP file handling, hash computation, and fixture loading.

Example usage:
    zip_contents = read_zip_file(zip_path)
    file_hash = compute_sha256_file(file_path)
    csv_data = load_csv_fixture("min_powder.csv")
    spec_data = load_spec_fixture("min_powder_spec.json")
"""

import json
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd

from core.models import SpecV1


def read_zip_file(zip_path: Path) -> Dict[str, bytes]:
    """
    Read contents of a ZIP file and return as dictionary.
    
    Args:
        zip_path: Path to the ZIP file
        
    Returns:
        Dict mapping filename to file contents as bytes
        
    Raises:
        FileNotFoundError: If ZIP file doesn't exist
        zipfile.BadZipFile: If file is not a valid ZIP
        
    Example:
        >>> zip_contents = read_zip_file(Path("evidence.zip"))
        >>> manifest_content = zip_contents["manifest.txt"]
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path}")
    
    contents = {}
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for filename in zf.namelist():
            contents[filename] = zf.read(filename)
    
    return contents


def read_zip_file_text(zip_path: Path) -> Dict[str, str]:
    """
    Read contents of a ZIP file and return text files as strings.
    
    Args:
        zip_path: Path to the ZIP file
        
    Returns:
        Dict mapping filename to file contents as strings (UTF-8 decoded)
        
    Example:
        >>> zip_texts = read_zip_file_text(Path("evidence.zip"))
        >>> manifest_lines = zip_texts["manifest.txt"].split("\\n")
    """
    byte_contents = read_zip_file(zip_path)
    text_contents = {}
    
    for filename, content in byte_contents.items():
        try:
            text_contents[filename] = content.decode('utf-8')
        except UnicodeDecodeError:
            # Skip binary files
            continue
            
    return text_contents


def compute_sha256_file(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file.
    
    Args:
        file_path: Path to the file to hash
        
    Returns:
        Hexadecimal SHA-256 hash string
        
    Raises:
        FileNotFoundError: If file doesn't exist
        
    Example:
        >>> file_hash = compute_sha256_file(Path("proof.pdf"))
        >>> assert len(file_hash) == 64
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read file in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    
    return sha256_hash.hexdigest()


def compute_sha256_bytes(data: bytes) -> str:
    """
    Compute SHA-256 hash of byte data.
    
    Args:
        data: Byte data to hash
        
    Returns:
        Hexadecimal SHA-256 hash string
        
    Example:
        >>> content_hash = compute_sha256_bytes(b"Hello, World!")
        >>> assert len(content_hash) == 64
    """
    return hashlib.sha256(data).hexdigest()


def load_csv_fixture(filename: str) -> pd.DataFrame:
    """
    Load a CSV fixture from the fixtures directory.
    
    Args:
        filename: Name of the CSV file in tests/fixtures/
        
    Returns:
        DataFrame with parsed CSV data
        
    Raises:
        FileNotFoundError: If fixture file doesn't exist
        
    Example:
        >>> df = load_csv_fixture("min_powder.csv")
        >>> assert "timestamp" in df.columns
        >>> assert "temp_C" in df.columns
    """
    fixtures_dir = Path(__file__).parent / "fixtures"
    csv_path = fixtures_dir / filename
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV fixture not found: {csv_path}")
    
    # Read CSV, skipping comment lines
    return pd.read_csv(csv_path, comment='#')


def load_spec_fixture(filename: str) -> Dict[str, Any]:
    """
    Load a spec JSON fixture from the fixtures directory.
    
    Args:
        filename: Name of the JSON file in tests/fixtures/
        
    Returns:
        Dictionary with parsed spec data
        
    Raises:
        FileNotFoundError: If fixture file doesn't exist
        json.JSONDecodeError: If JSON is invalid
        
    Example:
        >>> spec_data = load_spec_fixture("min_powder_spec.json")
        >>> assert spec_data["version"] == "1.0"
        >>> assert spec_data["spec"]["method"] == "PMT"
    """
    fixtures_dir = Path(__file__).parent / "fixtures"
    spec_path = fixtures_dir / filename
    
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec fixture not found: {spec_path}")
    
    with open(spec_path, 'r') as f:
        return json.load(f)


def load_spec_fixture_validated(filename: str) -> SpecV1:
    """
    Load and validate a spec JSON fixture as SpecV1 instance.
    
    Args:
        filename: Name of the JSON file in tests/fixtures/
        
    Returns:
        Validated SpecV1 instance
        
    Raises:
        FileNotFoundError: If fixture file doesn't exist
        ValidationError: If spec data is invalid
        
    Example:
        >>> spec = load_spec_fixture_validated("min_powder_spec.json")
        >>> assert spec.spec.target_temp_C == 170.0
        >>> assert spec.spec.method == "PMT"
    """
    spec_data = load_spec_fixture(filename)
    return SpecV1(**spec_data)


def verify_zip_manifest(zip_path: Path) -> Tuple[Dict[str, str], str]:
    """
    Verify ZIP file manifest and return file hashes and root hash.
    
    Args:
        zip_path: Path to evidence ZIP file
        
    Returns:
        Tuple of (file_hashes_dict, root_hash_string)
        
    Raises:
        FileNotFoundError: If ZIP or manifest files don't exist
        ValueError: If manifest format is invalid
        
    Example:
        >>> file_hashes, root_hash = verify_zip_manifest(Path("evidence.zip"))
        >>> assert "proof.pdf" in file_hashes
        >>> assert len(root_hash) == 64
    """
    zip_contents = read_zip_file_text(zip_path)
    
    if "manifest.txt" not in zip_contents:
        raise ValueError("No manifest.txt found in ZIP file")
    
    if "root.sha256" not in zip_contents:
        raise ValueError("No root.sha256 found in ZIP file")
    
    # Parse manifest file
    manifest_lines = zip_contents["manifest.txt"].strip().split('\n')
    file_hashes = {}
    
    for line in manifest_lines:
        if not line.strip() or line.startswith('#'):
            continue
            
        parts = line.strip().split('  ', 1)  # SHA-256 format uses two spaces
        if len(parts) != 2:
            raise ValueError(f"Invalid manifest line format: {line}")
            
        hash_value, filename = parts
        if len(hash_value) != 64:
            raise ValueError(f"Invalid hash length for {filename}: {hash_value}")
            
        file_hashes[filename] = hash_value
    
    # Get root hash
    root_hash = zip_contents["root.sha256"].strip()
    if len(root_hash) != 64:
        raise ValueError(f"Invalid root hash length: {root_hash}")
    
    return file_hashes, root_hash


def fixtures_dir() -> Path:
    """
    Get path to the test fixtures directory.
    
    Returns:
        Path to tests/fixtures/ directory
        
    Example:
        >>> fixtures_path = fixtures_dir()
        >>> csv_path = fixtures_path / "min_powder.csv"
    """
    return Path(__file__).parent / "fixtures"


def create_minimal_zip(output_path: Path, files: Dict[str, bytes]) -> None:
    """
    Create a minimal ZIP file with given contents.
    
    Args:
        output_path: Where to create the ZIP file
        files: Dict mapping filename to file contents as bytes
        
    Example:
        >>> files = {"test.txt": b"Hello", "data.json": b'{"key": "value"}'}
        >>> create_minimal_zip(Path("test.zip"), files)
    """
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)