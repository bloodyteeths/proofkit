"""
ProofKit Evidence Bundle Packer

Creates tamper-evident evidence bundles (evidence.zip) according to ROADMAP.md M4
requirements. Bundles all inputs and outputs with SHA-256 integrity checks
and deterministic zip creation for verification workflows.

Example usage:
    from core.pack import create_evidence_bundle
    from pathlib import Path
    
    # Bundle all evidence files
    bundle_path = create_evidence_bundle(
        raw_csv_path="temp_data.csv",
        spec_json_path="spec.json", 
        normalized_csv_path="normalized.csv",
        decision_json_path="decision.json",
        proof_pdf_path="proof.pdf",
        plot_png_path="plot.png",
        output_path="evidence.zip"
    )
    print(f"Evidence bundle created: {bundle_path}")
"""

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


class PackingError(Exception):
    """Raised when evidence bundle creation fails."""
    pass


def calculate_file_hash(file_path: Path) -> str:
    """
    Calculate SHA-256 hash of a file.
    
    Args:
        file_path: Path to the file to hash
        
    Returns:
        Hexadecimal SHA-256 hash string
        
    Raises:
        PackingError: If file cannot be read or hashed
    """
    if not file_path.exists():
        raise PackingError(f"File not found for hashing: {file_path}")
    
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        raise PackingError(f"Failed to calculate hash for {file_path}: {e}")


def calculate_content_hash(content: bytes) -> str:
    """
    Calculate SHA-256 hash of byte content.
    
    Args:
        content: Byte content to hash
        
    Returns:
        Hexadecimal SHA-256 hash string
    """
    return hashlib.sha256(content).hexdigest()


def create_manifest(file_info: List[Tuple[str, Path, str]], 
                   metadata: Dict[str, Any],
                   deterministic: bool = False) -> Tuple[Dict[str, Any], str]:
    """
    Create manifest with file hashes and calculate root hash.
    
    Args:
        file_info: List of (archive_path, source_path, file_hash) tuples
        metadata: Additional metadata to include in manifest
        deterministic: If True, use fixed timestamp for reproducible builds
        
    Returns:
        Tuple of (manifest_dict, root_hash)
    """
    # Create manifest structure
    if deterministic:
        created_at = "1980-01-01T00:00:00+00:00"  # Fixed timestamp for deterministic builds
    else:
        created_at = datetime.now(timezone.utc).isoformat()
    
    manifest = {
        "version": "1.0",
        "created_at": created_at,
        "metadata": metadata,
        "files": {}
    }
    
    # Add file information
    for archive_path, source_path, file_hash in file_info:
        manifest["files"][archive_path] = {
            "sha256": file_hash,
            "size_bytes": source_path.stat().st_size,
            "source_name": source_path.name
        }
    
    # Calculate root hash from sorted file hashes
    file_hashes = [info[2] for info in sorted(file_info, key=lambda x: x[0])]
    combined_hashes = "".join(file_hashes)
    root_hash = hashlib.sha256(combined_hashes.encode('utf-8')).hexdigest()
    
    manifest["root_hash"] = root_hash
    
    return manifest, root_hash


def validate_required_files(raw_csv_path: Optional[Path] = None,
                          spec_json_path: Optional[Path] = None,
                          normalized_csv_path: Optional[Path] = None,
                          decision_json_path: Optional[Path] = None,
                          proof_pdf_path: Optional[Path] = None,
                          plot_png_path: Optional[Path] = None) -> List[str]:
    """
    Validate that required files exist and are readable.
    
    Args:
        Various file paths for evidence bundle components
        
    Returns:
        List of validation error messages (empty if all valid)
    """
    errors = []
    required_files = {
        "Raw CSV": raw_csv_path,
        "Spec JSON": spec_json_path,
        "Normalized CSV": normalized_csv_path,
        "Decision JSON": decision_json_path,
        "Proof PDF": proof_pdf_path,
        "Plot PNG": plot_png_path
    }
    
    for file_type, file_path in required_files.items():
        if file_path is None:
            errors.append(f"{file_type} path not provided")
            continue
            
        if not file_path.exists():
            errors.append(f"{file_type} not found: {file_path}")
            continue
            
        if not file_path.is_file():
            errors.append(f"{file_type} is not a file: {file_path}")
            continue
            
        try:
            # Test file readability
            with open(file_path, 'rb') as f:
                f.read(1)
        except Exception as e:
            errors.append(f"{file_type} cannot be read: {file_path} ({e})")
    
    return errors


