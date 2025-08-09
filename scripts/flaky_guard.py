#!/usr/bin/env python3
"""
Flaky Test Guard - Resilient test runner with retry logic for ProofKit CI/CD.

This script runs pytest with intelligent retry logic for flaky tests,
ensuring CI stability while maintaining test reliability standards.

Features:
- Automatic retry for failed tests (up to MAX_RETRIES)
- Detailed failure analysis and reporting
- Integration with existing pytest configuration
- Support for test isolation and cleanup
- Flaky test detection and reporting
"""

import os
import sys
import json
import time
import subprocess
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TestResult:
    """Test execution result metadata."""
    name: str
    status: str  # passed, failed, error, skipped
    duration: float
    attempt: int
    error_message: Optional[str] = None


@dataclass
class TestRun:
    """Complete test run results."""
    timestamp: datetime
    total_tests: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float
    results: List[TestResult]


class FlakyGuard:
    """Intelligent test runner with retry logic for flaky tests."""
    
    def __init__(self):
        self.max_retries = int(os.environ.get('MAX_RETRIES', '2'))
        self.pytest_args = os.environ.get('PYTEST_ARGS', '--tb=short')
        self.verbose = os.environ.get('FLAKY_GUARD_VERBOSE', 'false').lower() == 'true'
        self.storage_dir = Path('storage')
        self.test_history = []
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(exist_ok=True)
    
    def log(self, message: str, level: str = 'INFO') -> None:
        """Log message with timestamp and level."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        if self.verbose or level in ['ERROR', 'WARNING']:
            print(f"[{timestamp}] {level}: {message}", flush=True)
    
    def cleanup_test_artifacts(self) -> None:
        """Clean up test artifacts before running tests."""
        self.log("Cleaning up test artifacts...")
        
        # Remove test storage files
        test_storage = self.storage_dir / 'test'
        if test_storage.exists():
            import shutil
            shutil.rmtree(test_storage)
        
        # Clean pytest cache
        pytest_cache = Path('.pytest_cache')
        if pytest_cache.exists():
            import shutil
            shutil.rmtree(pytest_cache)
        
        # Remove coverage files
        for cov_file in ['.coverage', 'coverage.xml']:
            if Path(cov_file).exists():
                Path(cov_file).unlink()
    
    def run_pytest(self, additional_args: List[str] = None) -> Tuple[int, str, Dict]:
        """Run pytest and return (exit_code, output, parsed_results)."""
        args = ['python', '-m', 'pytest']
        
        # Add configured pytest args
        if self.pytest_args:
            args.extend(self.pytest_args.split())
        
        # Add additional args if provided
        if additional_args:
            args.extend(additional_args)
        
        # Always add JSON report for result parsing
        json_report = self.storage_dir / 'pytest_report.json'
        args.extend(['--json-report', f'--json-report-file={json_report}'])
        
        self.log(f"Running: {' '.join(args)}")
        
        start_time = time.time()
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test run
            )
            duration = time.time() - start_time
            
            # Parse JSON report if available
            parsed_results = {}
            if json_report.exists():
                try:
                    with open(json_report, 'r') as f:
                        parsed_results = json.load(f)
                except json.JSONDecodeError as e:
                    self.log(f"Failed to parse pytest JSON report: {e}", 'WARNING')
            
            return result.returncode, result.stdout + result.stderr, parsed_results
            
        except subprocess.TimeoutExpired:
            self.log("Test execution timed out", 'ERROR')
            return 124, "Test execution timed out", {}
    
    def parse_test_results(self, pytest_output: str, parsed_json: Dict) -> TestRun:
        """Parse pytest output and JSON report to extract test results."""
        results = []
        
        # Extract from JSON report if available
        if parsed_json and 'tests' in parsed_json:
            for test in parsed_json['tests']:
                result = TestResult(
                    name=test.get('nodeid', 'unknown'),
                    status=test.get('outcome', 'unknown'),
                    duration=test.get('duration', 0.0),
                    attempt=1,  # Will be updated during retries
                    error_message=test.get('call', {}).get('longrepr', None) if test.get('outcome') in ['failed', 'error'] else None
                )
                results.append(result)
        
        # Extract summary from JSON
        summary = parsed_json.get('summary', {})
        
        return TestRun(
            timestamp=datetime.now(),
            total_tests=summary.get('total', 0),
            passed=summary.get('passed', 0),
            failed=summary.get('failed', 0),
            errors=summary.get('error', 0),
            skipped=summary.get('skipped', 0),
            duration=parsed_json.get('duration', 0.0),
            results=results
        )
    
    def identify_flaky_tests(self, failed_tests: List[TestResult]) -> List[str]:
        """Identify tests that might be flaky and worth retrying."""
        # Tests to always retry (known to be environment-sensitive)
        always_retry_patterns = [
            'test_file_cleanup',
            'test_concurrent_',
            'test_timeout_',
            'test_pdf_generation',  # PDF generation can be flaky
            'test_plot_',           # Matplotlib plotting can be flaky
            'test_timestamp_',      # Timing-sensitive tests
        ]
        
        # Tests to never retry (deterministic failures)
        never_retry_patterns = [
            'test_schema_validation',
            'test_json_parsing',
            'test_csv_format',
            'test_spec_validation',
        ]
        
        flaky_candidates = []
        
        for test in failed_tests:
            test_name = test.name
            
            # Skip if in never retry list
            if any(pattern in test_name for pattern in never_retry_patterns):
                self.log(f"Skipping retry for deterministic test: {test_name}")
                continue
            
            # Always retry certain patterns
            if any(pattern in test_name for pattern in always_retry_patterns):
                flaky_candidates.append(test_name)
                continue
            
            # Retry based on error message analysis
            if test.error_message:
                error = test.error_message.lower()
                
                # Retry for common flaky error patterns
                flaky_indicators = [
                    'timeout',
                    'connection refused',
                    'file not found',
                    'permission denied',
                    'resource temporarily unavailable',
                    'broken pipe',
                    'address already in use',
                    'no space left on device',
                ]
                
                if any(indicator in error for indicator in flaky_indicators):
                    flaky_candidates.append(test_name)
        
        return flaky_candidates
    
    def retry_failed_tests(self, failed_tests: List[str], attempt: int) -> Tuple[int, TestRun]:
        """Retry specific failed tests."""
        if not failed_tests:
            return 0, None
        
        self.log(f"Retrying {len(failed_tests)} tests (attempt {attempt + 1}/{self.max_retries + 1})")
        
        # Clean up before retry
        self.cleanup_test_artifacts()
        
        # Run only the failed tests
        retry_args = failed_tests  # pytest accepts test node IDs directly
        
        exit_code, output, parsed_results = self.run_pytest(retry_args)
        test_run = self.parse_test_results(output, parsed_results)
        
        # Update attempt numbers for tracking
        for result in test_run.results:
            result.attempt = attempt + 1
        
        return exit_code, test_run
    
    def generate_report(self, all_runs: List[TestRun]) -> str:
        """Generate comprehensive test execution report."""
        if not all_runs:
            return "No test runs completed."
        
        final_run = all_runs[-1]
        
        report = [
            "=== FLAKY GUARD TEST EXECUTION REPORT ===",
            f"Timestamp: {final_run.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total test runs: {len(all_runs)}",
            f"Max retries configured: {self.max_retries}",
            "",
            "=== FINAL RESULTS ===",
            f"Total tests: {final_run.total_tests}",
            f"Passed: {final_run.passed}",
            f"Failed: {final_run.failed}",
            f"Errors: {final_run.errors}",
            f"Skipped: {final_run.skipped}",
            f"Duration: {final_run.duration:.2f}s",
            ""
        ]
        
        # Analyze retry patterns
        if len(all_runs) > 1:
            report.append("=== RETRY ANALYSIS ===")
            
            flaky_tests = {}
            for run_idx, run in enumerate(all_runs):
                for result in run.results:
                    if result.status in ['failed', 'error']:
                        if result.name not in flaky_tests:
                            flaky_tests[result.name] = []
                        flaky_tests[result.name].append((run_idx + 1, result.status))
            
            # Show tests that failed multiple times
            persistent_failures = []
            recovered_tests = []
            
            for test_name, failures in flaky_tests.items():
                if len(failures) == len(all_runs):  # Failed in all runs
                    persistent_failures.append(test_name)
                else:
                    recovered_tests.append(test_name)
            
            if recovered_tests:
                report.append(f"Tests that recovered after retry: {len(recovered_tests)}")
                for test in recovered_tests[:5]:  # Show first 5
                    report.append(f"  - {test}")
                if len(recovered_tests) > 5:
                    report.append(f"  ... and {len(recovered_tests) - 5} more")
                report.append("")
            
            if persistent_failures:
                report.append(f"Tests that failed consistently: {len(persistent_failures)}")
                for test in persistent_failures:
                    report.append(f"  - {test}")
                report.append("")
        
        # Show final failed tests with error details
        if final_run.failed > 0 or final_run.errors > 0:
            report.append("=== FINAL FAILURES ===")
            for result in final_run.results:
                if result.status in ['failed', 'error']:
                    report.append(f"❌ {result.name}")
                    if result.error_message:
                        # Show first few lines of error
                        error_lines = result.error_message.split('\n')[:3]
                        for line in error_lines:
                            report.append(f"   {line.strip()}")
                    report.append("")
        
        return '\n'.join(report)
    
    def save_report(self, report: str) -> None:
        """Save test execution report to file."""
        report_file = self.storage_dir / 'flaky_guard_report.txt'
        with open(report_file, 'w') as f:
            f.write(report)
        self.log(f"Test report saved to {report_file}")
    
    def run(self) -> int:
        """Main execution method with retry logic."""
        self.log("=== STARTING FLAKY GUARD TEST EXECUTION ===")
        
        # Initial cleanup
        self.cleanup_test_artifacts()
        
        all_runs = []
        
        # Initial test run
        self.log("Running initial test suite...")
        exit_code, output, parsed_results = self.run_pytest()
        initial_run = self.parse_test_results(output, parsed_results)
        all_runs.append(initial_run)
        
        self.log(f"Initial run completed: {initial_run.passed} passed, {initial_run.failed} failed, {initial_run.errors} errors")
        
        # If all tests passed, we're done
        if exit_code == 0:
            self.log("✅ All tests passed on first attempt!")
            final_report = self.generate_report(all_runs)
            print(final_report)
            self.save_report(final_report)
            return 0
        
        # Identify failed tests that might be worth retrying
        failed_tests = [r for r in initial_run.results if r.status in ['failed', 'error']]
        flaky_candidates = self.identify_flaky_tests(failed_tests)
        
        if not flaky_candidates:
            self.log("No flaky test candidates identified. Reporting failure.")
            final_report = self.generate_report(all_runs)
            print(final_report)
            self.save_report(final_report)
            return exit_code
        
        self.log(f"Identified {len(flaky_candidates)} potentially flaky tests for retry")
        
        # Retry logic
        for attempt in range(self.max_retries):
            self.log(f"=== RETRY ATTEMPT {attempt + 1}/{self.max_retries} ===")
            
            retry_exit_code, retry_run = self.retry_failed_tests(flaky_candidates, attempt)
            
            if retry_run:
                all_runs.append(retry_run)
                self.log(f"Retry {attempt + 1} completed: {retry_run.passed} passed, {retry_run.failed} failed")
                
                # Update flaky candidates for next retry (only still failing tests)
                if retry_exit_code == 0:
                    self.log("✅ All retried tests now pass!")
                    break
                else:
                    # Only retry tests that failed again
                    still_failed = [r.name for r in retry_run.results if r.status in ['failed', 'error']]
                    flaky_candidates = [test for test in flaky_candidates if test in still_failed]
                    
                    if not flaky_candidates:
                        self.log("No more tests to retry")
                        break
        
        # Generate final report
        final_report = self.generate_report(all_runs)
        print(final_report)
        self.save_report(final_report)
        
        # Final determination
        final_run = all_runs[-1]
        if final_run.failed == 0 and final_run.errors == 0:
            self.log("✅ All tests passed after retries!")
            return 0
        else:
            self.log(f"❌ {final_run.failed + final_run.errors} tests still failing after all retries")
            return 1


def main() -> int:
    """Entry point for flaky guard script."""
    try:
        guard = FlakyGuard()
        return guard.run()
    except KeyboardInterrupt:
        print("\n❌ Test execution interrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Flaky guard crashed: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())