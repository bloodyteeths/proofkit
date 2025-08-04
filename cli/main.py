"""
ProofKit CLI Main Module

Command-line interface for ProofKit using Typer.
Provides granular control over the proof generation pipeline.
"""

import typer
from pathlib import Path
from typing import Optional
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="proofkit",
    help="ProofKit - Powder-coat cure process validation and proof generation",
    add_completion=False
)


@app.command()
def pack(
    raw_csv: Path = typer.Option(..., "--raw-csv", help="Path to raw CSV data file"),
    spec_json: Path = typer.Option(..., "--spec", help="Path to specification JSON file"),
    normalized_csv: Path = typer.Option(..., "--normalized", help="Path to normalized CSV data"),
    decision_json: Path = typer.Option(..., "--decision", help="Path to decision JSON file"),
    proof_pdf: Path = typer.Option(..., "--proof", help="Path to proof PDF file"),
    plot_png: Path = typer.Option(..., "--plot", help="Path to plot PNG file"),
    output: Path = typer.Option("evidence.zip", "--output", "-o", help="Output evidence bundle path"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Job identifier for metadata"),
    deterministic: bool = typer.Option(False, "--deterministic", help="Create deterministic bundle (for testing)")
) -> None:
    """
    Create tamper-evident evidence bundle from all proof components.
    
    Bundles all inputs and outputs into a ZIP archive with integrity manifest
    containing SHA-256 hashes for each file and a root hash for verification.
    """
    try:
        # Import pack module
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.pack import create_evidence_bundle
        
        # Validate input files
        missing_files = []
        for file_path, name in [
            (raw_csv, "Raw CSV"),
            (spec_json, "Spec JSON"),
            (normalized_csv, "Normalized CSV"),
            (decision_json, "Decision JSON"),
            (proof_pdf, "Proof PDF"),
            (plot_png, "Plot PNG")
        ]:
            if not file_path.exists():
                missing_files.append(f"{name}: {file_path}")
        
        if missing_files:
            typer.echo("Missing required files:", err=True)
            for missing in missing_files:
                typer.echo(f"  - {missing}", err=True)
            raise typer.Exit(1)
        
        typer.echo("Creating evidence bundle...")
        typer.echo(f"  Raw CSV: {raw_csv}")
        typer.echo(f"  Spec JSON: {spec_json}")
        typer.echo(f"  Normalized CSV: {normalized_csv}")
        typer.echo(f"  Decision JSON: {decision_json}")
        typer.echo(f"  Proof PDF: {proof_pdf}")
        typer.echo(f"  Plot PNG: {plot_png}")
        typer.echo(f"  Output: {output}")
        
        # Create evidence bundle
        result_path = create_evidence_bundle(
            raw_csv_path=str(raw_csv),
            spec_json_path=str(spec_json),
            normalized_csv_path=str(normalized_csv),
            decision_json_path=str(decision_json),
            proof_pdf_path=str(proof_pdf),
            plot_png_path=str(plot_png),
            output_path=str(output),
            job_id=job_id,
            deterministic=deterministic
        )
        
        bundle_size = Path(result_path).stat().st_size
        typer.echo(f"✓ Evidence bundle created successfully")
        typer.echo(f"  Path: {result_path}")
        typer.echo(f"  Size: {bundle_size:,} bytes")
        
        if job_id:
            typer.echo(f"  Job ID: {job_id}")
        
        if deterministic:
            typer.echo("  Mode: Deterministic (fixed timestamps)")
        
    except Exception as e:
        typer.echo(f"Failed to create evidence bundle: {e}", err=True)
        logger.exception("Evidence bundle creation failed")
        raise typer.Exit(1)


@app.command()
def verify(
    bundle: Path = typer.Argument(..., help="Path to evidence bundle (evidence.zip)"),
    extract_dir: Optional[Path] = typer.Option(None, "--extract-to", help="Directory to extract files (temp if not specified)"),
    quick: bool = typer.Option(False, "--quick", help="Quick verification (integrity only, no decision re-computation)"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Save detailed report as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output with detailed information")
) -> None:
    """
    Comprehensively verify evidence bundle integrity and decision validity.
    
    Performs complete verification including:
    - Bundle integrity validation using SHA-256 checksums
    - Decision algorithm re-computation and comparison (unless --quick)
    - Tamper detection and verification reporting
    """
    try:
        # Import verify module
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.verify import verify_evidence_bundle, verify_bundle_quick
        
        if not bundle.exists():
            typer.echo(f"Evidence bundle not found: {bundle}", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"Verifying evidence bundle: {bundle}")
        
        if quick:
            typer.echo("Mode: Quick verification (integrity only)")
            verification = verify_bundle_quick(str(bundle))
            
            if 'error' in verification:
                typer.echo(f"✗ Verification error: {verification['error']}", err=True)
                raise typer.Exit(1)
            
            typer.echo(f"Bundle exists: {'✓' if verification['bundle_exists'] else '✗'}")
            typer.echo(f"Manifest found: {'✓' if verification['manifest_found'] else '✗'}")
            typer.echo(f"Files verified: {verification['files_verified']}/{verification['files_total']}")
            typer.echo(f"Root hash valid: {'✓' if verification['root_hash_valid'] else '✗'}")
            typer.echo(f"Issues: {verification['issues_count']}")
            typer.echo(f"Warnings: {verification['warnings_count']}")
            
            if verification['valid']:
                typer.echo("\n✓ Quick verification PASSED")
            else:
                typer.echo("\n✗ Quick verification FAILED")
                raise typer.Exit(1)
        else:
            typer.echo("Mode: Full verification (integrity + decision validation)")
            
            # Perform comprehensive verification
            report = verify_evidence_bundle(
                str(bundle), 
                extract_dir=str(extract_dir) if extract_dir else None,
                verify_decision=True,
                cleanup_temp=extract_dir is None  # Only cleanup if using temp dir
            )
            
            # Display results
            typer.echo(f"\nBundle Integrity:")
            typer.echo(f"  Manifest found: {'✓' if report.manifest_found else '✗'}")
            typer.echo(f"  Files verified: {report.files_verified}/{report.files_total}")
            
            if report.root_hash:
                typer.echo(f"  Root hash: {report.root_hash[:16]}...")
                typer.echo(f"  Root hash valid: {'✓' if report.root_hash_valid else '✗'}")
            
            if report.decision_recomputed:
                typer.echo(f"\nDecision Verification:")
                typer.echo(f"  Algorithm re-run: {'✓' if report.decision_recomputed else '✗'}")
                typer.echo(f"  Decision matches: {'✓' if report.decision_matches else '✗'}")
                if report.decision_discrepancies:
                    typer.echo(f"  Discrepancies: {len(report.decision_discrepancies)}")
            
            # Show issues and warnings
            if report.issues:
                typer.echo(f"\nIssues ({len(report.issues)}):")
                for issue in report.issues:
                    typer.echo(f"  ✗ {issue}")
            
            if report.warnings:
                typer.echo(f"\nWarnings ({len(report.warnings)}):")
                for warning in report.warnings:
                    typer.echo(f"  ⚠ {warning}")
            
            # Verbose output
            if verbose:
                typer.echo(f"\nDetailed Information:")
                if report.bundle_metadata:
                    typer.echo(f"  Bundle metadata: {report.bundle_metadata}")
                if report.missing_files:
                    typer.echo(f"  Missing files: {report.missing_files}")
                if report.hash_mismatches:
                    typer.echo(f"  Hash mismatches:")
                    for mismatch in report.hash_mismatches:
                        typer.echo(f"    {mismatch['file']}: expected {mismatch['expected'][:16]}..., got {mismatch['actual'][:16]}...")
                if report.decision_discrepancies:
                    typer.echo(f"  Decision discrepancies:")
                    for discrepancy in report.decision_discrepancies:
                        typer.echo(f"    - {discrepancy}")
            
            # Save JSON report if requested
            if output_json:
                import json
                with open(output_json, 'w') as f:
                    json.dump(report.to_dict(), f, indent=2)
                typer.echo(f"\nDetailed report saved to: {output_json}")
            
            # Final result
            if report.is_valid:
                typer.echo("\n✓ Evidence bundle verification PASSED")
                typer.echo("  Bundle integrity confirmed")
                if report.decision_recomputed:
                    typer.echo("  Decision algorithm results verified")
            else:
                typer.echo("\n✗ Evidence bundle verification FAILED")
                typer.echo(f"  Found {len(report.issues)} issues")
                if report.decision_recomputed and not report.decision_matches:
                    typer.echo("  Decision results do not match")
                raise typer.Exit(1)
        
    except Exception as e:
        typer.echo(f"Failed to verify evidence bundle: {e}", err=True)
        logger.exception("Evidence bundle verification failed")
        raise typer.Exit(1)


@app.command()
def extract(
    bundle: Path = typer.Argument(..., help="Path to evidence bundle (evidence.zip)"),
    output_dir: Path = typer.Option("extracted", "--output", "-o", help="Directory to extract files to")
) -> None:
    """
    Extract evidence bundle contents for inspection.
    
    Extracts all files from the evidence bundle to a directory while
    preserving the internal file organization.
    """
    try:
        # Import pack module
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.pack import extract_evidence_bundle
        
        if not bundle.exists():
            typer.echo(f"Evidence bundle not found: {bundle}", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"Extracting evidence bundle: {bundle}")
        typer.echo(f"Output directory: {output_dir}")
        
        # Extract bundle
        extracted_files = extract_evidence_bundle(str(bundle), str(output_dir))
        
        typer.echo(f"✓ Extracted {len(extracted_files)} files:")
        for archive_path, file_path in extracted_files.items():
            typer.echo(f"  {archive_path} -> {file_path}")
        
    except Exception as e:
        typer.echo(f"Failed to extract evidence bundle: {e}", err=True)
        logger.exception("Evidence bundle extraction failed")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()