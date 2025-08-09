"""
ProofKit Audit Runner

Comprehensive audit framework that tests ProofKit against a battery of synthetic 
test cases across all supported industries. Validates decision correctness,
consistency, and edge case handling.

This module provides:
1. Systematic testing across industry fixtures
2. Decision algorithm invariant validation  
3. Performance benchmarking
4. Regression detection via output comparison

Example usage:
    python -m cli.audit_runner --industry powder --verbose
    python -m cli.audit_runner --all --save-results audit_results.json
"""

import typer
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import sys

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.pack import create_evidence_bundle
from core.verify import verify_evidence_bundle
from core.models import SpecV1
from core.types import safe_get_attr
from core.errors import RequiredSignalMissingError, DecisionError, ProofKitError, DataQualityError

app = typer.Typer(
    name="audit",
    help="ProofKit audit framework for systematic testing across industries",
    add_completion=False
)


@dataclass
class AuditTestCase:
    """Single audit test case with metadata."""
    industry: str
    test_type: str
    csv_path: str
    spec_path: str
    expected_result: Optional[str] = None  # PASS/FAIL/ERROR
    description: str = ""


@dataclass
class AuditResult:
    """Result of running a single audit test case."""
    test_case: AuditTestCase
    success: bool
    decision: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    decision_data: Optional[Dict[str, Any]] = None
    hash_signature: Optional[str] = None


@dataclass
class AuditSummary:
    """Summary of complete audit run."""
    timestamp: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    total_time_ms: float
    industries_tested: List[str]
    results: List[AuditResult]


def discover_test_fixtures(audit_dir: Path) -> List[AuditTestCase]:
    """
    Discover all test fixtures in the audit directory.
    
    Expected structure:
    audit/fixtures/{industry}/{test_type}.csv
    audit/fixtures/{industry}/{test_type}.json
    """
    fixtures = []
    audit_fixtures_dir = audit_dir / "fixtures"
    
    if not audit_fixtures_dir.exists():
        return fixtures
    
    # Map test types to expected results
    expected_results = {
        "pass": "PASS",
        "fail": "FAIL",
        "borderline": None,  # Could be either
        "missing_required": "ERROR",
        "gap": "ERROR", 
        "dup_ts": "ERROR",
        "tz_shift": None  # Should handle gracefully
    }
    
    test_descriptions = {
        "pass": "Clear passing case meeting all requirements",
        "fail": "Clear failing case not meeting hold time",
        "borderline": "Edge case near threshold boundaries",
        "missing_required": "Missing required sensors",
        "gap": "Data gaps exceeding allowed limits",
        "dup_ts": "Duplicate timestamp entries",
        "tz_shift": "Mixed timezone data"
    }
    
    for industry_dir in audit_fixtures_dir.iterdir():
        if industry_dir.is_dir():
            industry = industry_dir.name
            
            for csv_file in industry_dir.glob("*.csv"):
                test_type = csv_file.stem
                json_file = industry_dir / f"{test_type}.json"
                
                if json_file.exists():
                    fixtures.append(AuditTestCase(
                        industry=industry,
                        test_type=test_type,
                        csv_path=str(csv_file),
                        spec_path=str(json_file),
                        expected_result=expected_results.get(test_type),
                        description=test_descriptions.get(test_type, f"Test case: {test_type}")
                    ))
    
    return sorted(fixtures, key=lambda x: (x.industry, x.test_type))


