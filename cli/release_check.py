"""
ProofKit Release Check CLI

Comprehensive release validation script that runs all tests, checks coverage,
validates examples, and generates release report. Designed for both CI and 
manual release validation workflows.

Usage:
    python -m cli.release_check --mode development  # Fast validation
    python -m cli.release_check --mode production   # Full validation
    python -m cli.release_check --golden-regen      # Regenerate golden files
"""

import typer
import subprocess
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib
import os
import importlib

# Configure logging 
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="release-check",
    help="ProofKit comprehensive release validation and testing suite",
    add_completion=False
)

@dataclass
class ValidationResult:
    """Result of a single validation step"""
    name: str
    passed: bool
    duration: float
    details: Dict[str, Any]
    warnings: List[str] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.errors is None:
            self.errors = []

@dataclass 
class ReleaseReport:
    """Complete release validation report"""
    timestamp: str
    mode: str
    version: Optional[str]
    commit_hash: Optional[str]
    overall_passed: bool
    validation_results: List[ValidationResult]
    performance_metrics: Dict[str, float]
    coverage_summary: Dict[str, Any]
    total_duration: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReleaseValidator:
    """Main release validation orchestrator"""
    
    def __init__(self, project_root: Path, mode: str = "development"):
        self.project_root = project_root
        self.mode = mode
        self.results: List[ValidationResult] = []
        self.start_time = time.time()
        
        # Add project root to path for imports
        sys.path.insert(0, str(project_root))
        
    def run_command(self, cmd: List[str], cwd: Optional[Path] = None, timeout: int = 300) -> Tuple[int, str, str]:
        """Run shell command and return exit code, stdout, stderr"""
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            duration = time.time() - start_time
            logger.debug(f"Command {' '.join(cmd)} completed in {duration:.2f}s with exit code {result.returncode}")
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"Command {' '.join(cmd)} timed out after {timeout}s")
            return -1, "", f"Command timed out after {timeout}s"
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Command {' '.join(cmd)} failed: {e}")
            return -1, "", str(e)
    
    def validate_dependencies(self) -> ValidationResult:
        """Validate all dependencies are installed and compatible"""
        start_time = time.time()
        
        try:
            # Check requirements.txt dependencies
            returncode, stdout, stderr = self.run_command([
                sys.executable, "-m", "pip", "check"
            ])
            
            details = {
                "pip_check_passed": returncode == 0,
                "pip_output": stdout,
                "pip_errors": stderr
            }
            
            warnings = []
            errors = []
            
            if returncode != 0:
                errors.append(f"pip check failed: {stderr}")
            
            # Check for critical dependencies
            critical_deps = ["fastapi", "pydantic", "pandas", "numpy", "typer", "pytest"]
            missing_deps = []
            
            for dep in critical_deps:
                try:
                    importlib.import_module(dep)
                except ImportError:
                    missing_deps.append(dep)
            
            if missing_deps:
                errors.append(f"Missing critical dependencies: {', '.join(missing_deps)}")
            
            details["missing_dependencies"] = missing_deps
            
            passed = returncode == 0 and not missing_deps
            
            return ValidationResult(
                name="Dependencies",
                passed=passed,
                duration=time.time() - start_time,
                details=details,
                warnings=warnings,
                errors=errors
            )
            
        except Exception as e:
            return ValidationResult(
                name="Dependencies", 
                passed=False,
                duration=time.time() - start_time,
                details={"error": str(e)},
                errors=[f"Dependency validation failed: {e}"]
            )
    
    def validate_code_quality(self) -> ValidationResult:
        """Run code quality checks (flake8, mypy, formatting)"""
        start_time = time.time()
        
        details = {}
        warnings = []
        errors = []
        passed = True
        
        # Run flake8 (syntax errors)
        returncode, stdout, stderr = self.run_command([
            "flake8", ".", "--count", "--select=E9,F63,F7,F82", "--show-source", "--statistics"
        ])
        details["flake8_syntax"] = {
            "returncode": returncode,
            "output": stdout,
            "errors": stderr
        }
        if returncode != 0:
            errors.append(f"flake8 syntax errors: {stderr}")
            passed = False
        
        # Run flake8 (complexity and style warnings)
        returncode, stdout, stderr = self.run_command([
            "flake8", ".", "--count", "--exit-zero", "--max-complexity=10", "--statistics"
        ])
        details["flake8_style"] = {
            "returncode": returncode,
            "output": stdout,
            "warnings": stderr
        }
        if returncode > 0:
            warnings.append(f"flake8 style warnings: {stdout}")
        
        # Run mypy if available
        mypy_available = shutil.which("mypy") is not None
        if mypy_available:
            returncode, stdout, stderr = self.run_command(["mypy", "."])
            details["mypy"] = {
                "returncode": returncode,
                "output": stdout,
                "errors": stderr
            }
            if returncode != 0:
                if self.mode == "production":
                    errors.append(f"mypy type checking failed: {stderr}")
                    passed = False
                else:
                    warnings.append(f"mypy type checking issues: {stderr}")
        else:
            warnings.append("mypy not available for type checking")
        
        # Check code formatting if black is available
        black_available = shutil.which("black") is not None
        if black_available:
            returncode, stdout, stderr = self.run_command(["black", "--check", "."])
            details["black"] = {
                "returncode": returncode,
                "output": stdout,
                "errors": stderr
            }
            if returncode != 0:
                warnings.append(f"Code formatting issues found: {stderr}")
        
        return ValidationResult(
            name="Code Quality",
            passed=passed,
            duration=time.time() - start_time,
            details=details,
            warnings=warnings,
            errors=errors
        )
    
    def validate_tests(self) -> ValidationResult:
        """Run test suite with coverage reporting"""
        start_time = time.time()
        
        details = {}
        warnings = []
        errors = []
        
        # Run tests with coverage
        test_cmd = [
            "python", "-m", "pytest",
            "-q",  # Quiet mode as requested
            "--cov=.",
            "--cov-report=xml",
            "--cov-report=html", 
            "--cov-report=term-missing",
            "--junitxml=pytest-results.xml",
            "-v"
        ]
        
        if self.mode == "development":
            test_cmd.extend(["--maxfail=5", "-x"])  # Fast fail for development
        
        returncode, stdout, stderr = self.run_command(test_cmd, timeout=600)
        
        details["pytest"] = {
            "returncode": returncode,
            "output": stdout,
            "errors": stderr
        }
        
        # Parse coverage from output
        coverage_info = self._parse_coverage_output(stdout)
        details["coverage"] = coverage_info
        
        passed = returncode == 0
        if not passed:
            errors.append(f"Tests failed: {stderr}")
        
        # Run coverage gate check
        if passed:  # Only check coverage if tests passed
            coverage_gate_cmd = ["python", "scripts/coverage_gate.py"]
            cov_returncode, cov_stdout, cov_stderr = self.run_command(coverage_gate_cmd, timeout=60)
            
            details["coverage_gate"] = {
                "returncode": cov_returncode,
                "output": cov_stdout,
                "errors": cov_stderr
            }
            
            if cov_returncode != 0:
                errors.append(f"Coverage gate failed: {cov_stderr}")
                passed = False
            else:
                # Extract coverage details from gate output for reporting
                if "Total Coverage" in cov_stdout:
                    for line in cov_stdout.split('\n'):
                        if "Total Coverage" in line:
                            try:
                                # Extract percentage from line like "Total Coverage      92.5%"
                                parts = line.split()
                                for part in parts:
                                    if part.endswith('%'):
                                        coverage_info["gate_total_coverage"] = float(part.rstrip('%'))
                                        break
                            except (ValueError, IndexError):
                                pass
        
        return ValidationResult(
            name="Tests",
            passed=passed,
            duration=time.time() - start_time,
            details=details,
            warnings=warnings,
            errors=errors
        )
    
    def validate_examples(self) -> ValidationResult:
        """Validate all example CSV/spec pairs work correctly"""
        start_time = time.time()
        
        details = {}
        warnings = []
        errors = []
        
        examples_dir = self.project_root / "examples"
        if not examples_dir.exists():
            return ValidationResult(
                name="Examples",
                passed=False,
                duration=time.time() - start_time,
                details={"error": "Examples directory not found"},
                errors=["Examples directory not found"]
            )
        
        # Find example CSV/spec pairs
        csv_files = list(examples_dir.glob("*.csv"))
        spec_files = list(examples_dir.glob("*.json"))
        
        details["csv_files_found"] = len(csv_files)
        details["spec_files_found"] = len(spec_files)
        
        validated_pairs = []
        failed_pairs = []
        
        # Test key example pairs
        test_pairs = [
            ("powder_coat_cure_successful_180c_10min_pass.csv", "powder_coat_cure_spec_standard_180c_10min.json"),
            ("powder_coat_cure_cumulative_hold_pass_170c_20min.csv", "powder_coat_cure_spec_cumulative_hold_170c_20min.json"),
            ("ok_run.csv", "spec_example.json")  # Basic example
        ]
        
        for csv_name, spec_name in test_pairs:
            csv_path = examples_dir / csv_name
            spec_path = examples_dir / spec_name
            
            if not csv_path.exists() or not spec_path.exists():
                warnings.append(f"Example pair not found: {csv_name}, {spec_name}")
                continue
            
            # Test the example using the normalize -> decide pipeline
            try:
                result = self._test_example_pair(csv_path, spec_path)
                if result["success"]:
                    validated_pairs.append({
                        "csv": csv_name,
                        "spec": spec_name,
                        "result": result
                    })
                else:
                    failed_pairs.append({
                        "csv": csv_name,
                        "spec": spec_name,
                        "error": result.get("error", "Unknown error")
                    })
                    errors.append(f"Example validation failed: {csv_name} + {spec_name}: {result.get('error')}")
            except Exception as e:
                failed_pairs.append({
                    "csv": csv_name,
                    "spec": spec_name,
                    "error": str(e)
                })
                errors.append(f"Example validation error: {csv_name} + {spec_name}: {e}")
        
        details["validated_pairs"] = validated_pairs
        details["failed_pairs"] = failed_pairs
        
        passed = len(failed_pairs) == 0
        
        return ValidationResult(
            name="Examples",
            passed=passed,
            duration=time.time() - start_time,
            details=details,
            warnings=warnings,
            errors=errors
        )
    
    def validate_golden_outputs(self) -> ValidationResult:
        """Validate golden outputs haven't changed unexpectedly"""
        start_time = time.time()
        
        details = {}
        warnings = []
        errors = []
        
        # Check if golden outputs exist
        golden_outputs = self.project_root / "examples" / "outputs"
        if not golden_outputs.exists():
            warnings.append("No golden outputs directory found")
            return ValidationResult(
                name="Golden Outputs",
                passed=True,  # Not critical if missing
                duration=time.time() - start_time,
                details={"warning": "Golden outputs directory not found"},
                warnings=warnings
            )
        
        # Get list of golden files
        golden_files = list(golden_outputs.glob("*"))
        details["golden_files_found"] = len(golden_files)
        
        # For each golden file, compute hash and compare sizes
        file_info = []
        for golden_file in golden_files:
            if golden_file.is_file():
                file_size = golden_file.stat().st_size
                
                # Read first 512 bytes for quick comparison
                try:
                    with open(golden_file, 'rb') as f:
                        header = f.read(512)
                        header_hash = hashlib.sha256(header).hexdigest()[:16]
                    
                    file_info.append({
                        "name": golden_file.name,
                        "size": file_size,
                        "header_hash": header_hash
                    })
                except Exception as e:
                    warnings.append(f"Could not read golden file {golden_file.name}: {e}")
        
        details["golden_files"] = file_info
        
        # In production mode, we could compare against stored expected values
        # For now, just ensure files exist and are readable
        passed = len(file_info) > 0
        
        return ValidationResult(
            name="Golden Outputs",
            passed=passed,
            duration=time.time() - start_time,
            details=details,
            warnings=warnings,
            errors=errors
        )
    
    def validate_performance(self) -> ValidationResult:
        """Run performance benchmarks and regression tests"""
        start_time = time.time()
        
        details = {}
        warnings = []
        errors = []
        
        # Basic performance test: normalize and decide on sample data
        try:
            # Use the ok_run.csv example for benchmarking
            examples_dir = self.project_root / "examples"
            csv_path = examples_dir / "ok_run.csv"
            spec_path = examples_dir / "spec_example.json"
            
            if csv_path.exists() and spec_path.exists():
                perf_result = self._benchmark_pipeline(csv_path, spec_path)
                details.update(perf_result)
                
                # Check performance thresholds (reasonable for single CSV processing)
                normalize_time = perf_result.get("normalize_time", 0)
                decide_time = perf_result.get("decide_time", 0)
                total_time = perf_result.get("total_time", 0)
                
                # Warning thresholds (in seconds)
                if normalize_time > 2.0:
                    warnings.append(f"Normalize operation slow: {normalize_time:.2f}s")
                if decide_time > 1.0:
                    warnings.append(f"Decision operation slow: {decide_time:.2f}s")
                if total_time > 5.0:
                    warnings.append(f"Total pipeline slow: {total_time:.2f}s")
                    
            else:
                warnings.append("Performance test skipped: example files not found")
                
        except Exception as e:
            errors.append(f"Performance validation failed: {e}")
        
        passed = len(errors) == 0
        
        return ValidationResult(
            name="Performance",
            passed=passed,
            duration=time.time() - start_time,
            details=details,
            warnings=warnings,
            errors=errors
        )
    
    def _parse_coverage_output(self, output: str) -> Dict[str, Any]:
        """Parse coverage information from pytest output"""
        coverage_info = {}
        
        # Look for coverage summary line like "TOTAL    1234   123    90%"
        lines = output.split('\n')
        for line in lines:
            if 'TOTAL' in line and '%' in line:
                parts = line.split()
                if len(parts) >= 4 and parts[-1].endswith('%'):
                    try:
                        coverage_info["total_coverage"] = float(parts[-1].rstrip('%'))
                    except ValueError:
                        pass
                break
        
        # Count test results
        coverage_info["tests_collected"] = output.count("PASSED") + output.count("FAILED") + output.count("SKIPPED")
        coverage_info["tests_passed"] = output.count("PASSED")
        coverage_info["tests_failed"] = output.count("FAILED")
        coverage_info["tests_skipped"] = output.count("SKIPPED")
        
        return coverage_info
    
    def _test_example_pair(self, csv_path: Path, spec_path: Path) -> Dict[str, Any]:
        """Test a single CSV/spec pair through the pipeline"""
        try:
            # Import core modules
            from core.normalize import normalize_csv_data
            from core.decide import make_decision
            
            # Load spec
            with open(spec_path, 'r') as f:
                spec = json.load(f)
            
            # Normalize CSV
            normalize_start = time.time()
            normalized_df, messages = normalize_csv_data(str(csv_path), spec)
            normalize_time = time.time() - normalize_start
            
            # Make decision  
            decide_start = time.time()
            decision = make_decision(normalized_df, spec)
            decide_time = time.time() - decide_start
            
            return {
                "success": True,
                "normalize_time": normalize_time,
                "decide_time": decide_time,
                "decision_result": decision.get("decision", "unknown"),
                "messages": messages[:3]  # First 3 messages only
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _benchmark_pipeline(self, csv_path: Path, spec_path: Path) -> Dict[str, Any]:
        """Benchmark the complete pipeline on sample data"""
        try:
            from core.normalize import normalize_csv_data
            from core.decide import make_decision
            
            # Load spec
            with open(spec_path, 'r') as f:
                spec = json.load(f)
            
            # Run multiple iterations for better timing
            iterations = 3
            normalize_times = []
            decide_times = []
            
            for i in range(iterations):
                # Normalize timing
                start = time.time()
                normalized_df, messages = normalize_csv_data(str(csv_path), spec)
                normalize_times.append(time.time() - start)
                
                # Decision timing
                start = time.time()  
                decision = make_decision(normalized_df, spec)
                decide_times.append(time.time() - start)
            
            return {
                "normalize_time": sum(normalize_times) / len(normalize_times),
                "decide_time": sum(decide_times) / len(decide_times),
                "total_time": sum(normalize_times) + sum(decide_times),
                "iterations": iterations,
                "csv_rows": len(normalized_df) if normalized_df is not None else 0
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "normalize_time": 0,
                "decide_time": 0,
                "total_time": 0
            }
    
    def run_all_validations(self) -> ReleaseReport:
        """Run all validation steps and generate comprehensive report"""
        logger.info(f"Starting release validation in {self.mode} mode...")
        
        validations = [
            ("Dependencies", self.validate_dependencies),
            ("Code Quality", self.validate_code_quality),
            ("Tests", self.validate_tests),
            ("Examples", self.validate_examples),
            ("Golden Outputs", self.validate_golden_outputs),
            ("Performance", self.validate_performance),
        ]
        
        for name, validation_func in validations:
            logger.info(f"Running {name} validation...")
            result = validation_func()
            self.results.append(result)
            
            if result.passed:
                logger.info(f"✓ {name} validation passed ({result.duration:.2f}s)")
            else:
                logger.error(f"✗ {name} validation failed ({result.duration:.2f}s)")
                for error in result.errors:
                    logger.error(f"  Error: {error}")
            
            if result.warnings:
                for warning in result.warnings:
                    logger.warning(f"  Warning: {warning}")
        
        # Calculate overall status
        overall_passed = all(result.passed for result in self.results)
        total_duration = time.time() - self.start_time
        
        # Extract performance metrics
        performance_metrics = {}
        for result in self.results:
            if result.name == "Performance":
                performance_metrics = result.details
                break
        
        # Extract coverage summary
        coverage_summary = {}
        for result in self.results:
            if result.name == "Tests":
                coverage_summary = result.details.get("coverage", {})
                break
        
        # Get version info
        version = self._get_version()
        commit_hash = self._get_commit_hash()
        
        return ReleaseReport(
            timestamp=datetime.now().isoformat(),
            mode=self.mode,
            version=version,
            commit_hash=commit_hash,
            overall_passed=overall_passed,
            validation_results=self.results,
            performance_metrics=performance_metrics,
            coverage_summary=coverage_summary,
            total_duration=total_duration
        )
    
    def _get_version(self) -> Optional[str]:
        """Get version from pyproject.toml or git tags"""
        try:
            # Try pyproject.toml first
            pyproject_path = self.project_root / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, 'r') as f:
                    content = f.read()
                    for line in content.split('\n'):
                        if line.strip().startswith('version ='):
                            return line.split('=')[1].strip().strip('"\'')
            
            # Try git tags
            returncode, stdout, stderr = self.run_command(["git", "describe", "--tags", "--exact-match"], timeout=10)
            if returncode == 0:
                return stdout.strip()
            
            # Try git describe
            returncode, stdout, stderr = self.run_command(["git", "describe", "--tags"], timeout=10)
            if returncode == 0:
                return stdout.strip()
            
            return None
            
        except Exception:
            return None
    
    def _get_commit_hash(self) -> Optional[str]:
        """Get current git commit hash"""
        try:
            returncode, stdout, stderr = self.run_command(["git", "rev-parse", "HEAD"], timeout=10)
            if returncode == 0:
                return stdout.strip()
            return None
        except Exception:
            return None


