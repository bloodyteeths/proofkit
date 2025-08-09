#!/usr/bin/env python3
"""
Differential Verification Script

Compares main engine calculations against independent reference implementations
to detect regressions and validate algorithm consistency.

Example usage:
    python scripts/diff_check.py
    python scripts/diff_check.py --industry powder
    python scripts/diff_check.py --tolerance 0.01 --output diff_results.json
"""

import os
import sys
import argparse
import json
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Main engine imports
from core.normalize import normalize_csv_data
from core.decide import make_decision
from core.models import SpecV1
import core.metrics_powder as powder_engine
import core.metrics_haccp as haccp_engine
import core.metrics_coldchain as coldchain_engine
import core.metrics_autoclave as autoclave_engine
import core.metrics_concrete as concrete_engine

# Independent calculator imports
from validation.independent.powder_hold import (
    calculate_hold_time, calculate_ramp_rate as powder_ramp_rate,
    calculate_time_to_threshold
)
from validation.independent.haccp_cooling import validate_cooling_phases
from validation.independent.coldchain_daily import calculate_daily_compliance
from validation.independent.autoclave_fo import calculate_fo_value, calculate_fo_metrics
from validation.independent.concrete_window import calculate_curing_compliance

logger = logging.getLogger(__name__)


class DifferentialChecker:
    """Compares main engine vs independent calculations."""
    
    # Industry-specific tolerances
    INDUSTRY_TOLERANCES = {
        'powder': {
            'hold_time_s': 1.0,  # ±1s for powder hold times
            'ramp_rate_C_per_min': 0.05,  # ±5% for ramp rates
            'time_to_threshold_s': 1.0,  # ±1s for time to threshold
        },
        'autoclave': {
            'fo_value': 0.1,  # ±0.1 for F0 values  
            'hold_time_s': 1.0,  # ±1s for sterilization times
        },
        'coldchain': {
            'overall_compliance_pct': 0.5,  # ±0.5% for compliance percentages
            'excursion_duration_s': 1.0,  # ±1s for excursion timing
        },
        'haccp': {
            'phase1_time_s': 30.0,  # ±30s for 135→70C phase
            'phase2_time_s': 30.0,  # ±30s for 70→41C phase
        },
        'concrete': {
            'percent_in_spec_24h': 1.0,  # ±1% for 24h compliance
            'temperature_time_hours': 0.1,  # ±0.1h for temperature-time
        }
    }
    
    def __init__(self, tolerance: float = 0.05):
        """
        Initialize differential checker.
        
        Args:
            tolerance: Default relative tolerance for numerical comparisons (default 5%)
        """
        self.tolerance = tolerance
        self.results = []
        
    def check_powder_coating(self, csv_path: str, spec_path: str) -> Dict[str, Any]:
        """Compare powder coating calculations."""
        logger.info(f"Checking powder coating: {csv_path}")
        
        try:
            # Load spec and normalize data
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            normalized_df = normalize_csv_data(csv_path, spec)
            
            # Main engine calculation
            engine_result = powder_engine.validate_powder_coating_cure(normalized_df, spec)
            
            # Independent calculation
            timestamps = normalized_df['timestamp'].values
            temp_cols = [col for col in normalized_df.columns 
                        if 'temp' in col.lower() and col != 'timestamp']
            
            if not temp_cols:
                return {
                    'status': 'ERROR',
                    'error': 'No temperature columns found'
                }
            
            # Use first temperature column for independent calculation
            temperatures = normalized_df[temp_cols[0]].values
            
            # Calculate independent metrics
            threshold = spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C
            independent_hold = calculate_hold_time(
                timestamps, temperatures, threshold, 
                hysteresis=2.0, continuous_only=True
            )
            independent_ramp = powder_ramp_rate(timestamps, temperatures)
            independent_time_to_threshold = calculate_time_to_threshold(
                timestamps, temperatures, threshold
            )
            
            # Compare results
            comparisons = {}
            
            # Hold time comparison
            if hasattr(engine_result, 'actual_hold_time_s'):
                engine_hold = engine_result.actual_hold_time_s
                comparisons['hold_time_s'] = self._compare_values(
                    engine_hold, independent_hold, 'hold_time_s', 'powder'
                )
            
            # Ramp rate comparison (if available)
            if hasattr(engine_result, 'ramp_rate_C_per_min'):
                engine_ramp = getattr(engine_result, 'ramp_rate_C_per_min', None)
                if engine_ramp is not None:
                    comparisons['ramp_rate_C_per_min'] = self._compare_values(
                        engine_ramp, independent_ramp, 'ramp_rate_C_per_min', 'powder'
                    )
            
            # Time to threshold comparison
            if hasattr(engine_result, 'time_to_threshold_s'):
                engine_ttt = getattr(engine_result, 'time_to_threshold_s', None)
                if engine_ttt is not None and independent_time_to_threshold != -1:
                    comparisons['time_to_threshold_s'] = self._compare_values(
                        engine_ttt, independent_time_to_threshold, 'time_to_threshold_s', 'powder'
                    )
            
            return {
                'status': 'SUCCESS',
                'industry': 'powder',
                'dataset': os.path.basename(csv_path),
                'engine_result': {
                    'pass': engine_result.pass_,
                    'hold_time_s': getattr(engine_result, 'actual_hold_time_s', None),
                    'ramp_rate_C_per_min': getattr(engine_result, 'ramp_rate_C_per_min', None),
                    'time_to_threshold_s': getattr(engine_result, 'time_to_threshold_s', None)
                },
                'independent_result': {
                    'hold_time_s': independent_hold,
                    'ramp_rate_C_per_min': independent_ramp,
                    'time_to_threshold_s': independent_time_to_threshold if independent_time_to_threshold != -1 else None
                },
                'comparisons': comparisons
            }
            
        except Exception as e:
            logger.error(f"Error in powder coating check: {e}")
            return {
                'status': 'ERROR',
                'industry': 'powder',
                'dataset': os.path.basename(csv_path),
                'error': str(e)
            }
    
    def check_haccp_cooling(self, csv_path: str, spec_path: str) -> Dict[str, Any]:
        """Compare HACCP cooling calculations."""
        logger.info(f"Checking HACCP cooling: {csv_path}")
        
        try:
            # Load spec and normalize data
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            normalized_df = normalize_csv_data(csv_path, spec)
            
            # Main engine calculation
            engine_result = haccp_engine.validate_haccp_cooling(normalized_df, spec)
            
            # Independent calculation
            timestamps = normalized_df['timestamp'].values
            temp_cols = [col for col in normalized_df.columns 
                        if 'temp' in col.lower() and col != 'timestamp']
            
            if not temp_cols:
                return {
                    'status': 'ERROR',
                    'error': 'No temperature columns found'
                }
            
            temperatures = normalized_df[temp_cols[0]].values
            independent_phases = validate_cooling_phases(timestamps, temperatures)
            
            # Compare results
            comparisons = {}
            
            # Phase 1 timing
            if hasattr(engine_result, 'phase1_actual_time_s'):
                engine_phase1 = getattr(engine_result, 'phase1_actual_time_s', None)
                independent_phase1 = independent_phases.get('phase1_actual_time_s')
                
                if engine_phase1 is not None and independent_phase1 is not None:
                    comparisons['phase1_time_s'] = self._compare_values(
                        engine_phase1, independent_phase1, 'phase1_time_s', 'haccp'
                    )
            
            # Phase 2 timing
            if hasattr(engine_result, 'phase2_actual_time_s'):
                engine_phase2 = getattr(engine_result, 'phase2_actual_time_s', None)
                independent_phase2 = independent_phases.get('phase2_actual_time_s')
                
                if engine_phase2 is not None and independent_phase2 is not None:
                    comparisons['phase2_time_s'] = self._compare_values(
                        engine_phase2, independent_phase2, 'phase2_time_s', 'haccp'
                    )
            
            return {
                'status': 'SUCCESS',
                'industry': 'haccp',
                'dataset': os.path.basename(csv_path),
                'engine_result': {
                    'pass': engine_result.pass_,
                    'phase1_time_s': getattr(engine_result, 'phase1_actual_time_s', None),
                    'phase2_time_s': getattr(engine_result, 'phase2_actual_time_s', None)
                },
                'independent_result': independent_phases,
                'comparisons': comparisons
            }
            
        except Exception as e:
            logger.error(f"Error in HACCP cooling check: {e}")
            return {
                'status': 'ERROR',
                'industry': 'haccp',
                'dataset': os.path.basename(csv_path),
                'error': str(e)
            }
    
    def check_coldchain_storage(self, csv_path: str, spec_path: str) -> Dict[str, Any]:
        """Compare cold chain calculations."""
        logger.info(f"Checking cold chain: {csv_path}")
        
        try:
            # Load spec and normalize data
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            normalized_df = normalize_csv_data(csv_path, spec)
            
            # Main engine calculation
            engine_result = coldchain_engine.validate_coldchain_storage(normalized_df, spec)
            
            # Independent calculation
            timestamps = normalized_df['timestamp'].values
            temp_cols = [col for col in normalized_df.columns 
                        if 'temp' in col.lower() and col != 'timestamp']
            
            if not temp_cols:
                return {
                    'status': 'ERROR',
                    'error': 'No temperature columns found'
                }
            
            temperatures = normalized_df[temp_cols[0]].values
            independent_daily = calculate_daily_compliance(timestamps, temperatures, 2.0, 8.0)
            
            # Compare results
            comparisons = {}
            
            # Overall compliance comparison
            if hasattr(engine_result, 'overall_compliance_pct'):
                engine_compliance = getattr(engine_result, 'overall_compliance_pct', None)
                independent_compliance = independent_daily.get('overall_compliance_pct', 0.0)
                
                if engine_compliance is not None:
                    comparisons['overall_compliance_pct'] = self._compare_values(
                        engine_compliance, independent_compliance, 'overall_compliance_pct', 'coldchain'
                    )
            
            return {
                'status': 'SUCCESS',
                'industry': 'coldchain',
                'dataset': os.path.basename(csv_path),
                'engine_result': {
                    'pass': engine_result.pass_,
                    'compliance_pct': getattr(engine_result, 'overall_compliance_pct', None)
                },
                'independent_result': independent_daily,
                'comparisons': comparisons
            }
            
        except Exception as e:
            logger.error(f"Error in cold chain check: {e}")
            return {
                'status': 'ERROR',
                'industry': 'coldchain',
                'dataset': os.path.basename(csv_path),
                'error': str(e)
            }
    
    def check_autoclave_sterilization(self, csv_path: str, spec_path: str) -> Dict[str, Any]:
        """Compare autoclave calculations."""
        logger.info(f"Checking autoclave: {csv_path}")
        
        try:
            # Load spec and normalize data
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            normalized_df = normalize_csv_data(csv_path, spec)
            
            # Main engine calculation
            engine_result = autoclave_engine.validate_autoclave_sterilization(normalized_df, spec)
            
            # Independent calculation
            timestamps = normalized_df['timestamp'].values
            temp_cols = [col for col in normalized_df.columns 
                        if 'temp' in col.lower() and col != 'timestamp']
            
            if not temp_cols:
                return {
                    'status': 'ERROR',
                    'error': 'No temperature columns found'
                }
            
            temperatures = normalized_df[temp_cols[0]].values
            independent_fo = calculate_fo_metrics(timestamps, temperatures, 121.0, 10.0)
            
            # Compare results
            comparisons = {}
            
            # F0 value comparison
            if hasattr(engine_result, 'fo_value'):
                engine_fo = getattr(engine_result, 'fo_value', None)
                independent_fo_val = independent_fo.get('fo_value', 0.0)
                
                if engine_fo is not None:
                    comparisons['fo_value'] = self._compare_values(
                        engine_fo, independent_fo_val, 'fo_value', 'autoclave'
                    )
            
            return {
                'status': 'SUCCESS',
                'industry': 'autoclave',
                'dataset': os.path.basename(csv_path),
                'engine_result': {
                    'pass': engine_result.pass_,
                    'fo_value': getattr(engine_result, 'fo_value', None)
                },
                'independent_result': independent_fo,
                'comparisons': comparisons
            }
            
        except Exception as e:
            logger.error(f"Error in autoclave check: {e}")
            return {
                'status': 'ERROR',
                'industry': 'autoclave',
                'dataset': os.path.basename(csv_path),
                'error': str(e)
            }
    
    def _compare_values(self, engine_val: float, independent_val: float, metric_name: str, industry: str = None) -> Dict[str, Any]:
        """Compare two numerical values with tolerance."""
        if engine_val is None or independent_val is None:
            return {
                'match': False,
                'engine_value': engine_val,
                'independent_value': independent_val,
                'difference': None,
                'relative_error': None,
                'within_tolerance': False,
                'tolerance_type': 'default',
                'tolerance_used': self.tolerance,
                'notes': 'One or both values are None'
            }
        
        # Handle zero values
        if engine_val == 0 and independent_val == 0:
            return {
                'match': True,
                'engine_value': engine_val,
                'independent_value': independent_val,
                'difference': 0.0,
                'relative_error': 0.0,
                'within_tolerance': True,
                'notes': 'Both values are zero'
            }
        
        # Calculate differences
        absolute_diff = abs(engine_val - independent_val)
        
        if max(abs(engine_val), abs(independent_val)) > 0:
            relative_error = absolute_diff / max(abs(engine_val), abs(independent_val))
        else:
            relative_error = 0.0
        
        # Determine tolerance to use (industry-specific or default)
        tolerance_used = self.tolerance
        tolerance_type = 'default'
        
        if industry and industry in self.INDUSTRY_TOLERANCES:
            industry_tolerances = self.INDUSTRY_TOLERANCES[industry]
            if metric_name in industry_tolerances:
                specific_tolerance = industry_tolerances[metric_name]
                tolerance_used = specific_tolerance
                tolerance_type = 'absolute'
                # For absolute tolerances, check absolute difference
                within_tolerance = absolute_diff <= tolerance_used
            else:
                # Use default relative tolerance
                within_tolerance = relative_error <= tolerance_used
        else:
            # Use default relative tolerance  
            within_tolerance = relative_error <= tolerance_used
        
        exact_match = absolute_diff < 1e-10
        
        return {
            'match': exact_match,
            'engine_value': float(engine_val),
            'independent_value': float(independent_val),
            'difference': float(absolute_diff),
            'relative_error': float(relative_error),
            'within_tolerance': within_tolerance,
            'tolerance_used': float(tolerance_used),
            'tolerance_type': tolerance_type,
            'notes': 'Values match exactly' if exact_match else 
                    ('Within tolerance' if within_tolerance else 'Outside tolerance')
        }
    
    def run_diff_check(self, test_cases: List[Dict[str, str]]) -> Dict[str, Any]:
        """Run differential check on multiple test cases."""
        results = []
        summary = {
            'total_cases': 0,
            'successful_cases': 0,
            'error_cases': 0,
            'within_tolerance': 0,
            'outside_tolerance': 0,
            'by_industry': {}
        }
        
        for case in test_cases:
            industry = case.get('industry', '').lower()
            csv_path = case['csv_path']
            spec_path = case['spec_path']
            
            # Run appropriate checker
            if industry == 'powder' or industry == 'powder-coating':
                result = self.check_powder_coating(csv_path, spec_path)
            elif industry == 'haccp':
                result = self.check_haccp_cooling(csv_path, spec_path)
            elif industry == 'coldchain':
                result = self.check_coldchain_storage(csv_path, spec_path)
            elif industry == 'autoclave':
                result = self.check_autoclave_sterilization(csv_path, spec_path)
            else:
                result = {
                    'status': 'ERROR',
                    'industry': industry,
                    'dataset': os.path.basename(csv_path),
                    'error': f'Unsupported industry: {industry}'
                }
            
            results.append(result)
            
            # Update summary
            summary['total_cases'] += 1
            
            if result['status'] == 'SUCCESS':
                summary['successful_cases'] += 1
                
                # Check tolerance compliance
                comparisons = result.get('comparisons', {})
                case_within_tolerance = True
                
                for metric_name, comparison in comparisons.items():
                    if not comparison.get('within_tolerance', True):
                        case_within_tolerance = False
                        break
                
                if case_within_tolerance:
                    summary['within_tolerance'] += 1
                else:
                    summary['outside_tolerance'] += 1
            else:
                summary['error_cases'] += 1
            
            # Industry breakdown
            industry_key = result.get('industry', 'unknown')
            if industry_key not in summary['by_industry']:
                summary['by_industry'][industry_key] = {
                    'total': 0, 'success': 0, 'error': 0, 'within_tolerance': 0
                }
            
            summary['by_industry'][industry_key]['total'] += 1
            if result['status'] == 'SUCCESS':
                summary['by_industry'][industry_key]['success'] += 1
                if case_within_tolerance:
                    summary['by_industry'][industry_key]['within_tolerance'] += 1
            else:
                summary['by_industry'][industry_key]['error'] += 1
        
        return {
            'summary': summary,
            'results': results,
            'tolerance': self.tolerance,
            'timestamp': datetime.now().isoformat()
        }