def run_single_test(test_case: AuditTestCase, verbose: bool = False) -> AuditResult:
    """Run a single audit test case and return results."""
    start_time = time.time()
    
    try:
        if verbose:
            typer.echo(f"  Running {test_case.industry}/{test_case.test_type}...")
        
        # Load spec
        with open(test_case.spec_path, 'r') as f:
            spec = json.load(f)
        
        # Validate spec structure using Pydantic model
        try:
            spec_model = SpecV1(**spec)
        except Exception as e:
            if verbose:
                typer.echo(f"    Spec validation failed: {e}")
            return AuditResult(
                test_case=test_case,
                success=False,
                error_message=f"Invalid spec: {e}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        # Load and normalize CSV data
        try:
            df, metadata = load_csv_with_metadata(test_case.csv_path)
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0),
                industry=spec.get('industry')
            )
            if verbose:
                typer.echo(f"    Loaded {len(df)} rows, normalized to {len(normalized_df)}")
        except (DataQualityError, RequiredSignalMissingError) as e:
            if verbose:
                typer.echo(f"    Expected error during normalization: {type(e).__name__}: {e}")
            
            # If we expected an error, this is success
            success = (test_case.expected_result == "ERROR")
            
            if verbose and not success:
                typer.echo(f"    ERROR mismatch: expected={test_case.expected_result}, got=ERROR")
            
            return AuditResult(
                test_case=test_case,
                success=success,
                decision="ERROR",
                error_message=f"{type(e).__name__}: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            if verbose:
                typer.echo(f"    Normalization failed: {e}")
            return AuditResult(
                test_case=test_case,
                success=False,
                error_message=f"Normalization error: {e}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        # Make decision
        try:
            decision_result = make_decision(normalized_df, spec_model)
            # Use safe getter to handle both dict and attribute access patterns
            decision = safe_get_attr(decision_result, 'status', 'UNKNOWN')
            
            # Create hash signature for determinism testing
            # Convert to dict for JSON serialization if it's a Pydantic model
            if hasattr(decision_result, 'model_dump'):
                decision_dict = decision_result.model_dump(by_alias=True)
            else:
                decision_dict = decision_result
            decision_str = json.dumps(decision_dict, sort_keys=True, default=str)
            hash_signature = hashlib.sha256(decision_str.encode()).hexdigest()[:16]
            
            execution_time = (time.time() - start_time) * 1000
            
            if verbose:
                typer.echo(f"    Decision: {decision} ({execution_time:.1f}ms)")
                typer.echo(f"    Hash: {hash_signature}")
            
            # Determine if test passed based on expected result
            success = True
            if test_case.expected_result:
                success = (decision == test_case.expected_result)
                if verbose and not success:
                    typer.echo(f"    PASS/FAIL mismatch: expected={test_case.expected_result}, got={decision}")
                    
                    # Include metrics snippet for PASS/FAIL mismatches to aid diagnosis
                    metrics_parts = []
                    
                    # Add hold_secs if available
                    if hasattr(decision_result, 'actual_hold_time_s'):
                        hold_secs = getattr(decision_result, 'actual_hold_time_s', 0.0)
                        metrics_parts.append(f"hold_secs={hold_secs:.1f}")
                    
                    # Add Fo if available (truncate large floats)
                    if 'Fo' in decision_dict:
                        fo_val = decision_dict['Fo']
                        metrics_parts.append(f"Fo={fo_val:.2f}")
                    
                    # Add percent_in_range if available  
                    if 'percent_in_range' in decision_dict:
                        pct_val = decision_dict['percent_in_range']
                        metrics_parts.append(f"pct_in_range={pct_val:.1f}%")
                    
                    if metrics_parts:
                        typer.echo(f"    Metrics: {', '.join(metrics_parts)}")
            
            return AuditResult(
                test_case=test_case,
                success=success,
                decision=decision,
                execution_time_ms=execution_time,
                decision_data=decision_dict if hasattr(decision_result, 'model_dump') else decision_result,
                hash_signature=hash_signature
            )
            
        except (RequiredSignalMissingError, DecisionError, ProofKitError, DataQualityError) as e:
            if verbose:
                typer.echo(f"    Expected ProofKit error: {type(e).__name__}: {e}")
            
            # If we expected an error, this is success
            success = (test_case.expected_result == "ERROR")
            
            if verbose and not success:
                typer.echo(f"    ERROR mismatch: expected={test_case.expected_result}, got=ERROR")
            
            return AuditResult(
                test_case=test_case,
                success=success,
                decision="ERROR",
                error_message=f"{type(e).__name__}: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            if verbose:
                typer.echo(f"    Unexpected error: {type(e).__name__}: {e}")
            
            # Unexpected errors are only success if we expected ERROR
            success = (test_case.expected_result == "ERROR")
            
            if verbose and not success:
                typer.echo(f"    Unexpected ERROR: expected={test_case.expected_result}, got=ERROR (unexpected)")
            
            return AuditResult(
                test_case=test_case,
                success=success,
                decision="ERROR" if test_case.expected_result == "ERROR" else "UNKNOWN",
                error_message=f"Unexpected {type(e).__name__}: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
            
    except Exception as e:
        if verbose:
            typer.echo(f"    Top-level unexpected error: {type(e).__name__}: {e}")
        return AuditResult(
            test_case=test_case,
            success=False,
            error_message=f"Top-level {type(e).__name__}: {str(e)}",
            execution_time_ms=(time.time() - start_time) * 1000
        )


@app.command()
def run(
    industry: Optional[str] = typer.Option(None, "--industry", "-i", help="Run tests for specific industry"),
    test_type: Optional[str] = typer.Option(None, "--test-type", "-t", help="Run specific test type"),
    all_tests: bool = typer.Option(False, "--all", help="Run all available tests"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    save_results: Optional[Path] = typer.Option(None, "--save-results", help="Save detailed results to JSON file"),
    benchmark: bool = typer.Option(False, "--benchmark", help="Include performance benchmarking"),
    determinism_check: bool = typer.Option(False, "--determinism", help="Run each test multiple times to check for deterministic results"),
    compare_golden: bool = typer.Option(False, "--compare-golden", help="Compare results to golden hashes")
) -> None:
    """
    Run audit tests across ProofKit fixtures.
    
    This command discovers and executes test cases from the audit/fixtures directory,
    validating decision correctness and consistency across industries and edge cases.
    """
    # Find audit directory
    script_dir = Path(__file__).parent.parent
    audit_dir = script_dir / "audit"
    
    if not audit_dir.exists():
        typer.echo("Audit directory not found. Expected: audit/fixtures/{industry}/", err=True)
        raise typer.Exit(1)
    
    # Discover test fixtures
    typer.echo("Discovering audit test fixtures...")
    test_cases = discover_test_fixtures(audit_dir)
    
    if not test_cases:
        typer.echo("No test fixtures found in audit/fixtures/", err=True)
        raise typer.Exit(1)
    
    # Filter test cases
    if industry:
        test_cases = [tc for tc in test_cases if tc.industry == industry]
        if not test_cases:
            typer.echo(f"No test cases found for industry: {industry}", err=True)
            raise typer.Exit(1)
    
    if test_type:
        test_cases = [tc for tc in test_cases if tc.test_type == test_type]
        if not test_cases:
            typer.echo(f"No test cases found for test type: {test_type}", err=True)
            raise typer.Exit(1)
    
    if not all_tests and not industry and not test_type:
        typer.echo("Specify --industry, --test-type, or --all to run tests")
        raise typer.Exit(1)
    
    typer.echo(f"Found {len(test_cases)} test cases")
    
    if verbose:
        industries = sorted(set(tc.industry for tc in test_cases))
        test_types = sorted(set(tc.test_type for tc in test_cases))
        typer.echo(f"Industries: {', '.join(industries)}")
        typer.echo(f"Test types: {', '.join(test_types)}")
    
    # Run tests
    typer.echo(f"\\nRunning audit tests...")
    start_time = time.time()
    results = []
    
    for test_case in test_cases:
        if determinism_check:
            # Run test multiple times to check determinism
            typer.echo(f"\\nTesting determinism: {test_case.industry}/{test_case.test_type}")
            hashes = []
            for run in range(3):
                result = run_single_test(test_case, verbose=False)
                if result.hash_signature:
                    hashes.append(result.hash_signature)
                if run == 0:  # Keep first result
                    results.append(result)
            
            # Check if all hashes match
            if len(set(hashes)) > 1:
                typer.echo(f"  ⚠️  Non-deterministic results detected!")
                typer.echo(f"  Hashes: {hashes}")
            else:
                typer.echo(f"  ✓ Deterministic results confirmed")
        else:
            result = run_single_test(test_case, verbose)
            results.append(result)
    
    total_time = (time.time() - start_time) * 1000
    
    # Analyze results
    passed = len([r for r in results if r.success])
    failed = len([r for r in results if not r.success and not r.error_message])
    errors = len([r for r in results if r.error_message])
    
    # Golden hash comparison if requested
    golden_mismatches = 0
    if compare_golden:
        typer.echo(f"\nComparing to golden hashes...")
        for result in results:
            matches, error_msg = compare_to_golden(result, audit_dir)
            if not matches:
                golden_mismatches += 1
                if verbose:
                    typer.echo(f"  ❌ {result.test_case.industry}/{result.test_case.test_type}: {error_msg}")
        
        if golden_mismatches == 0:
            typer.echo(f"  ✅ All results match golden hashes")
        else:
            typer.echo(f"  ⚠️  {golden_mismatches} results differ from golden hashes")
    
    # Create summary
    summary = AuditSummary(
        timestamp=datetime.now().isoformat(),
        total_tests=len(results),
        passed_tests=passed,
        failed_tests=failed,
        error_tests=errors,
        total_time_ms=total_time,
        industries_tested=sorted(set(tc.industry for tc in test_cases)),
        results=results
    )
    
    # Display summary
    typer.echo(f"\\nAudit Results Summary:")
    typer.echo(f"  Total tests: {summary.total_tests}")
    typer.echo(f"  Passed: {summary.passed_tests} ✓")
    typer.echo(f"  Failed: {summary.failed_tests} ✗")
    typer.echo(f"  Errors: {summary.error_tests} ⚠️")
    typer.echo(f"  Total time: {summary.total_time_ms:.0f}ms")
    typer.echo(f"  Average per test: {summary.total_time_ms/len(results):.1f}ms")
    
    # Show failed/error tests
    if failed > 0 or errors > 0:
        typer.echo(f"\\nFailed/Error Details:")
        for result in results:
            if not result.success:
                status = "ERROR" if result.error_message else "FAIL"
                typer.echo(f"  {status}: {result.test_case.industry}/{result.test_case.test_type}")
                if result.error_message:
                    typer.echo(f"    {result.error_message}")
                elif result.decision != result.test_case.expected_result:
                    typer.echo(f"    Expected: {result.test_case.expected_result}, Got: {result.decision}")
    
    # Performance analysis
    if benchmark:
        typer.echo(f"\\nPerformance Analysis:")
        times = [r.execution_time_ms for r in results if r.execution_time_ms > 0]
        if times:
            typer.echo(f"  Min time: {min(times):.1f}ms")
            typer.echo(f"  Max time: {max(times):.1f}ms")
            typer.echo(f"  Median time: {sorted(times)[len(times)//2]:.1f}ms")
        
        # Find slowest tests
        slow_tests = sorted(results, key=lambda r: r.execution_time_ms, reverse=True)[:5]
        typer.echo(f"  Slowest tests:")
        for result in slow_tests:
            typer.echo(f"    {result.test_case.industry}/{result.test_case.test_type}: {result.execution_time_ms:.1f}ms")
    
    # Save results if requested
    if save_results:
        with open(save_results, 'w') as f:
            # Convert dataclasses to dict for JSON serialization
            summary_dict = asdict(summary)
            json.dump(summary_dict, f, indent=2, default=str)
        typer.echo(f"\\nDetailed results saved to: {save_results}")
    
    # Exit with appropriate code
    if failed > 0 or errors > 0:
        typer.echo(f"\\n❌ Audit completed with {failed + errors} failures")
        raise typer.Exit(1)
    elif compare_golden and golden_mismatches > 0:
        typer.echo(f"\\n⚠️  Audit tests passed but {golden_mismatches} golden hash mismatches found")
        raise typer.Exit(1)
    else:
        typer.echo(f"\\n✅ All audit tests passed")


@app.command()
def list_fixtures(
    industry: Optional[str] = typer.Option(None, "--industry", "-i", help="Filter by industry")
) -> None:
    """List all available audit test fixtures."""
    script_dir = Path(__file__).parent.parent
    audit_dir = script_dir / "audit"
    
    test_cases = discover_test_fixtures(audit_dir)
    
    if industry:
        test_cases = [tc for tc in test_cases if tc.industry == industry]
    
    if not test_cases:
        typer.echo("No test fixtures found")
        return
    
    typer.echo(f"Available audit fixtures:")
    current_industry = None
    
    for tc in test_cases:
        if tc.industry != current_industry:
            current_industry = tc.industry
            typer.echo(f"\\n{tc.industry.upper()}:")
        
        expected = tc.expected_result or "varies"
        typer.echo(f"  {tc.test_type:15} - {tc.description} (expect: {expected})")


@app.command() 
def validate_fixtures(
    industry: Optional[str] = typer.Option(None, "--industry", "-i", help="Validate specific industry"),
    fix_issues: bool = typer.Option(False, "--fix", help="Attempt to fix common issues")
) -> None:
    """Validate that all fixture files are properly structured."""
    script_dir = Path(__file__).parent.parent
    audit_dir = script_dir / "audit"
    
    test_cases = discover_test_fixtures(audit_dir)
    
    if industry:
        test_cases = [tc for tc in test_cases if tc.industry == industry]
    
    typer.echo(f"Validating {len(test_cases)} fixture pairs...")
    
    issues_found = 0
    
    for tc in test_cases:
        typer.echo(f"\\nValidating {tc.industry}/{tc.test_type}:")
        
        # Check file existence
        csv_path = Path(tc.csv_path)
        json_path = Path(tc.spec_path)
        
        if not csv_path.exists():
            typer.echo(f"  ✗ CSV file missing: {csv_path}")
            issues_found += 1
            continue
            
        if not json_path.exists():
            typer.echo(f"  ✗ JSON file missing: {json_path}")
            issues_found += 1
            continue
        
        # Validate CSV structure
        try:
            import pandas as pd
            df = pd.read_csv(csv_path)
            typer.echo(f"  ✓ CSV readable ({len(df)} rows, {len(df.columns)} columns)")
            
            # Check for timestamp column
            if 'timestamp' not in df.columns:
                typer.echo(f"  ✗ Missing 'timestamp' column")
                issues_found += 1
            
            # Check for sensor columns
            sensor_cols = [col for col in df.columns if col.startswith('sensor_')]
            typer.echo(f"  ✓ Found {len(sensor_cols)} sensor columns")
            
        except Exception as e:
            typer.echo(f"  ✗ CSV validation failed: {e}")
            issues_found += 1
        
        # Validate JSON structure
        try:
            with open(json_path) as f:
                spec = json.load(f)
            
            validate_spec(spec)
            typer.echo(f"  ✓ JSON spec is valid")
            
        except Exception as e:
            typer.echo(f"  ✗ JSON validation failed: {e}")
            issues_found += 1
    
    if issues_found == 0:
        typer.echo(f"\\n✅ All fixtures validated successfully")
    else:
        typer.echo(f"\\n❌ Found {issues_found} issues in fixtures")
        raise typer.Exit(1)


def validate_spec(spec: Dict[str, Any]) -> None:
    """Basic validation of spec structure."""
    required_fields = ['version', 'industry', 'job', 'spec']
    for field in required_fields:
        if field not in spec:
            raise ValueError(f"Missing required field: {field}")
    
    if 'target_temp_C' not in spec.get('spec', {}):
        raise ValueError("Missing target_temp_C in spec")


def load_golden_hash(audit_dir: Path, industry: str, test_type: str) -> Optional[str]:
    """Load golden hash for a test case."""
    golden_path = audit_dir / "golden" / industry / f"{test_type}.sha256"
    if golden_path.exists():
        return golden_path.read_text().strip()
    return None


def compare_to_golden(result: AuditResult, audit_dir: Path) -> Tuple[bool, Optional[str]]:
    """Compare result hash to golden hash."""
    if not result.hash_signature:
        return False, "No hash signature in result"
    
    golden_hash = load_golden_hash(audit_dir, result.test_case.industry, result.test_case.test_type)
    if not golden_hash:
        return False, "No golden hash found"
    
    if result.hash_signature == golden_hash:
        return True, None
    else:
        return False, f"Hash mismatch: expected {golden_hash}, got {result.hash_signature}"


@app.command()
def compare_golden(
    industry: Optional[str] = typer.Option(None, "--industry", "-i", help="Compare specific industry"),
    test_type: Optional[str] = typer.Option(None, "--test-type", "-t", help="Compare specific test type"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
) -> None:
    """Compare audit results to golden hashes."""
    script_dir = Path(__file__).parent.parent
    audit_dir = script_dir / "audit"
    
    if not (audit_dir / "golden").exists():
        typer.echo("Golden hash directory not found. Run with --save-golden first.", err=True)
        raise typer.Exit(1)
    
    test_cases = discover_test_fixtures(audit_dir)
    
    if industry:
        test_cases = [tc for tc in test_cases if tc.industry == industry]
    
    if test_type:
        test_cases = [tc for tc in test_cases if tc.test_type == test_type]
    
    if not test_cases:
        typer.echo("No test cases found", err=True)
        raise typer.Exit(1)
    
    typer.echo(f"Comparing {len(test_cases)} test cases to golden hashes...")
    
    mismatches = 0
    for test_case in test_cases:
        if verbose:
            typer.echo(f"\\nTesting {test_case.industry}/{test_case.test_type}...")
        
        # Run the test to get current hash
        result = run_single_test(test_case, verbose=False)
        
        # Compare to golden hash
        matches, error_msg = compare_to_golden(result, audit_dir)
        
        if matches:
            if verbose:
                typer.echo(f"  ✓ Hash matches golden")
        else:
            typer.echo(f"❌ {test_case.industry}/{test_case.test_type}: {error_msg}")
            mismatches += 1
    
    if mismatches == 0:
        typer.echo(f"\\n✅ All {len(test_cases)} test cases match golden hashes")
    else:
        typer.echo(f"\\n❌ {mismatches} test cases have hash mismatches")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()