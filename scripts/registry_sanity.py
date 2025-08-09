#!/usr/bin/env python3
"""
Registry Sanity Checker

Validates all datasets in the validation campaign registry by:
1. Loading each entry and parsing with normalizer
2. Computing basic metrics (sample count, step, duplicates, timezone, units)
3. Checking expected outcome matches basic preconditions
4. Writing comprehensive consistency report

Example usage:
    python scripts/registry_sanity.py
    python scripts/registry_sanity.py --registry validation_campaign/registry.yaml --output report_consistency.json
"""

import sys
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.normalize import load_csv_with_metadata, normalize_temperature_data
from core.models import SpecV1
from core.errors import DataQualityError
import core.models as models

# Import independent calculators for validation
from validation.independent import powder_hold, autoclave_fo, coldchain_daily, concrete_window, haccp_cooling

logger = logging.getLogger(__name__)


class RegistrySanityChecker:
    """
    Validates all datasets in validation campaign registry.
    
    Performs comprehensive checks on each dataset including:
    - File existence and readability
    - CSV parsing and normalization
    - Spec schema validation
    - Basic metric computation
    - Expected outcome validation
    """
    
    def __init__(self, registry_path: str = "validation_campaign/registry.yaml"):
        self.registry_path = Path(registry_path)
        self.root_path = Path(__file__).parent.parent
        self.report: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "registry_path": str(registry_path),
            "summary": {
                "total_datasets": 0,
                "passed_validation": 0,
                "failed_validation": 0,
                "errors": 0
            },
            "results": {},
            "errors": []
        }
    
    def load_registry(self) -> Dict[str, Any]:
        """Load and parse registry YAML file."""
        try:
            with open(self.registry_path, 'r') as f:
                registry = yaml.safe_load(f)
            
            if not isinstance(registry, dict) or 'datasets' not in registry:
                raise ValueError("Registry must be a dict with 'datasets' key")
            
            return registry['datasets']
        except Exception as e:
            self.report["errors"].append(f"Failed to load registry: {str(e)}")
            raise
    
    def validate_dataset_entry(self, dataset_id: str, dataset_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single dataset entry from the registry.
        
        Returns validation result with metrics and status.
        """
        result = {
            "dataset_id": dataset_id,
            "status": "unknown",
            "metrics": {},
            "errors": [],
            "warnings": []
        }
        
        try:
            # Check required fields
            required_fields = ["id", "industry", "csv_path", "spec_path", "expected_outcome"]
            for field in required_fields:
                if field not in dataset_config:
                    result["errors"].append(f"Missing required field: {field}")
            
            if result["errors"]:
                result["status"] = "error"
                return result
            
            # Resolve file paths
            csv_path = self.root_path / dataset_config["csv_path"]
            spec_path = self.root_path / dataset_config["spec_path"]
            
            # Check file existence
            if not csv_path.exists():
                result["errors"].append(f"CSV file not found: {csv_path}")
            if not spec_path.exists():
                result["errors"].append(f"Spec file not found: {spec_path}")
            
            if result["errors"]:
                result["status"] = "error"
                return result
            
            # Load and validate spec
            try:
                with open(spec_path, 'r') as f:
                    spec_data = json.load(f)
                spec = SpecV1(**spec_data)
                result["metrics"]["spec_valid"] = True
            except Exception as e:
                result["errors"].append(f"Spec validation failed: {str(e)}")
                result["metrics"]["spec_valid"] = False
                result["status"] = "error"
                return result
            
            # Load and parse CSV
            try:
                df, metadata = load_csv_with_metadata(str(csv_path))
                result["metrics"]["csv_loadable"] = True
                result["metrics"]["sample_count"] = len(df)
                result["metrics"]["metadata"] = metadata
            except Exception as e:
                result["errors"].append(f"CSV loading failed: {str(e)}")
                result["metrics"]["csv_loadable"] = False
                result["status"] = "error"
                return result
            
            # Compute basic metrics
            try:
                # Check for required timestamp column
                if 'timestamp' not in df.columns:
                    result["errors"].append("No timestamp column found")
                    result["status"] = "error"
                    return result
                
                # Convert timestamp to datetime if needed
                if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # Compute time step statistics
                time_diffs = df['timestamp'].diff().dt.total_seconds()
                time_diffs = time_diffs[time_diffs.notna()]
                
                if len(time_diffs) > 0:
                    result["metrics"]["mean_step_s"] = float(time_diffs.mean())
                    result["metrics"]["median_step_s"] = float(time_diffs.median())
                    result["metrics"]["min_step_s"] = float(time_diffs.min())
                    result["metrics"]["max_step_s"] = float(time_diffs.max())
                else:
                    result["warnings"].append("Cannot compute time steps (single sample)")
                
                # Check for duplicate timestamps
                duplicate_count = df['timestamp'].duplicated().sum()
                result["metrics"]["duplicate_timestamps"] = int(duplicate_count)
                if duplicate_count > 0:
                    result["warnings"].append(f"Found {duplicate_count} duplicate timestamps")
                
                # Find temperature columns
                temp_columns = [col for col in df.columns if 'temperature' in col.lower() or col.lower() in ['temp', 't']]
                if not temp_columns:
                    # Look for any numeric columns that might be temperature
                    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                    if 'timestamp' in numeric_cols:
                        numeric_cols.remove('timestamp')
                    temp_columns = numeric_cols
                
                result["metrics"]["temperature_columns"] = temp_columns
                result["metrics"]["temperature_column_count"] = len(temp_columns)
                
                if not temp_columns:
                    result["errors"].append("No temperature columns found")
                    result["status"] = "error"
                    return result
                
                # Compute temperature statistics for first temp column
                if temp_columns:
                    temp_col = temp_columns[0]
                    temp_data = df[temp_col].dropna()
                    
                    if len(temp_data) > 0:
                        result["metrics"]["temp_min"] = float(temp_data.min())
                        result["metrics"]["temp_max"] = float(temp_data.max())
                        result["metrics"]["temp_mean"] = float(temp_data.mean())
                        result["metrics"]["temp_std"] = float(temp_data.std()) if len(temp_data) > 1 else 0.0
                        result["metrics"]["temp_missing_count"] = int(df[temp_col].isna().sum())
                
                # Detect likely temperature units
                if temp_columns:
                    temp_col = temp_columns[0]
                    temp_data = df[temp_col].dropna()
                    if len(temp_data) > 0:
                        avg_temp = temp_data.mean()
                        if avg_temp > 50:
                            result["metrics"]["likely_units"] = "celsius"
                        elif avg_temp > 32:
                            result["metrics"]["likely_units"] = "uncertain"  # Could be C or F
                        else:
                            result["metrics"]["likely_units"] = "celsius_or_other"
                
                # Calculate total duration
                if len(df) > 1:
                    duration_s = (df['timestamp'].max() - df['timestamp'].min()).total_seconds()
                    result["metrics"]["duration_seconds"] = float(duration_s)
                    result["metrics"]["duration_minutes"] = float(duration_s / 60)
                    result["metrics"]["duration_hours"] = float(duration_s / 3600)
                
            except Exception as e:
                result["errors"].append(f"Metrics computation failed: {str(e)}")
                result["status"] = "error"
                return result
            
            # Attempt normalization (basic test)
            try:
                if 'data_requirements' in spec_data and 'max_sample_period_s' in spec_data['data_requirements']:
                    target_step = spec_data['data_requirements']['max_sample_period_s']
                    allowed_gaps = spec_data['data_requirements'].get('allowed_gaps_s', target_step * 2)
                    
                    normalized_df = normalize_temperature_data(
                        df, 
                        target_step_s=target_step, 
                        allowed_gaps_s=allowed_gaps
                    )
                    result["metrics"]["normalization_successful"] = True
                    result["metrics"]["normalized_sample_count"] = len(normalized_df)
                else:
                    result["warnings"].append("Cannot test normalization: missing data_requirements in spec")
            except DataQualityError as e:
                result["metrics"]["normalization_successful"] = False
                result["metrics"]["normalization_error"] = str(e)
                # This might be expected for ERROR cases
            except Exception as e:
                result["errors"].append(f"Normalization test failed: {str(e)}")
            
            # Validate expected outcome using independent calculators
            expected = dataset_config["expected_outcome"]
            result["metrics"]["expected_outcome"] = expected
            
            # Run independent calculator validation if applicable
            industry = dataset_config.get("industry")
            independent_result = self._run_independent_validation(df, spec, industry, dataset_id)
            result["metrics"]["independent_validation"] = independent_result
            
            # Basic outcome validation logic
            outcome_valid = True
            
            if expected == "ERROR":
                # ERROR cases should have data quality issues
                if (result["metrics"].get("duplicate_timestamps", 0) == 0 and 
                    result["metrics"].get("temp_missing_count", 0) == 0 and
                    result["metrics"].get("normalization_successful", True)):
                    result["warnings"].append("Expected ERROR but data appears clean")
                    outcome_valid = False
            
            elif expected in ["PASS", "FAIL"]:
                # PASS/FAIL cases should have clean data
                if (result["metrics"].get("duplicate_timestamps", 0) > 0 or
                    not result["metrics"].get("normalization_successful", False)):
                    result["warnings"].append(f"Expected {expected} but data has quality issues")
                    outcome_valid = False
                
                # Validate against independent calculator if available
                if independent_result and "feasible" in independent_result:
                    calc_feasible = independent_result["feasible"]
                    if expected == "PASS" and not calc_feasible:
                        result["warnings"].append(f"Independent calculator suggests FAIL but expected PASS")
                        outcome_valid = False
                    elif expected == "FAIL" and calc_feasible:
                        result["warnings"].append(f"Independent calculator suggests PASS but expected FAIL")
                        outcome_valid = False
            
            result["metrics"]["expected_outcome_reasonable"] = outcome_valid
            
            # Determine overall status
            if result["errors"]:
                result["status"] = "error"
            elif result["warnings"] and not outcome_valid:
                result["status"] = "warning"
            else:
                result["status"] = "passed"
            
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(f"Unexpected validation error: {str(e)}")
        
        return result
    
    def _run_independent_validation(self, df: pd.DataFrame, spec: SpecV1, industry: str, dataset_id: str) -> Optional[Dict[str, Any]]:
        """
        Run independent calculator validation for applicable datasets.
        
        Returns validation results or None if not applicable.
        """
        try:
            if not hasattr(df, 'timestamp') or len(df) < 2:
                return None
                
            # Ensure timestamp is datetime
            if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df = df.copy()
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Find temperature column
            temp_cols = [col for col in df.columns if 'temperature' in col.lower()]
            if not temp_cols:
                return None
                
            temp_col = temp_cols[0]
            timestamps = df['timestamp'].values
            temperatures = df[temp_col].values
            
            # Remove NaN values
            valid_mask = ~np.isnan(temperatures)
            timestamps = timestamps[valid_mask]
            temperatures = temperatures[valid_mask]
            
            if len(temperatures) < 2:
                return None
            
            result = {"calculator_used": None, "feasible": None, "metrics": {}}
            
            # Run industry-specific independent calculators
            if industry == "powder":
                result["calculator_used"] = "powder_hold"
                
                # Extract target conditions from spec
                target_temp = 180.0  # Default
                min_hold_s = 600.0  # Default 10 minutes
                
                if hasattr(spec, 'target_conditions'):
                    if 'temperature' in spec.target_conditions:
                        target_temp = spec.target_conditions['temperature'].get('value', 180.0)
                    min_hold_s = spec.target_conditions.get('minimum_hold_time_s', 600.0)
                
                # Calculate hold time
                hold_time_s = powder_hold.calculate_hold_time(
                    timestamps, temperatures, target_temp, hysteresis=2.0, continuous_only=True
                )
                
                result["metrics"]["hold_time_s"] = hold_time_s
                result["metrics"]["hold_time_min"] = hold_time_s / 60
                result["metrics"]["target_temp"] = target_temp
                result["metrics"]["min_required_s"] = min_hold_s
                result["feasible"] = hold_time_s >= min_hold_s
                
            elif industry == "coldchain":
                result["calculator_used"] = "coldchain_daily"
                
                # Check for temperature excursions
                min_temp = 2.0
                max_temp = 8.0
                
                if hasattr(spec, 'target_conditions') and 'temperature_range' in spec.target_conditions:
                    temp_range = spec.target_conditions['temperature_range']
                    min_temp = temp_range.get('min', 2.0)
                    max_temp = temp_range.get('max', 8.0)
                
                excursions = coldchain_daily.detect_excursions(
                    timestamps, temperatures, min_temp, max_temp
                )
                
                result["metrics"]["excursions_detected"] = len(excursions)
                result["metrics"]["max_excursion_temp"] = max(temperatures) if len(temperatures) > 0 else None
                result["metrics"]["min_excursion_temp"] = min(temperatures) if len(temperatures) > 0 else None
                result["feasible"] = len(excursions) == 0
                
            elif industry == "concrete":
                result["calculator_used"] = "concrete_window"
                
                # Check temperature compliance over curing window
                min_temp = 10.0
                duration_hours = (timestamps[-1] - timestamps[0]) / np.timedelta64(1, 'h')
                
                compliant = concrete_window.validate_curing_window(
                    timestamps, temperatures, min_temp=min_temp, min_duration_hours=48
                )
                
                result["metrics"]["duration_hours"] = float(duration_hours)
                result["metrics"]["min_temp_maintained"] = float(np.min(temperatures)) >= min_temp
                result["feasible"] = compliant
                
            elif industry == "autoclave":
                result["calculator_used"] = "autoclave_fo"
                
                # Calculate F0 value if possible
                target_temp = 121.0
                if hasattr(spec, 'target_conditions') and 'temperature' in spec.target_conditions:
                    target_temp = spec.target_conditions['temperature'].get('value', 121.0)
                
                fo_value = autoclave_fo.calculate_fo_value(timestamps, temperatures, target_temp)
                
                result["metrics"]["fo_value"] = fo_value
                result["metrics"]["target_temp"] = target_temp
                result["feasible"] = fo_value >= 8.0  # Minimum F0 for sterilization
                
            elif industry == "haccp":
                result["calculator_used"] = "haccp_cooling"
                
                # Validate cooling curve compliance
                compliant = haccp_cooling.validate_cooling_curve(
                    timestamps, temperatures, start_temp=135.0, intermediate_temp=70.0, final_temp=41.0
                )
                
                result["metrics"]["cooling_compliant"] = compliant
                result["feasible"] = compliant
            
            elif industry == "sterile":
                # Use powder hold calculator for sterile dry heat
                result["calculator_used"] = "powder_hold_adapted"
                
                target_temp = 170.0
                min_hold_s = 3600.0  # 1 hour
                
                if hasattr(spec, 'target_conditions'):
                    if 'temperature' in spec.target_conditions:
                        target_temp = spec.target_conditions['temperature'].get('value', 170.0)
                    min_hold_s = spec.target_conditions.get('minimum_hold_time_s', 3600.0)
                
                hold_time_s = powder_hold.calculate_hold_time(
                    timestamps, temperatures, target_temp, hysteresis=2.0, continuous_only=True
                )
                
                result["metrics"]["hold_time_s"] = hold_time_s
                result["metrics"]["target_temp"] = target_temp
                result["feasible"] = hold_time_s >= min_hold_s
            
            return result
            
        except Exception as e:
            return {"error": str(e), "calculator_used": None, "feasible": None}
    
    def run_validation(self) -> Dict[str, Any]:
        """Run validation on all datasets in registry."""
        try:
            datasets = self.load_registry()
            self.report["summary"]["total_datasets"] = len(datasets)
            
            for dataset_name, dataset_config in datasets.items():
                logger.info(f"Validating dataset: {dataset_name}")
                
                result = self.validate_dataset_entry(dataset_name, dataset_config)
                self.report["results"][dataset_name] = result
                
                # Update summary counts
                if result["status"] == "passed":
                    self.report["summary"]["passed_validation"] += 1
                elif result["status"] == "warning":
                    self.report["summary"]["failed_validation"] += 1
                else:  # error
                    self.report["summary"]["errors"] += 1
        
        except Exception as e:
            self.report["errors"].append(f"Validation run failed: {str(e)}")
            logger.error(f"Validation failed: {e}")
        
        return self.report
    
    def save_report(self, output_path: str = "report_consistency.json") -> None:
        """Save validation report to JSON file."""
        output_file = Path(output_path)
        with open(output_file, 'w') as f:
            json.dump(self.report, f, indent=2, default=str)
        
        logger.info(f"Validation report saved to: {output_file}")


def main():
    """Main entry point for registry sanity checker."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate validation campaign registry")
    parser.add_argument(
        "--registry", 
        default="validation_campaign/registry.yaml",
        help="Path to registry YAML file"
    )
    parser.add_argument(
        "--output",
        default="report_consistency.json", 
        help="Output path for validation report"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run validation
    checker = RegistrySanityChecker(args.registry)
    report = checker.run_validation()
    checker.save_report(args.output)
    
    # Print summary
    summary = report["summary"]
    print("\n=== Registry Validation Summary ===")
    print(f"Total datasets: {summary['total_datasets']}")
    print(f"Passed: {summary['passed_validation']}")
    print(f"Failed: {summary['failed_validation']}")  
    print(f"Errors: {summary['errors']}")
    
    if report["errors"]:
        print("\n=== Global Errors ===")
        for error in report["errors"]:
            print(f"ERROR: {error}")
    
    # Print detailed results for failed cases
    failed_cases = [
        (name, result) for name, result in report["results"].items() 
        if result["status"] in ["warning", "error"]
    ]
    
    if failed_cases:
        print(f"\n=== Failed/Warning Cases ({len(failed_cases)}) ===")
        for name, result in failed_cases:
            print(f"\n{name} ({result['status'].upper()}):")
            if result["errors"]:
                for error in result["errors"]:
                    print(f"  ERROR: {error}")
            if result["warnings"]:
                for warning in result["warnings"]:
                    print(f"  WARNING: {warning}")
    
    # Exit with appropriate code
    if summary["errors"] > 0:
        sys.exit(1)
    elif summary["failed_validation"] > 0:
        sys.exit(2)  # Warnings
    else:
        print("\n✅ All datasets passed validation!")
        sys.exit(0)


if __name__ == "__main__":
    main()