@app.command()
def validate(
    mode: str = typer.Option("development", "--mode", "-m", help="Validation mode: development or production"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", "-o", help="Save detailed report as JSON"),
    output_html: Optional[Path] = typer.Option(None, "--output-html", help="Save HTML report"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on first validation failure"),
    golden_regen: bool = typer.Option(False, "--golden-regen", help="Regenerate golden output files"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output with detailed information")
) -> None:
    """
    Run comprehensive release validation checks.
    
    Validates code quality, tests, examples, performance, and generates
    a detailed release report. Supports both development and production modes.
    """
    if mode not in ["development", "production"]:
        typer.echo("Mode must be 'development' or 'production'", err=True)
        raise typer.Exit(1)
    
    # Determine project root
    project_root = Path(__file__).parent.parent
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        typer.echo(f"Project root: {project_root}")
        typer.echo(f"Validation mode: {mode}")
    
    # Handle golden file regeneration
    if golden_regen:
        typer.echo("Regenerating golden output files...")
        _regenerate_golden_files(project_root)
        typer.echo("✓ Golden files regenerated")
        return
    
    # Create validator and run validations
    validator = ReleaseValidator(project_root, mode)
    
    try:
        report = validator.run_all_validations()
        
        # Display summary
        typer.echo(f"\n{'='*60}")
        typer.echo(f"ProofKit Release Validation Report")
        typer.echo(f"{'='*60}")
        typer.echo(f"Mode: {report.mode}")
        typer.echo(f"Timestamp: {report.timestamp}")
        if report.version:
            typer.echo(f"Version: {report.version}")
        if report.commit_hash:
            typer.echo(f"Commit: {report.commit_hash[:12]}...")
        typer.echo(f"Duration: {report.total_duration:.2f}s")
        typer.echo()
        
        # Validation results summary
        typer.echo("Validation Results:")
        for result in report.validation_results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            typer.echo(f"  {status:8} {result.name:15} ({result.duration:.2f}s)")
            
            if verbose:
                if result.warnings:
                    for warning in result.warnings:
                        typer.echo(f"           ⚠ {warning}")
                if result.errors:
                    for error in result.errors:
                        typer.echo(f"           ✗ {error}")
        
        typer.echo()
        
        # Coverage summary
        if report.coverage_summary:
            coverage = report.coverage_summary.get("total_coverage", 0)
            tests_passed = report.coverage_summary.get("tests_passed", 0)
            tests_total = report.coverage_summary.get("tests_collected", 0)
            
            typer.echo(f"Test Coverage: {coverage:.1f}%")
            typer.echo(f"Tests Passed: {tests_passed}/{tests_total}")
            typer.echo()
        
        # Performance summary
        if report.performance_metrics:
            normalize_time = report.performance_metrics.get("normalize_time", 0)
            decide_time = report.performance_metrics.get("decide_time", 0)
            
            typer.echo(f"Performance:")
            typer.echo(f"  Normalize: {normalize_time:.3f}s")
            typer.echo(f"  Decision:  {decide_time:.3f}s")
            typer.echo()
        
        # Overall result
        if report.overall_passed:
            typer.echo("🎉 RELEASE VALIDATION PASSED")
            typer.echo("All validations completed successfully!")
        else:
            typer.echo("❌ RELEASE VALIDATION FAILED") 
            failed_validations = [r.name for r in report.validation_results if not r.passed]
            typer.echo(f"Failed validations: {', '.join(failed_validations)}")
        
        # Save reports
        if output_json:
            with open(output_json, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            typer.echo(f"\nDetailed JSON report saved to: {output_json}")
        
        if output_html:
            _generate_html_report(report, output_html)
            typer.echo(f"HTML report saved to: {output_html}")
        
        # Exit with appropriate code
        if not report.overall_passed:
            raise typer.Exit(1)
            
    except KeyboardInterrupt:
        typer.echo("\nValidation interrupted by user", err=True)
        raise typer.Exit(130)
    except Exception as e:
        typer.echo(f"Validation failed with error: {e}", err=True)
        logger.exception("Validation error")
        raise typer.Exit(1)


def _regenerate_golden_files(project_root: Path) -> None:
    """Regenerate golden output files from current examples"""
    try:
        # Import required modules
        sys.path.insert(0, str(project_root))
        from core.normalize import normalize_csv_data
        from core.decide import make_decision
        from core.plot import create_proof_plot
        from core.render_pdf import create_proof_pdf
        
        examples_dir = project_root / "examples"
        outputs_dir = examples_dir / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        
        # Golden file test cases
        test_cases = [
            {
                "csv": "powder_coat_cure_successful_180c_10min_pass.csv",
                "spec": "powder_coat_cure_spec_standard_180c_10min.json",
                "prefix": "proof_pass"
            },
            {
                "csv": "powder_coat_cure_insufficient_hold_time_fail.csv", 
                "spec": "powder_coat_cure_spec_standard_180c_10min.json",
                "prefix": "proof_fail_short_hold"
            }
        ]
        
        for case in test_cases:
            csv_path = examples_dir / case["csv"]
            spec_path = examples_dir / case["spec"]
            
            if not csv_path.exists() or not spec_path.exists():
                continue
            
            # Load spec
            with open(spec_path, 'r') as f:
                spec = json.load(f)
            
            # Process pipeline
            normalized_df, messages = normalize_csv_data(str(csv_path), spec)
            decision = make_decision(normalized_df, spec)
            
            # Save decision JSON
            decision_path = outputs_dir / f"decision_{case['prefix']}.json"
            with open(decision_path, 'w') as f:
                json.dump(decision, f, indent=2)
            
            # Create and save plot
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                plot_path = tmp.name
            
            create_proof_plot(normalized_df, spec, decision, plot_path)
            
            # Move to outputs
            final_plot_path = outputs_dir / f"proof_plot_{case['prefix']}.png"
            shutil.move(plot_path, final_plot_path)
            
            # Create and save PDF
            pdf_path = outputs_dir / f"proof_{case['prefix']}.pdf"
            create_proof_pdf(
                normalized_df, spec, decision, 
                str(final_plot_path), str(pdf_path)
            )
            
    except Exception as e:
        typer.echo(f"Failed to regenerate golden files: {e}", err=True)
        raise


def _generate_html_report(report: ReleaseReport, output_path: Path) -> None:
    """Generate HTML report from release validation results"""
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ProofKit Release Validation Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .header { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
            .pass { color: #28a745; }
            .fail { color: #dc3545; }
            .warning { color: #ffc107; }
            .validation-item { margin: 10px 0; padding: 10px; border-left: 4px solid #ddd; }
            .validation-item.pass { border-color: #28a745; }
            .validation-item.fail { border-color: #dc3545; }
            .details { background: #f8f9fa; padding: 10px; margin: 10px 0; font-family: monospace; font-size: 12px; }
            table { width: 100%; border-collapse: collapse; margin: 20px 0; }
            th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>ProofKit Release Validation Report</h1>
            <p><strong>Mode:</strong> {mode}</p>
            <p><strong>Timestamp:</strong> {timestamp}</p>
            <p><strong>Version:</strong> {version}</p>
            <p><strong>Commit:</strong> {commit_hash}</p>
            <p><strong>Duration:</strong> {total_duration:.2f}s</p>
            <p><strong>Overall Result:</strong> 
                <span class="{overall_class}">{overall_result}</span>
            </p>
        </div>
        
        <h2>Validation Results</h2>
        {validation_results}
        
        <h2>Test Coverage Summary</h2>
        {coverage_table}
        
        <h2>Performance Metrics</h2>
        {performance_table}
        
    </body>
    </html>
    """
    
    # Build validation results HTML
    validation_html = ""
    for result in report.validation_results:
        css_class = "pass" if result.passed else "fail"
        status = "✓ PASS" if result.passed else "✗ FAIL"
        
        validation_html += f'''
        <div class="validation-item {css_class}">
            <h3>{result.name} - {status} ({result.duration:.2f}s)</h3>
        '''
        
        if result.warnings:
            validation_html += "<h4>Warnings:</h4><ul>"
            for warning in result.warnings:
                validation_html += f"<li class='warning'>{warning}</li>"
            validation_html += "</ul>"
        
        if result.errors:
            validation_html += "<h4>Errors:</h4><ul>"
            for error in result.errors:
                validation_html += f"<li class='fail'>{error}</li>"
            validation_html += "</ul>"
        
        validation_html += "</div>"
    
    # Build coverage table
    coverage_html = "<table><tr><th>Metric</th><th>Value</th></tr>"
    for key, value in report.coverage_summary.items():
        coverage_html += f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>"
    coverage_html += "</table>"
    
    # Build performance table
    performance_html = "<table><tr><th>Metric</th><th>Value</th></tr>"
    for key, value in report.performance_metrics.items():
        if isinstance(value, float):
            value_str = f"{value:.3f}s" if "time" in key else str(value)
        else:
            value_str = str(value)
        performance_html += f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value_str}</td></tr>"
    performance_html += "</table>"
    
    # Fill template
    html_content = html_template.format(
        mode=report.mode,
        timestamp=report.timestamp,
        version=report.version or "Unknown",
        commit_hash=report.commit_hash[:12] + "..." if report.commit_hash else "Unknown",
        total_duration=report.total_duration,
        overall_class="pass" if report.overall_passed else "fail",
        overall_result="PASSED" if report.overall_passed else "FAILED",
        validation_results=validation_html,
        coverage_table=coverage_html,
        performance_table=performance_html
    )
    
    with open(output_path, 'w') as f:
        f.write(html_content)


if __name__ == "__main__":
    app()