def create_evidence_bundle(raw_csv_path: str,
                         spec_json_path: str,
                         normalized_csv_path: str,
                         decision_json_path: str,
                         proof_pdf_path: str,
                         plot_png_path: str,
                         output_path: str,
                         job_id: Optional[str] = None,
                         deterministic: bool = False) -> str:
    """
    Create tamper-evident evidence bundle (evidence.zip).
    
    Creates a ZIP archive containing all inputs and outputs with a manifest
    that includes SHA-256 hashes for each file and a root hash for integrity
    verification. The ZIP is created deterministically for reproducible builds.
    
    Args:
        raw_csv_path: Path to original raw CSV data
        spec_json_path: Path to specification JSON file
        normalized_csv_path: Path to normalized CSV data
        decision_json_path: Path to decision result JSON
        proof_pdf_path: Path to proof PDF document
        plot_png_path: Path to temperature plot PNG image
        output_path: Path where evidence.zip will be created
        job_id: Optional job identifier for metadata
        deterministic: If True, create reproducible bundle with fixed timestamps
        
    Returns:
        Absolute path to created evidence bundle
        
    Raises:
        PackingError: If bundle creation fails
    """
    try:
        # Convert paths to Path objects
        raw_csv = Path(raw_csv_path)
        spec_json = Path(spec_json_path)
        normalized_csv = Path(normalized_csv_path)
        decision_json = Path(decision_json_path)
        proof_pdf = Path(proof_pdf_path)
        plot_png = Path(plot_png_path)
        output = Path(output_path)
        
        # Validate all required files exist
        validation_errors = validate_required_files(
            raw_csv, spec_json, normalized_csv, 
            decision_json, proof_pdf, plot_png
        )
        
        if validation_errors:
            error_msg = "Validation failed:\n" + "\n".join(f"- {error}" for error in validation_errors)
            raise PackingError(error_msg)
        
        # Ensure output directory exists
        output.parent.mkdir(parents=True, exist_ok=True)
        
        # Define file organization within ZIP
        file_mapping = [
            ("inputs/raw_data.csv", raw_csv),
            ("inputs/specification.json", spec_json),
            ("outputs/normalized_data.csv", normalized_csv),
            ("outputs/decision.json", decision_json),
            ("outputs/proof.pdf", proof_pdf),
            ("outputs/plot.png", plot_png)
        ]
        
        # Calculate hashes for all files
        file_info = []
        logger.info("Calculating file hashes...")
        
        for archive_path, source_path in file_mapping:
            file_hash = calculate_file_hash(source_path)
            file_info.append((archive_path, source_path, file_hash))
            logger.debug(f"Hash calculated for {archive_path}: {file_hash[:16]}...")
        
        # Create metadata
        metadata = {
            "proofkit_version": "0.1.0",
            "bundle_type": "evidence",
            "job_id": job_id or "unknown",
            "created_by": "ProofKit Evidence Packer",
            "file_count": len(file_mapping)
        }
        
        # Create manifest and calculate root hash
        manifest, root_hash = create_manifest(file_info, metadata, deterministic)
        
        # Create manifest JSON content
        manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
        manifest_bytes = manifest_json.encode('utf-8')
        manifest_hash = calculate_content_hash(manifest_bytes)
        
        # Add manifest to file info
        file_info.append(("manifest.json", None, manifest_hash))
        
        logger.info(f"Creating evidence bundle with root hash: {root_hash[:16]}...")
        
        # Create deterministic ZIP file
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            # Set consistent timestamp for deterministic zip creation
            # Use Unix epoch for reproducible builds
            fixed_time = (1980, 1, 1, 0, 0, 0)
            
            # Add all files in deterministic order (sorted by archive path)
            for archive_path, source_path, _ in sorted(file_info, key=lambda x: x[0]):
                if source_path is None:
                    # This is the manifest file
                    info = zipfile.ZipInfo(archive_path)
                    info.date_time = fixed_time
                    info.external_attr = 0o644 << 16  # Set file permissions
                    zipf.writestr(info, manifest_bytes)
                else:
                    # Regular file
                    info = zipfile.ZipInfo(archive_path)
                    info.date_time = fixed_time
                    info.external_attr = 0o644 << 16  # Set file permissions
                    
                    with open(source_path, 'rb') as src_file:
                        zipf.writestr(info, src_file.read())
        
        logger.info(f"Evidence bundle created successfully: {output}")
        logger.info(f"Bundle root hash: {root_hash}")
        logger.info(f"Bundle size: {output.stat().st_size} bytes")
        
        return str(output.absolute())
    
    except Exception as e:
        logger.error(f"Failed to create evidence bundle: {e}")
        raise PackingError(f"Evidence bundle creation failed: {str(e)}")