def load_test_cases(examples_dir: str = None) -> List[Dict[str, str]]:
    """Load test cases from examples directory."""
    if examples_dir is None:
        examples_dir = project_root / "examples"
    
    examples_path = Path(examples_dir)
    if not examples_path.exists():
        return []
    
    test_cases = []
    
    # Look for CSV files and corresponding spec files
    for csv_file in examples_path.glob("*.csv"):
        # Derive spec file name
        csv_name = csv_file.stem
        spec_file = examples_path / f"{csv_name}_spec.json"
        
        if not spec_file.exists():
            # Try alternative naming patterns
            spec_file = examples_path / f"{csv_name}.json"
            if not spec_file.exists():
                logger.warning(f"No spec file found for {csv_file}")
                continue
        
        # Determine industry from filename
        csv_lower = csv_name.lower()
        if 'powder' in csv_lower:
            industry = 'powder'
        elif 'haccp' in csv_lower or 'cooling' in csv_lower:
            industry = 'haccp'
        elif 'coldchain' in csv_lower or 'cold' in csv_lower:
            industry = 'coldchain'
        elif 'autoclave' in csv_lower or 'steriliz' in csv_lower:
            industry = 'autoclave'
        elif 'concrete' in csv_lower:
            industry = 'concrete'
        else:
            logger.warning(f"Could not determine industry for {csv_file}")
            continue
        
        test_cases.append({
            'industry': industry,
            'csv_path': str(csv_file),
            'spec_path': str(spec_file)
        })
    
    return test_cases


