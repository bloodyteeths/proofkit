#!/usr/bin/env python3
"""
Registry-based Validation Runner

Runs validation tests against all datasets in registry.yaml and produces comprehensive reports.
This script serves as the integration point for real-world validation checks using the registry.

Usage:
    python cli/registry_validation.py --mode full
    python cli/registry_validation.py --mode smoke --industries powder,autoclave
    python cli/registry_validation.py --output-format json

Features:
- Validates all datasets in registry.yaml
- Produces detailed reports with performance metrics
- Supports filtering by industry, outcome, or dataset type
- Generates campaign data for /campaign UI
- Validates independent verification metrics for real-world datasets
"""

import argparse
import json
import time
import yaml
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

# Import core validation modules
from core.models import SpecV1
from core.decide import make_decision
from core.normalize import normalize_dataframe
from core.errors import RequiredSignalMissingError, ValidationError
from core.verify import verify_evidence_bundle
from core.pack import create_evidence_bundle


@dataclass
class ValidationResult:
    """Result of validating a single dataset."""
    dataset_id: str
    dataset_key: str
    industry: str
    expected_outcome: str
    actual_outcome: str
    success: bool
    processing_time_s: float
    error_message: Optional[str] = None
    disagreement_reason: Optional[str] = None
    bundle_verified: bool = False
    independent_validation_passed: bool = True


@dataclass
class ConfusionMatrix:
    """Confusion matrix for an industry."""
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    
    @property
    def accuracy(self) -> float:
        """Calculate accuracy percentage."""
        total = self.true_positive + self.false_positive + self.true_negative + self.false_negative
        if total == 0:
            return 0.0
        return (self.true_positive + self.true_negative) / total * 100.0
    
    @property
    def precision(self) -> float:
        """Calculate precision percentage."""
        denominator = self.true_positive + self.false_positive
        if denominator == 0:
            return 0.0
        return self.true_positive / denominator * 100.0
    
    @property
    def recall(self) -> float:
        """Calculate recall percentage."""
        denominator = self.true_positive + self.false_negative
        if denominator == 0:
            return 0.0
        return self.true_positive / denominator * 100.0


@dataclass
class IndustryReport:
    """Validation report for a single industry."""
    industry: str
    confusion_matrix: ConfusionMatrix
    total_tests: int
    disagreements: List[Dict[str, str]]
    performance_metrics: Dict[str, float]


@dataclass
class CampaignReport:
    """Complete campaign validation report."""
    timestamp: str
    total_datasets: int
    industries_tested: List[str]
    industry_reports: Dict[str, IndustryReport]
    overall_accuracy: float
    total_processing_time_s: float
    critical_failures: List[str]


