"""
ProofKit Evidence Bundle Verification System

Implements comprehensive verification system for evidence bundles according to
ROADMAP.md M4 requirements and CLAUDE.md principles. Validates bundle integrity,
re-runs decision algorithms, and provides detailed verification reports.

Example usage:
    from core.verify import verify_evidence_bundle, VerificationReport
    
    # Verify complete evidence bundle
    report = verify_evidence_bundle("evidence.zip")
    
    if report.is_valid:
        print(f"Bundle verified successfully (root hash: {report.root_hash[:16]}...)")
        print(f"Decision matches: {report.decision_matches}")
    else:
        print(f"Verification failed: {report.issues}")
"""

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
import logging
import hashlib
import pandas as pd

from core.models import SpecV1, DecisionResult
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.pack import calculate_content_hash, PackingError

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """Raised when evidence bundle verification fails."""
    pass


class VerificationReport:
    """
    Comprehensive verification report for evidence bundles.
    
    Contains all verification results including integrity checks,
    decision re-computation, and tamper detection.
    """
    
    def __init__(self):
        self.bundle_path: Optional[str] = None
        self.timestamp = datetime.now(timezone.utc).isoformat()
        
        # Bundle integrity results
        self.bundle_exists = False
        self.manifest_found = False
        self.manifest_valid = False
        self.root_hash: Optional[str] = None
        self.root_hash_valid = False
        
        # File integrity results
        self.files_total = 0
        self.files_verified = 0
        self.missing_files: List[str] = []
        self.hash_mismatches: List[Dict[str, str]] = []
        self.extra_files: List[str] = []
        
        # Decision re-computation results
        self.decision_recomputed = False
        self.original_decision: Optional[DecisionResult] = None
        self.recomputed_decision: Optional[DecisionResult] = None
        self.decision_matches = False
        self.decision_discrepancies: List[str] = []
        
        # Data processing results
        self.data_normalized = False
        self.normalization_issues: List[str] = []
        
        # Overall verification status
        self.is_valid = False
        self.issues: List[str] = []
        self.warnings: List[str] = []
        
        # Metadata
        self.bundle_metadata: Dict[str, Any] = {}
        self.verification_metadata = {
            "proofkit_version": "0.1.0",
            "verification_timestamp": self.timestamp,
            "verifier": "ProofKit Verification System"
        }
    
    def add_issue(self, issue: str, is_warning: bool = False):
        """Add a verification issue or warning."""
        if is_warning:
            self.warnings.append(issue)
        else:
            self.issues.append(issue)
    
    def finalize(self):
        """Finalize verification status based on all checks."""
        self.is_valid = (
            self.bundle_exists and
            self.manifest_found and
            self.manifest_valid and
            self.root_hash_valid and
            self.files_verified == self.files_total and
            len(self.hash_mismatches) == 0 and
            len(self.missing_files) == 0 and
            (not self.decision_recomputed or self.decision_matches) and
            len(self.issues) == 0
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary format."""
        return {
            "verification_metadata": self.verification_metadata,
            "bundle_path": self.bundle_path,
            "timestamp": self.timestamp,
            "is_valid": self.is_valid,
            "bundle_integrity": {
                "bundle_exists": self.bundle_exists,
                "manifest_found": self.manifest_found,
                "manifest_valid": self.manifest_valid,
                "root_hash": self.root_hash,
                "root_hash_valid": self.root_hash_valid,
                "files_total": self.files_total,
                "files_verified": self.files_verified,
                "missing_files": self.missing_files,
                "hash_mismatches": self.hash_mismatches,
                "extra_files": self.extra_files
            },
            "decision_verification": {
                "decision_recomputed": self.decision_recomputed,
                "decision_matches": self.decision_matches,
                "decision_discrepancies": self.decision_discrepancies,
                "original_decision": self.original_decision.model_dump() if self.original_decision else None,
                "recomputed_decision": self.recomputed_decision.model_dump() if self.recomputed_decision else None
            },
            "data_processing": {
                "data_normalized": self.data_normalized,
                "normalization_issues": self.normalization_issues
            },
            "bundle_metadata": self.bundle_metadata,
            "issues": self.issues,
            "warnings": self.warnings
        }
    
    def __str__(self) -> str:
        """String representation of verification report."""
        status = "VALID" if self.is_valid else "INVALID"
        lines = [
            f"ProofKit Evidence Bundle Verification Report",
            f"Bundle: {self.bundle_path}",
            f"Status: {status}",
            f"Timestamp: {self.timestamp}",
            "",
            f"Bundle Integrity:",
            f"  Root Hash: {self.root_hash[:16] + '...' if self.root_hash else 'N/A'}",
            f"  Files Verified: {self.files_verified}/{self.files_total}",
            f"  Hash Valid: {self.root_hash_valid}",
        ]
        
        if self.decision_recomputed:
            lines.extend([
                "",
                f"Decision Verification:",
                f"  Decision Matches: {self.decision_matches}",
                f"  Discrepancies: {len(self.decision_discrepancies)}"
            ])
        
        if self.issues:
            lines.extend(["", "Issues:"] + [f"  - {issue}" for issue in self.issues])
        
        if self.warnings:
            lines.extend(["", "Warnings:"] + [f"  - {warning}" for warning in self.warnings])
        
        return "\n".join(lines)


def extract_bundle_to_temp(bundle_path: str) -> Tuple[str, Dict[str, str]]:
    """
    Extract evidence bundle to temporary directory.
    
    Args:
        bundle_path: Path to evidence bundle
        
    Returns:
        Tuple of (temp_directory_path, extracted_files_mapping)
        
    Raises:
        VerificationError: If extraction fails
    """
    try:
        bundle = Path(bundle_path)
        if not bundle.exists():
            raise VerificationError(f"Evidence bundle not found: {bundle_path}")
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix='proofkit_verify_')
        temp_path = Path(temp_dir)
        
        extracted_files = {}
        
        with zipfile.ZipFile(bundle, 'r') as zipf:
            # Validate zip file integrity
            bad_file = zipf.testzip()
            if bad_file:
                raise VerificationError(f"Corrupted zip file - bad file: {bad_file}")
            
            # Extract all files
            for archive_path in zipf.namelist():
                try:
                    # Security check: prevent path traversal
                    if '..' in archive_path or archive_path.startswith('/'):
                        raise VerificationError(f"Unsafe archive path detected: {archive_path}")
                    
                    # Extract file
                    extracted_file = temp_path / archive_path
                    extracted_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(extracted_file, 'wb') as f:
                        f.write(zipf.read(archive_path))
                    
                    extracted_files[archive_path] = str(extracted_file)
                    
                except Exception as e:
                    raise VerificationError(f"Failed to extract {archive_path}: {e}")
        
        logger.info(f"Evidence bundle extracted to: {temp_dir}")
        return temp_dir, extracted_files
    
    except Exception as e:
        logger.error(f"Failed to extract evidence bundle: {e}")
        raise VerificationError(f"Evidence bundle extraction failed: {str(e)}")


def verify_bundle_integrity(bundle_path: str, extracted_files: Dict[str, str]) -> Tuple[bool, Dict[str, Any]]:
    """
    Verify bundle integrity using manifest checksums.
    
    Args:
        bundle_path: Path to evidence bundle
        extracted_files: Mapping of archive paths to extracted file paths
        
    Returns:
        Tuple of (integrity_valid, verification_details)
    """
    verification = {
        "manifest_found": False,
        "manifest_valid": False,
        "root_hash": None,
        "root_hash_valid": False,
        "files_total": 0,
        "files_verified": 0,
        "missing_files": [],
        "hash_mismatches": [],
        "extra_files": [],
        "bundle_metadata": {}
    }
    
    try:
        # Check if manifest exists
        if "manifest.json" not in extracted_files:
            return False, verification
        
        verification["manifest_found"] = True
        
        # Read and parse manifest
        manifest_path = extracted_files["manifest.json"]
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        verification["manifest_valid"] = True
        verification["root_hash"] = manifest.get("root_hash")
        verification["bundle_metadata"] = manifest.get("metadata", {})
        
        manifest_files = manifest.get("files", {})
        verification["files_total"] = len(manifest_files)
        
        # Verify each file hash
        file_hashes_for_root = []
        
        for archive_path in sorted(manifest_files.keys()):
            file_info = manifest_files[archive_path]
            expected_hash = file_info["sha256"]
            file_hashes_for_root.append(expected_hash)
            
            if archive_path not in extracted_files:
                verification["missing_files"].append(archive_path)
                continue
            
            # Calculate actual hash
            extracted_path = Path(extracted_files[archive_path])
            with open(extracted_path, 'rb') as f:
                actual_hash = calculate_content_hash(f.read())
            
            if actual_hash == expected_hash:
                verification["files_verified"] += 1
            else:
                verification["hash_mismatches"].append({
                    "file": archive_path,
                    "expected": expected_hash,
                    "actual": actual_hash
                })
        
        # Check for extra files (not in manifest)
        manifest_file_set = set(manifest_files.keys()) | {"manifest.json"}
        extracted_file_set = set(extracted_files.keys())
        extra_files = extracted_file_set - manifest_file_set
        verification["extra_files"] = list(extra_files)
        
        # Verify root hash
        combined_hashes = "".join(file_hashes_for_root)
        calculated_root_hash = hashlib.sha256(combined_hashes.encode('utf-8')).hexdigest()
        verification["root_hash_valid"] = (calculated_root_hash == verification["root_hash"])
        
        # Overall integrity check
        integrity_valid = (
            verification["files_verified"] == verification["files_total"] and
            len(verification["hash_mismatches"]) == 0 and
            len(verification["missing_files"]) == 0 and
            verification["root_hash_valid"]
        )
        
        return integrity_valid, verification
    
    except Exception as e:
        logger.error(f"Bundle integrity verification failed: {e}")
        return False, verification


def recompute_decision(extracted_files: Dict[str, str]) -> Tuple[bool, Optional[DecisionResult], List[str]]:
    """
    Re-run decision algorithm on extracted data.
    
    Args:
        extracted_files: Mapping of archive paths to extracted file paths
        
    Returns:
        Tuple of (success, recomputed_decision_result, issues)
    """
    issues = []
    
    try:
        # Locate required files
        required_files = {
            "inputs/raw_data.csv": "raw CSV data",
            "inputs/specification.json": "specification",
            "outputs/decision.json": "original decision"
        }
        
        for archive_path, description in required_files.items():
            if archive_path not in extracted_files:
                issues.append(f"Missing {description}: {archive_path}")
        
        if issues:
            return False, None, issues
        
        # Load specification
        spec_path = Path(extracted_files["inputs/specification.json"])
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec_data = json.load(f)
        
        try:
            spec = SpecV1(**spec_data)
        except Exception as e:
            issues.append(f"Invalid specification format: {e}")
            return False, None, issues
        
        # Load and normalize raw data
        raw_csv_path = extracted_files["inputs/raw_data.csv"]
        try:
            raw_df, metadata = load_csv_with_metadata(raw_csv_path)
            
            # Use data requirements from spec for normalization
            data_req = spec.data_requirements
            normalized_df = normalize_temperature_data(
                raw_df,
                target_step_s=30.0,  # Default step size
                allowed_gaps_s=data_req.allowed_gaps_s,
                max_sample_period_s=data_req.max_sample_period_s
            )
            
        except Exception as e:
            issues.append(f"Data normalization failed: {e}")
            return False, None, issues
        
        # Re-run decision algorithm
        try:
            recomputed_decision = make_decision(normalized_df, spec)
            return True, recomputed_decision, issues
            
        except Exception as e:
            issues.append(f"Decision algorithm failed: {e}")
            return False, None, issues
    
    except Exception as e:
        issues.append(f"Decision recomputation failed: {e}")
        return False, None, issues


def compare_decisions(original: DecisionResult, recomputed: DecisionResult) -> Tuple[bool, List[str]]:
    """
    Compare original and recomputed decision results.
    
    Args:
        original: Original decision result from bundle
        recomputed: Recomputed decision result
        
    Returns:
        Tuple of (decisions_match, list_of_discrepancies)
    """
    discrepancies = []
    
    # Critical fields that must match exactly
    critical_fields = {
        'pass_': 'Pass/Fail status',
        'target_temp_C': 'Target temperature',
        'conservative_threshold_C': 'Conservative threshold',
        'required_hold_time_s': 'Required hold time'
    }
    
    for field, description in critical_fields.items():
        original_value = getattr(original, field)
        recomputed_value = getattr(recomputed, field)
        
        if original_value != recomputed_value:
            discrepancies.append(f"{description} mismatch: {original_value} != {recomputed_value}")
    
    # Numerical fields with tolerance
    numerical_tolerance = 0.1  # Allow small floating point differences
    numerical_fields = {
        'actual_hold_time_s': 'Actual hold time',
        'max_temp_C': 'Maximum temperature',
        'min_temp_C': 'Minimum temperature'
    }
    
    for field, description in numerical_fields.items():
        original_value = getattr(original, field)
        recomputed_value = getattr(recomputed, field)
        
        if abs(original_value - recomputed_value) > numerical_tolerance:
            discrepancies.append(f"{description} difference: {original_value:.2f} vs {recomputed_value:.2f}")
    
    # Reasons comparison (order may differ, but content should be similar)
    original_reasons = set(original.reasons)
    recomputed_reasons = set(recomputed.reasons)
    
    if original_reasons != recomputed_reasons:
        missing_reasons = original_reasons - recomputed_reasons
        extra_reasons = recomputed_reasons - original_reasons
        
        if missing_reasons:
            discrepancies.append(f"Missing reasons in recomputation: {list(missing_reasons)}")
        if extra_reasons:
            discrepancies.append(f"Extra reasons in recomputation: {list(extra_reasons)}")
    
    decisions_match = len(discrepancies) == 0
    return decisions_match, discrepancies


def verify_evidence_bundle(bundle_path: str, 
                          extract_dir: Optional[str] = None,
                          verify_decision: bool = True,
                          cleanup_temp: bool = True) -> VerificationReport:
    """
    Comprehensive evidence bundle verification.
    
    Performs complete verification including:
    1. Bundle integrity validation using SHA-256 checksums
    2. Decision algorithm re-computation and comparison
    3. Tamper detection and verification reporting
    
    Args:
        bundle_path: Path to evidence bundle (.zip file)
        extract_dir: Optional directory to extract files (uses temp if None)
        verify_decision: Whether to re-run decision algorithm
        cleanup_temp: Whether to clean up temporary files
        
    Returns:
        VerificationReport with comprehensive verification results
        
    Raises:
        VerificationError: If verification cannot be performed
    """
    report = VerificationReport()
    report.bundle_path = str(Path(bundle_path).absolute())
    temp_dir = None
    
    try:
        logger.info(f"Starting verification of evidence bundle: {bundle_path}")
        
        # Check if bundle exists
        if not Path(bundle_path).exists():
            report.add_issue(f"Evidence bundle not found: {bundle_path}")
            report.finalize()
            return report
        
        report.bundle_exists = True
        
        # Extract bundle to temporary directory
        try:
            if extract_dir:
                temp_dir = extract_dir
                # Manual extraction to specified directory
                temp_path = Path(temp_dir)
                temp_path.mkdir(parents=True, exist_ok=True)
                extracted_files = {}
                
                with zipfile.ZipFile(bundle_path, 'r') as zipf:
                    for archive_path in zipf.namelist():
                        extracted_file = temp_path / archive_path
                        extracted_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(extracted_file, 'wb') as f:
                            f.write(zipf.read(archive_path))
                        extracted_files[archive_path] = str(extracted_file)
            else:
                temp_dir, extracted_files = extract_bundle_to_temp(bundle_path)
                
        except VerificationError as e:
            report.add_issue(f"Bundle extraction failed: {e}")
            report.finalize()
            return report
        
        # Verify bundle integrity
        try:
            integrity_valid, integrity_details = verify_bundle_integrity(bundle_path, extracted_files)
            
            # Update report with integrity results
            report.manifest_found = integrity_details["manifest_found"]
            report.manifest_valid = integrity_details["manifest_valid"]
            report.root_hash = integrity_details["root_hash"]
            report.root_hash_valid = integrity_details["root_hash_valid"]
            report.files_total = integrity_details["files_total"]
            report.files_verified = integrity_details["files_verified"]
            report.missing_files = integrity_details["missing_files"]
            report.hash_mismatches = integrity_details["hash_mismatches"]
            report.extra_files = integrity_details["extra_files"]
            report.bundle_metadata = integrity_details["bundle_metadata"]
            
            # Add issues for integrity failures
            if not report.manifest_found:
                report.add_issue("Manifest file not found in bundle")
            elif not report.manifest_valid:
                report.add_issue("Manifest file is invalid or corrupted")
            
            if not report.root_hash_valid:
                report.add_issue("Root hash verification failed - bundle may be tampered")
            
            for missing_file in report.missing_files:
                report.add_issue(f"Missing file from bundle: {missing_file}")
            
            for mismatch in report.hash_mismatches:
                report.add_issue(f"Hash mismatch for {mismatch['file']}: expected {mismatch['expected'][:16]}... got {mismatch['actual'][:16]}...")
            
            for extra_file in report.extra_files:
                report.add_issue(f"Unexpected file in bundle: {extra_file}")
                
        except Exception as e:
            report.add_issue(f"Bundle integrity verification failed: {e}")
        
        # Re-run decision algorithm if requested and integrity is valid
        if verify_decision and report.manifest_found and report.manifest_valid:
            try:
                logger.info("Re-running decision algorithm on extracted data...")
                
                # Load original decision for comparison
                if "outputs/decision.json" in extracted_files:
                    decision_path = Path(extracted_files["outputs/decision.json"])
                    with open(decision_path, 'r', encoding='utf-8') as f:
                        original_decision_data = json.load(f)
                    
                    try:
                        report.original_decision = DecisionResult(**original_decision_data)
                    except Exception as e:
                        report.add_issue(f"Invalid original decision format: {e}")
                
                # Recompute decision
                success, recomputed_decision, decision_issues = recompute_decision(extracted_files)
                
                if success and recomputed_decision:
                    report.decision_recomputed = True
                    report.recomputed_decision = recomputed_decision
                    report.data_normalized = True
                    
                    # Compare decisions if we have both
                    if report.original_decision:
                        decisions_match, discrepancies = compare_decisions(
                            report.original_decision, 
                            recomputed_decision
                        )
                        
                        report.decision_matches = decisions_match
                        report.decision_discrepancies = discrepancies
                        
                        if not decisions_match:
                            for discrepancy in discrepancies:
                                report.add_issue(f"Decision discrepancy: {discrepancy}")
                        else:
                            logger.info("Decision algorithm results match original")
                    else:
                        report.add_issue("Cannot compare decisions - original decision not available")
                
                else:
                    report.add_issue("Decision recomputation failed")
                    for issue in decision_issues:
                        report.add_issue(f"Decision recomputation: {issue}")
                
            except Exception as e:
                report.add_issue(f"Decision verification failed: {e}")
        
        # Add warnings for non-critical issues
        if report.extra_files:
            report.add_issue("Bundle contains unexpected files", is_warning=True)
        
        # Finalize verification status
        report.finalize()
        
        logger.info(f"Verification completed - Status: {'VALID' if report.is_valid else 'INVALID'}")
        logger.info(f"Issues found: {len(report.issues)}, Warnings: {len(report.warnings)}")
        
        return report
    
    except Exception as e:
        logger.error(f"Verification process failed: {e}")
        report.add_issue(f"Verification process failed: {str(e)}")
        report.finalize()
        return report
    
    finally:
        # Cleanup temporary directory if requested
        if cleanup_temp and temp_dir and not extract_dir:
            try:
                import shutil
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temporary directory {temp_dir}: {e}")


def verify_bundle_quick(bundle_path: str) -> Dict[str, Any]:
    """
    Quick verification that only checks bundle integrity (no decision re-computation).
    
    Args:
        bundle_path: Path to evidence bundle
        
    Returns:
        Dictionary with quick verification results
    """
    try:
        report = verify_evidence_bundle(bundle_path, verify_decision=False)
        
        return {
            "valid": report.is_valid,
            "bundle_exists": report.bundle_exists,
            "manifest_found": report.manifest_found,
            "root_hash": report.root_hash,
            "root_hash_valid": report.root_hash_valid,
            "files_verified": report.files_verified,
            "files_total": report.files_total,
            "issues_count": len(report.issues),
            "warnings_count": len(report.warnings)
        }
    
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


# Usage example in comments:
"""
Example usage for ProofKit evidence bundle verification:

from core.verify import verify_evidence_bundle, verify_bundle_quick
from pathlib import Path

# Full verification with decision re-computation
report = verify_evidence_bundle("evidence.zip")

if report.is_valid:
    print(f"✓ Bundle verification PASSED")
    print(f"  Root hash: {report.root_hash[:16]}...")
    print(f"  Files verified: {report.files_verified}/{report.files_total}")
    print(f"  Decision matches: {report.decision_matches}")
else:
    print(f"✗ Bundle verification FAILED")
    print(f"  Issues: {len(report.issues)}")
    for issue in report.issues:
        print(f"    - {issue}")

# Quick verification (integrity only)
quick_result = verify_bundle_quick("evidence.zip")
print(f"Quick verification: {'PASS' if quick_result['valid'] else 'FAIL'}")

# Generate detailed report
print("\nDetailed Report:")
print(report)
"""