def main():
    parser = argparse.ArgumentParser(description="Run differential verification checks")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.05,
        help="Relative tolerance for comparisons (default 5%)"
    )
    parser.add_argument(
        "--industry",
        choices=["powder", "haccp", "coldchain", "autoclave", "concrete"],
        help="Run checks only for specific industry"
    )
    parser.add_argument(
        "--examples-dir",
        help="Directory containing example CSV and spec files"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file for results"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load test cases
    test_cases = load_test_cases(args.examples_dir)
    
    # Filter by industry if specified
    if args.industry:
        test_cases = [case for case in test_cases 
                     if case['industry'].lower() == args.industry.lower()]
    
    if not test_cases:
        logger.error("No test cases found")
        return 1
    
    logger.info(f"Found {len(test_cases)} test cases")
    
    # Run differential checks
    checker = DifferentialChecker(tolerance=args.tolerance)
    results = checker.run_diff_check(test_cases)
    
    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Results saved to {args.output}")
    else:
        print(json.dumps(results, indent=2, default=str))
    
    # Print summary
    summary = results['summary']
    logger.info(f"Summary: {summary['successful_cases']}/{summary['total_cases']} successful")
    logger.info(f"Tolerance compliance: {summary['within_tolerance']}/{summary['successful_cases']} within {args.tolerance*100}%")
    
    # Return appropriate exit code
    if summary['error_cases'] > 0:
        return 1
    elif summary['outside_tolerance'] > 0:
        logger.warning(f"{summary['outside_tolerance']} cases outside tolerance")
        return 2
    else:
        logger.info("All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())