def verify_evidence_bundle(bundle_path: str) -> Dict[str, Any]:
    """
    Verify evidence bundle integrity by checking all file hashes.
    
    Args:
        bundle_path: Path to evidence.zip bundle
        
    Returns:
        Dictionary with verification results
        
    Raises:
        PackingError: If bundle cannot be verified
    """
    try:
        bundle = Path(bundle_path)
        if not bundle.exists():
            raise PackingError(f"Evidence bundle not found: {bundle_path}")
        
        verification_result = {
            "bundle_path": str(bundle.absolute()),
            "valid": False,
            "manifest_found": False,
            "files_verified": 0,
            "files_total": 0,
            "hash_mismatches": [],
            "missing_files": [],
            "root_hash": None,
            "root_hash_valid": False
        }
        
        with zipfile.ZipFile(bundle, 'r') as zipf:
            # Check if manifest exists
            if "manifest.json" not in zipf.namelist():
                raise PackingError("Manifest not found in evidence bundle")
            
            verification_result["manifest_found"] = True
            
            # Read and parse manifest
            manifest_content = zipf.read("manifest.json")
            manifest = json.loads(manifest_content.decode('utf-8'))
            
            verification_result["root_hash"] = manifest.get("root_hash")
            verification_result["files_total"] = len(manifest.get("files", {}))
            
            # Verify each file hash
            for archive_path, file_info in manifest["files"].items():
                expected_hash = file_info["sha256"]
                
                if archive_path not in zipf.namelist():
                    verification_result["missing_files"].append(archive_path)
                    continue
                
                # Calculate actual hash
                file_content = zipf.read(archive_path)
                actual_hash = calculate_content_hash(file_content)
                
                if actual_hash == expected_hash:
                    verification_result["files_verified"] += 1
                else:
                    verification_result["hash_mismatches"].append({
                        "file": archive_path,
                        "expected": expected_hash,
                        "actual": actual_hash
                    })
            
            # Verify root hash
            file_hashes = []
            for archive_path in sorted(manifest["files"].keys()):
                file_hashes.append(manifest["files"][archive_path]["sha256"])
            
            combined_hashes = "".join(file_hashes)
            calculated_root_hash = hashlib.sha256(combined_hashes.encode('utf-8')).hexdigest()
            
            verification_result["root_hash_valid"] = (
                calculated_root_hash == verification_result["root_hash"]
            )
            
            # Overall validity check
            verification_result["valid"] = (
                verification_result["files_verified"] == verification_result["files_total"] and
                len(verification_result["hash_mismatches"]) == 0 and
                len(verification_result["missing_files"]) == 0 and
                verification_result["root_hash_valid"]
            )
        
        return verification_result
    
    except Exception as e:
        logger.error(f"Failed to verify evidence bundle: {e}")
        raise PackingError(f"Evidence bundle verification failed: {str(e)}")


def extract_evidence_bundle(bundle_path: str, extract_dir: str) -> Dict[str, str]:
    """
    Extract evidence bundle to directory for inspection.
    
    Args:
        bundle_path: Path to evidence.zip bundle
        extract_dir: Directory to extract files to
        
    Returns:
        Dictionary mapping archive paths to extracted file paths
        
    Raises:
        PackingError: If extraction fails
    """
    try:
        bundle = Path(bundle_path)
        extract_path = Path(extract_dir)
        
        if not bundle.exists():
            raise PackingError(f"Evidence bundle not found: {bundle_path}")
        
        # Create extraction directory
        extract_path.mkdir(parents=True, exist_ok=True)
        
        extracted_files = {}
        
        with zipfile.ZipFile(bundle, 'r') as zipf:
            for archive_path in zipf.namelist():
                # Extract file
                extracted_file = extract_path / archive_path
                extracted_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(extracted_file, 'wb') as f:
                    f.write(zipf.read(archive_path))
                
                extracted_files[archive_path] = str(extracted_file.absolute())
        
        logger.info(f"Evidence bundle extracted to: {extract_path}")
        return extracted_files
    
    except Exception as e:
        logger.error(f"Failed to extract evidence bundle: {e}")
        raise PackingError(f"Evidence bundle extraction failed: {str(e)}")


# Usage example in comments:
"""
Example usage for ProofKit evidence bundle creation:

from core.pack import create_evidence_bundle, verify_evidence_bundle
from pathlib import Path

# Create evidence bundle from all components
bundle_path = create_evidence_bundle(
    raw_csv_path="data/temperature_log.csv",
    spec_json_path="specs/cure_spec.json",
    normalized_csv_path="outputs/normalized.csv", 
    decision_json_path="outputs/decision.json",
    proof_pdf_path="outputs/proof.pdf",
    plot_png_path="outputs/plot.png",
    output_path="evidence/evidence.zip",
    job_id="batch_001"
)

print(f"Evidence bundle created: {bundle_path}")

# Verify bundle integrity
verification = verify_evidence_bundle(bundle_path)
if verification["valid"]:
    print(f"Bundle verified successfully (root hash: {verification['root_hash'][:16]}...)")
else:
    print(f"Bundle verification failed: {verification}")
"""