class RegistryValidator:
    """Registry-based validation runner."""
    
    def __init__(self, registry_path: Path, base_path: Path):
        """Initialize validator with registry and base paths."""
        self.registry_path = registry_path
        self.base_path = base_path
        self.logger = logging.getLogger(__name__)
        
        # Load registry
        if not registry_path.exists():
            raise FileNotFoundError(f"Registry file not found: {registry_path}")
        
        with open(registry_path, 'r') as f:
            self.registry = yaml.safe_load(f)
        
        self.logger.info(f"Loaded registry with {len(self.registry['datasets'])} datasets")
    
    def get_datasets(self, 
                    industries: Optional[List[str]] = None,
                    outcomes: Optional[List[str]] = None,
                    dataset_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get filtered datasets from registry."""
        datasets = []
        
        for dataset_key, dataset in self.registry['datasets'].items():
            dataset['key'] = dataset_key
            
            # Apply filters
            if industries and dataset['industry'] not in industries:
                continue
            if outcomes and dataset['expected_outcome'] not in outcomes:
                continue
            if dataset_types:
                # Classify dataset type based on provenance
                dataset_type = 'realworld' if 'realworld' in dataset['csv_path'] else 'synthetic'
                if dataset_type not in dataset_types:
                    continue
            
            datasets.append(dataset)
        
        return datasets
    
    def validate_dataset(self, dataset: Dict[str, Any]) -> ValidationResult:
        """Validate a single dataset."""
        start_time = time.time()
        
        try:
            # Load data files
            csv_path = self.base_path / dataset['csv_path']
            spec_path = self.base_path / dataset['spec_path']
            
            if not csv_path.exists():
                return ValidationResult(
                    dataset_id=dataset['id'],
                    dataset_key=dataset['key'],
                    industry=dataset['industry'],
                    expected_outcome=dataset['expected_outcome'],
                    actual_outcome="ERROR",
                    success=False,
                    processing_time_s=time.time() - start_time,
                    error_message=f"CSV file not found: {csv_path}"
                )
            
            if not spec_path.exists():
                return ValidationResult(
                    dataset_id=dataset['id'],
                    dataset_key=dataset['key'],
                    industry=dataset['industry'],
                    expected_outcome=dataset['expected_outcome'],
                    actual_outcome="ERROR",
                    success=False,
                    processing_time_s=time.time() - start_time,
                    error_message=f"Spec file not found: {spec_path}"
                )
            
            # Load CSV data
            df = pd.read_csv(csv_path)
            
            # Load and validate spec
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            # Normalize data
            normalized_df = normalize_dataframe(df)
            
            # Make decision
            result = make_decision(normalized_df, spec)
            
            # Test evidence bundle
            bundle_verified = False
            try:
                bundle_data = create_evidence_bundle(normalized_df, spec, result)
                verification_result = verify_evidence_bundle(bundle_data)
                bundle_verified = verification_result.get('verified', False)
            except Exception as e:
                self.logger.warning(f"Bundle verification failed for {dataset['id']}: {e}")
            
            # Check independent validation
            independent_validation_passed = True
            if 'independent_validation' in dataset:
                independent_validation_passed = self._validate_independent_metrics(
                    result, dataset['independent_validation']
                )
            
            processing_time = time.time() - start_time
            expected = dataset['expected_outcome']
            actual = result.status
            success = (expected == actual)
            
            disagreement_reason = None
            if not success:
                disagreement_reason = self._generate_disagreement_reason(expected, actual, result)
            
            return ValidationResult(
                dataset_id=dataset['id'],
                dataset_key=dataset['key'],
                industry=dataset['industry'],
                expected_outcome=expected,
                actual_outcome=actual,
                success=success,
                processing_time_s=processing_time,
                bundle_verified=bundle_verified,
                independent_validation_passed=independent_validation_passed,
                disagreement_reason=disagreement_reason
            )
            
        except RequiredSignalMissingError as e:
            processing_time = time.time() - start_time
            expected = dataset['expected_outcome']
            actual = "ERROR"  # Signal missing results in ERROR
            success = (expected in ["ERROR", "INDETERMINATE"])
            
            return ValidationResult(
                dataset_id=dataset['id'],
                dataset_key=dataset['key'],
                industry=dataset['industry'],
                expected_outcome=expected,
                actual_outcome=actual,
                success=success,
                processing_time_s=processing_time,
                error_message=f"Required signal missing: {', '.join(e.missing_signals)}"
            )
            
        except ValidationError as e:
            processing_time = time.time() - start_time
            expected = dataset['expected_outcome']
            actual = "ERROR"
            success = (expected == "ERROR")
            
            return ValidationResult(
                dataset_id=dataset['id'],
                dataset_key=dataset['key'],
                industry=dataset['industry'],
                expected_outcome=expected,
                actual_outcome=actual,
                success=success,
                processing_time_s=processing_time,
                error_message=str(e)
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Unexpected error validating {dataset['id']}: {e}")
            
            return ValidationResult(
                dataset_id=dataset['id'],
                dataset_key=dataset['key'],
                industry=dataset['industry'],
                expected_outcome=dataset['expected_outcome'],
                actual_outcome="ERROR",
                success=False,
                processing_time_s=processing_time,
                error_message=str(e)
            )
    
    def _validate_independent_metrics(self, result: Any, independent_validation: Dict[str, Any]) -> bool:
        """Validate result against independent validation metrics."""
        try:
            # F0 value validation for autoclave
            if 'fo_value_calculated' in independent_validation:
                expected_fo = independent_validation['fo_value_calculated']
                if hasattr(result, 'fo_value'):
                    # Allow 15% tolerance for F0 calculations
                    if abs(result.fo_value - expected_fo) / expected_fo > 0.15:
                        return False
            
            # Hold time validation
            if 'hold_time_minutes' in independent_validation:
                expected_hold = independent_validation['hold_time_minutes'] * 60  # Convert to seconds
                if hasattr(result, 'sterilization_time_s'):
                    # Allow 5 minute tolerance
                    if abs(result.sterilization_time_s - expected_hold) > 300:
                        return False
                elif hasattr(result, 'hold_time_s'):
                    if abs(result.hold_time_s - expected_hold) > 300:
                        return False
            
            # Temperature excursion validation
            if 'excursion_detected' in independent_validation:
                expected_excursion = independent_validation['excursion_detected']
                if expected_excursion:
                    # Should detect excursion in failure reasons
                    if not any("excursion" in reason.lower() or "temperature" in reason.lower()
                              for reason in result.reasons):
                        return False
            
            # Maximum temperature validation
            if 'max_temperature' in independent_validation:
                expected_max = independent_validation['max_temperature']
                if hasattr(result, 'max_temperature_C'):
                    # Allow 2°C tolerance
                    if abs(result.max_temperature_C - expected_max) > 2.0:
                        return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Independent validation check failed: {e}")
            return False
    
    def _generate_disagreement_reason(self, expected: str, actual: str, result: Any) -> str:
        """Generate human-readable disagreement reason."""
        if expected == "PASS" and actual == "FAIL":
            if hasattr(result, 'reasons') and result.reasons:
                return f"Algorithm failed case that should pass: {'; '.join(result.reasons[:2])}"
            return "Algorithm failed case that should pass"
        elif expected == "FAIL" and actual == "PASS":
            return "Algorithm passed case that should fail"
        elif expected in ["ERROR", "INDETERMINATE"] and actual in ["PASS", "FAIL"]:
            return f"Algorithm gave definitive result ({actual}) for uncertain case"
        elif expected in ["PASS", "FAIL"] and actual in ["ERROR", "INDETERMINATE"]:
            return f"Algorithm gave uncertain result ({actual}) for definitive case"
        else:
            return f"Expected {expected}, got {actual}"
    
    def run_validation(self, 
                      industries: Optional[List[str]] = None,
                      outcomes: Optional[List[str]] = None,
                      dataset_types: Optional[List[str]] = None) -> CampaignReport:
        """Run complete validation campaign."""
        start_time = time.time()
        
        # Get datasets to validate
        datasets = self.get_datasets(industries, outcomes, dataset_types)
        
        self.logger.info(f"Running validation on {len(datasets)} datasets")
        
        # Run validations
        results = []
        for dataset in datasets:
            self.logger.debug(f"Validating {dataset['id']}")
            result = self.validate_dataset(dataset)
            results.append(result)
        
        # Generate report
        report = self._generate_campaign_report(results, time.time() - start_time)
        
        self.logger.info(f"Validation completed in {report.total_processing_time_s:.2f}s")
        self.logger.info(f"Overall accuracy: {report.overall_accuracy:.1f}%")
        
        return report
    
    def _generate_campaign_report(self, results: List[ValidationResult], total_time: float) -> CampaignReport:
        """Generate comprehensive campaign report."""
        # Group results by industry
        industry_results = defaultdict(list)
        for result in results:
            industry_results[result.industry].append(result)
        
        # Generate industry reports
        industry_reports = {}
        industries_tested = []
        total_correct = 0
        total_tests = 0
        critical_failures = []
        
        for industry, industry_result_list in industry_results.items():
            industries_tested.append(industry)
            
            # Build confusion matrix
            cm = ConfusionMatrix()
            disagreements = []
            performance_times = []
            
            for result in industry_result_list:
                total_tests += 1
                performance_times.append(result.processing_time_s)
                
                if result.success:
                    total_correct += 1
                    
                    # Classify true positive/negative
                    if result.expected_outcome == "PASS":
                        cm.true_positive += 1
                    else:  # FAIL, ERROR, INDETERMINATE
                        cm.true_negative += 1
                else:
                    # Track disagreements
                    disagreements.append({
                        "dataset": result.dataset_key,
                        "expected": result.expected_outcome,
                        "actual": result.actual_outcome,
                        "reason": result.disagreement_reason or "Unknown disagreement"
                    })
                    
                    # Classify false positive/negative
                    if result.expected_outcome == "PASS" and result.actual_outcome == "FAIL":
                        cm.false_negative += 1
                    elif result.expected_outcome == "FAIL" and result.actual_outcome == "PASS":
                        cm.false_positive += 1
                    elif result.expected_outcome == "PASS":
                        cm.false_negative += 1  # PASS expected but got ERROR/INDETERMINATE
                    else:
                        cm.false_positive += 1  # Non-PASS expected but got PASS
                
                # Track critical failures
                if not result.success and result.industry in ['powder', 'autoclave']:
                    critical_failures.append(f"{result.industry}: {result.dataset_id}")
            
            # Performance metrics
            performance_metrics = {
                "avg_processing_time_s": sum(performance_times) / len(performance_times) if performance_times else 0,
                "max_processing_time_s": max(performance_times) if performance_times else 0,
                "min_processing_time_s": min(performance_times) if performance_times else 0
            }
            
            industry_reports[industry] = IndustryReport(
                industry=industry,
                confusion_matrix=cm,
                total_tests=len(industry_result_list),
                disagreements=disagreements,
                performance_metrics=performance_metrics
            )
        
        # Calculate overall accuracy
        overall_accuracy = (total_correct / total_tests * 100.0) if total_tests > 0 else 0.0
        
        return CampaignReport(
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
            total_datasets=total_tests,
            industries_tested=sorted(industries_tested),
            industry_reports=industry_reports,
            overall_accuracy=overall_accuracy,
            total_processing_time_s=total_time,
            critical_failures=critical_failures
        )
    
    def export_campaign_data(self, report: CampaignReport, output_path: Path):
        """Export campaign data in format compatible with /campaign UI."""
        campaign_data = {}
        
        for industry, industry_report in report.industry_reports.items():
            campaign_data[industry] = {
                "confusion_matrix": asdict(industry_report.confusion_matrix),
                "total_tests": industry_report.total_tests,
                "disagreements": industry_report.disagreements,
                "performance_metrics": industry_report.performance_metrics
            }
        
        # Write JSON output
        with open(output_path, 'w') as f:
            json.dump({
                "timestamp": report.timestamp,
                "total_datasets": report.total_datasets,
                "overall_accuracy": report.overall_accuracy,
                "campaign_data": campaign_data
            }, f, indent=2)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Registry-based validation runner")
    
    parser.add_argument("--registry", type=Path, 
                       default=Path("validation_campaign/registry.yaml"),
                       help="Path to registry.yaml file")
    
    parser.add_argument("--base-path", type=Path, default=Path("."),
                       help="Base path for resolving dataset file paths")
    
    parser.add_argument("--mode", choices=["full", "smoke", "critical"], default="full",
                       help="Validation mode")
    
    parser.add_argument("--industries", type=str,
                       help="Comma-separated list of industries to test")
    
    parser.add_argument("--outcomes", type=str,
                       help="Comma-separated list of outcomes to test")
    
    parser.add_argument("--dataset-types", type=str,
                       help="Comma-separated list of dataset types (synthetic, realworld)")
    
    parser.add_argument("--output", type=Path,
                       help="Output file for campaign data")
    
    parser.add_argument("--output-format", choices=["json", "yaml"], default="json",
                       help="Output format")
    
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Parse filter arguments
    industries = args.industries.split(',') if args.industries else None
    outcomes = args.outcomes.split(',') if args.outcomes else None
    dataset_types = args.dataset_types.split(',') if args.dataset_types else None
    
    # Mode-specific filters
    if args.mode == "smoke":
        # Test minimal set for quick validation
        if not industries:
            industries = ["powder", "autoclave"]
        if not outcomes:
            outcomes = ["PASS", "FAIL"]
    elif args.mode == "critical":
        # Test only critical industries and failure cases
        if not industries:
            industries = ["powder", "autoclave", "haccp"]
        if not outcomes:
            outcomes = ["FAIL", "ERROR"]
    
    try:
        # Initialize validator
        validator = RegistryValidator(args.registry, args.base_path)
        
        # Run validation
        report = validator.run_validation(industries, outcomes, dataset_types)
        
        # Output results
        if args.output:
            if args.output_format == "json":
                validator.export_campaign_data(report, args.output)
                print(f"Campaign data exported to {args.output}")
            else:
                with open(args.output, 'w') as f:
                    yaml.dump(asdict(report), f, default_flow_style=False)
                print(f"Report exported to {args.output}")
        else:
            # Print summary to stdout
            print(f"\nValidation Summary:")
            print(f"  Total datasets: {report.total_datasets}")
            print(f"  Industries: {', '.join(report.industries_tested)}")
            print(f"  Overall accuracy: {report.overall_accuracy:.1f}%")
            print(f"  Processing time: {report.total_processing_time_s:.2f}s")
            
            if report.critical_failures:
                print(f"\nCritical failures:")
                for failure in report.critical_failures:
                    print(f"  - {failure}")
            
            print(f"\nIndustry breakdown:")
            for industry, industry_report in report.industry_reports.items():
                cm = industry_report.confusion_matrix
                print(f"  {industry}: {cm.accuracy:.1f}% ({industry_report.total_tests} tests)")
        
        # Exit with error code if critical failures
        if report.critical_failures:
            exit(1)
        
    except Exception as e:
        logging.error(f"Validation failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()