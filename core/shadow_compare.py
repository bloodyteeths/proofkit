"""
ProofKit Shadow Comparison Engine

Implements differential verification by comparing main engine results
against independent reference implementations with industry-specific tolerances.

This module provides the core functionality for shadow runs that help ensure
algorithmic correctness and detect regressions.

Example usage:
    from core.shadow_compare import ShadowComparator
    from core.models import SpecV1
    
    comparator = ShadowComparator()
    result = comparator.run_shadow_comparison(normalized_df, spec)
    
    if result.status == 'INDETERMINATE':
        print(f"Tolerance violation: {result.reason}")
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime
from enum import Enum

from core.models import SpecV1, DecisionResult
from core.decide import make_decision
from core.temperature_utils import detect_temperature_columns

# Independent calculator imports
from validation.independent.powder_hold import (
    calculate_hold_time, 
    calculate_ramp_rate as powder_ramp_rate,
    calculate_time_to_threshold
)
from validation.independent.haccp_cooling import validate_cooling_phases
from validation.independent.coldchain_daily import calculate_daily_compliance
from validation.independent.autoclave_fo import calculate_fo_value, calculate_fo_metrics
from validation.independent.concrete_window import validate_concrete_curing

logger = logging.getLogger(__name__)


class ShadowStatus(Enum):
    """Shadow comparison status codes."""
    AGREEMENT = "AGREEMENT"           # Engine and independent agree within tolerance
    TOLERANCE_VIOLATION = "TOLERANCE_VIOLATION"  # Outside tolerance - return INDETERMINATE
    ENGINE_ERROR = "ENGINE_ERROR"     # Main engine failed
    INDEPENDENT_ERROR = "INDEPENDENT_ERROR"  # Independent calculator failed
    NOT_SUPPORTED = "NOT_SUPPORTED"  # Industry not supported for shadow runs
    DISABLED = "DISABLED"            # Shadow runs disabled


class ShadowResult:
    """Result of shadow comparison run."""
    
    def __init__(self, 
                 status: ShadowStatus,
                 engine_result: Optional[DecisionResult] = None,
                 independent_result: Optional[Dict[str, Any]] = None,
                 differences: Optional[Dict[str, Any]] = None,
                 reason: Optional[str] = None,
                 tolerances_used: Optional[Dict[str, float]] = None):
        self.status = status
        self.engine_result = engine_result
        self.independent_result = independent_result
        self.differences = differences or {}
        self.reason = reason
        self.tolerances_used = tolerances_used or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'status': self.status.value,
            'reason': self.reason,
            'engine_result': self.engine_result.model_dump() if self.engine_result else None,
            'independent_result': self.independent_result,
            'differences': self.differences,
            'tolerances_used': self.tolerances_used
        }


class ShadowComparator:
    """Compares main engine results with independent calculators."""
    
    # Industry-specific tolerances from the specification
    INDUSTRY_TOLERANCES = {
        'powder': {
            'hold_time_s': 1.0,                    # ±1s for powder hold times
            'ramp_rate_C_per_min': 0.05,          # ±5% relative tolerance for ramp rates  
            'time_to_threshold_s': 1.0,           # ±1s for time to threshold
        },
        'autoclave': {
            'fo_value': 0.1,                      # ±0.1 for F0 values
            'hold_time_s': 1.0,                   # ±1s for sterilization times
        },
        'sterile': {
            'phase_times_s': 60.0,                # ±60s for sterile phase times
        },
        'haccp': {
            'phase1_time_s': 30.0,                # ±30s for 135→70C phase
            'phase2_time_s': 30.0,                # ±30s for 70→41C phase  
        },
        'concrete': {
            'percent_in_spec_24h': 1.0,           # ±1% for 24h compliance
            'temperature_time_hours': 0.1,       # ±0.1h for temperature-time
        },
        'coldchain': {
            'overall_compliance_pct': 0.5,       # ±0.5% for compliance percentages
            'excursion_duration_s': 1.0,         # ±1s for excursion timing
        }
    }
    
    def __init__(self, default_tolerance: float = 0.05):
        """
        Initialize shadow comparator.
        
        Args:
            default_tolerance: Default relative tolerance (5%)
        """
        self.default_tolerance = default_tolerance
    
    def run_shadow_comparison(self, 
                            normalized_df: pd.DataFrame, 
                            spec: SpecV1) -> ShadowResult:
        """
        Run complete shadow comparison: engine vs independent calculator.
        
        Args:
            normalized_df: Normalized temperature data
            spec: Process specification
            
        Returns:
            ShadowResult with comparison outcome
        """
        industry = spec.industry.lower() if spec.industry else "powder"
        
        logger.info(f"Starting shadow comparison for {industry} industry")
        
        try:
            # Run main engine
            logger.debug("Running main engine calculation...")
            engine_result = make_decision(normalized_df, spec)
            
            # Run independent calculator
            logger.debug("Running independent calculation...")
            independent_result = self._run_independent_calculator(normalized_df, spec, industry)
            
            if independent_result is None:
                return ShadowResult(
                    status=ShadowStatus.NOT_SUPPORTED,
                    engine_result=engine_result,
                    reason=f"Independent calculator not available for {industry}"
                )
            
            # Compare results
            logger.debug("Comparing engine vs independent results...")
            comparison_result = self._compare_results(
                engine_result, independent_result, industry
            )
            
            if comparison_result['within_tolerance']:
                return ShadowResult(
                    status=ShadowStatus.AGREEMENT,
                    engine_result=engine_result,
                    independent_result=independent_result,
                    differences=comparison_result['differences'],
                    tolerances_used=comparison_result['tolerances_used']
                )
            else:
                # Tolerance violation - should return INDETERMINATE
                violation_details = self._format_tolerance_violations(comparison_result)
                return ShadowResult(
                    status=ShadowStatus.TOLERANCE_VIOLATION,
                    engine_result=engine_result,
                    independent_result=independent_result,
                    differences=comparison_result['differences'],
                    reason=f"DIFF_EXCEEDS_TOL: {violation_details}",
                    tolerances_used=comparison_result['tolerances_used']
                )
                
        except Exception as e:
            logger.error(f"Shadow comparison failed: {e}")
            try:
                # Try to still get engine result
                engine_result = make_decision(normalized_df, spec)
                return ShadowResult(
                    status=ShadowStatus.INDEPENDENT_ERROR,
                    engine_result=engine_result,
                    reason=f"Independent calculator error: {str(e)}"
                )
            except Exception as engine_e:
                return ShadowResult(
                    status=ShadowStatus.ENGINE_ERROR,
                    reason=f"Engine error: {str(engine_e)}, Independent error: {str(e)}"
                )
    
    def _run_independent_calculator(self, 
                                  normalized_df: pd.DataFrame, 
                                  spec: SpecV1, 
                                  industry: str) -> Optional[Dict[str, Any]]:
        """
        Run the appropriate independent calculator based on industry.
        
        Args:
            normalized_df: Normalized data
            spec: Process specification  
            industry: Industry type
            
        Returns:
            Independent calculation results or None if not supported
        """
        # Extract common data
        timestamps = normalized_df['timestamp'].values
        temp_columns = detect_temperature_columns(normalized_df)
        
        if not temp_columns:
            logger.warning("No temperature columns found for independent calculation")
            return None
        
        # Use first temperature column for independent calculation
        temperatures = normalized_df[temp_columns[0]].values
        
        try:
            if industry in ['powder', 'powder-coating']:
                return self._calculate_powder_independent(timestamps, temperatures, spec)
            elif industry == 'haccp':
                return self._calculate_haccp_independent(timestamps, temperatures, spec)
            elif industry == 'coldchain':
                return self._calculate_coldchain_independent(timestamps, temperatures, spec)
            elif industry == 'autoclave':
                return self._calculate_autoclave_independent(timestamps, temperatures, spec)
            elif industry == 'concrete':
                return self._calculate_concrete_independent(timestamps, temperatures, spec)
            else:
                logger.warning(f"Independent calculator not available for industry: {industry}")
                return None
                
        except Exception as e:
            logger.error(f"Independent calculator failed for {industry}: {e}")
            raise
    
    def _calculate_powder_independent(self, 
                                    timestamps: np.ndarray, 
                                    temperatures: np.ndarray, 
                                    spec: SpecV1) -> Dict[str, Any]:
        """Calculate powder coating metrics using independent calculator."""
        threshold = spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C
        
        # Calculate independent metrics
        hold_time = calculate_hold_time(
            timestamps, temperatures, threshold, 
            hysteresis=2.0, continuous_only=True
        )
        ramp_rate = powder_ramp_rate(timestamps, temperatures)
        time_to_threshold = calculate_time_to_threshold(timestamps, temperatures, threshold)
        
        return {
            'industry': 'powder',
            'hold_time_s': hold_time,
            'ramp_rate_C_per_min': ramp_rate,
            'time_to_threshold_s': time_to_threshold if time_to_threshold != -1 else None,
            'threshold_temp_C': threshold,
            'pass': hold_time >= spec.spec.hold_time_s
        }
    
    def _calculate_haccp_independent(self, 
                                   timestamps: np.ndarray, 
                                   temperatures: np.ndarray, 
                                   spec: SpecV1) -> Dict[str, Any]:
        """Calculate HACCP cooling metrics using independent calculator."""
        phases = validate_cooling_phases(timestamps, temperatures)
        return {
            'industry': 'haccp',
            'phase1_actual_time_s': phases.get('phase1_actual_time_s'),
            'phase2_actual_time_s': phases.get('phase2_actual_time_s'),
            'phase1_pass': phases.get('phase1_pass', False),
            'phase2_pass': phases.get('phase2_pass', False),
            'pass': phases.get('phase1_pass', False) and phases.get('phase2_pass', False),
            'start_temp_C': phases.get('start_temp_C'),
            'end_temp_C': phases.get('end_temp_C'),
            'errors': phases.get('errors', [])
        }
    
    def _calculate_coldchain_independent(self, 
                                       timestamps: np.ndarray, 
                                       temperatures: np.ndarray, 
                                       spec: SpecV1) -> Dict[str, Any]:
        """Calculate cold chain metrics using independent calculator."""
        # Default cold chain parameters (2-8°C range)
        daily_compliance = calculate_daily_compliance(timestamps, temperatures, 2.0, 8.0)
        
        return {
            'industry': 'coldchain',
            'overall_compliance_pct': daily_compliance.get('overall_compliance_pct', 0.0),
            'total_excursions': daily_compliance.get('total_excursions', 0),
            'total_excursion_duration_s': daily_compliance.get('total_excursion_duration_s', 0.0),
            'mean_kinetic_temperature_C': daily_compliance.get('mean_kinetic_temperature_C'),
            'pass': daily_compliance.get('overall_compliance_pct', 0.0) >= 95.0
        }
    
    def _calculate_autoclave_independent(self, 
                                       timestamps: np.ndarray, 
                                       temperatures: np.ndarray, 
                                       spec: SpecV1) -> Dict[str, Any]:
        """Calculate autoclave metrics using independent calculator."""
        fo_metrics = calculate_fo_metrics(timestamps, temperatures, 121.0, 10.0)
        
        return {
            'industry': 'autoclave',
            'fo_value': fo_metrics.get('fo_value', 0.0),
            'hold_time_s': fo_metrics.get('hold_time_s', 0.0),
            'max_temp_C': fo_metrics.get('max_temp_C'),
            'min_temp_C': fo_metrics.get('min_temp_C'),
            'pass': fo_metrics.get('sterilization_pass', False)
        }
    
    def _calculate_concrete_independent(self, 
                                      timestamps: np.ndarray, 
                                      temperatures: np.ndarray, 
                                      spec: SpecV1) -> Dict[str, Any]:
        """Calculate concrete curing metrics using independent calculator."""
        # Use spec parameters if available, otherwise defaults
        min_temp = getattr(spec.spec, 'min_temp_C', 10.0)
        max_temp = getattr(spec.spec, 'max_temp_C', 35.0)
        
        curing_result = validate_concrete_curing(
            timestamps, temperatures, 
            min_temp_C=min_temp, max_temp_C=max_temp,
            window_hours=24.0, min_compliance_pct=95.0
        )
        
        return {
            'industry': 'concrete',
            'percent_in_spec_24h': curing_result.get('compliance_pct', 0.0),
            'estimated_strength_pct': curing_result.get('estimated_strength_pct', 0.0),
            'total_maturity_C_h': curing_result.get('total_maturity_C_h', 0.0),
            'curing_duration_days': curing_result.get('curing_duration_days', 0.0),
            'compliant_windows': curing_result.get('compliant_windows', 0),
            'total_windows': curing_result.get('total_windows', 0),
            'pass': curing_result.get('pass', False),
            'reasons': curing_result.get('reasons', [])
        }
    
    def _compare_results(self, 
                        engine_result: DecisionResult, 
                        independent_result: Dict[str, Any], 
                        industry: str) -> Dict[str, Any]:
        """
        Compare engine and independent results with industry-specific tolerances.
        
        Args:
            engine_result: Main engine decision result
            independent_result: Independent calculator result
            industry: Industry type for tolerance lookup
            
        Returns:
            Dict with comparison results and tolerance compliance
        """
        differences = {}
        tolerances_used = {}
        all_within_tolerance = True
        
        # Get industry-specific tolerances
        industry_tolerances = self.INDUSTRY_TOLERANCES.get(industry, {})
        
        # Compare metrics based on industry
        if industry in ['powder', 'powder-coating']:
            comparisons = [
                ('hold_time_s', 'actual_hold_time_s', 'hold_time_s'),
                ('ramp_rate_C_per_min', 'ramp_rate_C_per_min', 'ramp_rate_C_per_min'),
                ('time_to_threshold_s', 'time_to_threshold_s', 'time_to_threshold_s')
            ]
        elif industry == 'haccp':
            comparisons = [
                ('phase1_time_s', 'phase1_actual_time_s', 'phase1_actual_time_s'),
                ('phase2_time_s', 'phase2_actual_time_s', 'phase2_actual_time_s')
            ]
        elif industry == 'coldchain':
            comparisons = [
                ('overall_compliance_pct', 'overall_compliance_pct', 'overall_compliance_pct')
            ]
        elif industry == 'autoclave':
            comparisons = [
                ('fo_value', 'fo_value', 'fo_value'),
                ('hold_time_s', 'actual_hold_time_s', 'hold_time_s')  
            ]
        elif industry == 'concrete':
            comparisons = [
                ('percent_in_spec_24h', 'compliance_pct', 'percent_in_spec_24h')
            ]
        else:
            # Unknown industry - no specific comparisons
            comparisons = []
        
        # Perform comparisons
        for tolerance_key, engine_attr, independent_key in comparisons:
            engine_val = getattr(engine_result, engine_attr, None)
            independent_val = independent_result.get(independent_key)
            
            if engine_val is not None and independent_val is not None:
                comparison = self._compare_values(
                    engine_val, independent_val, tolerance_key, industry_tolerances
                )
                differences[tolerance_key] = comparison
                tolerances_used[tolerance_key] = comparison['tolerance_used']
                
                if not comparison['within_tolerance']:
                    all_within_tolerance = False
                    logger.warning(
                        f"Tolerance violation in {tolerance_key}: "
                        f"engine={engine_val}, independent={independent_val}, "
                        f"diff={comparison['difference']}, "
                        f"tolerance={comparison['tolerance_used']}"
                    )
        
        return {
            'within_tolerance': all_within_tolerance,
            'differences': differences,
            'tolerances_used': tolerances_used,
            'industry': industry
        }
    
    def _compare_values(self, 
                       engine_val: float, 
                       independent_val: float, 
                       metric_name: str,
                       industry_tolerances: Dict[str, float]) -> Dict[str, Any]:
        """
        Compare two values with appropriate tolerance.
        
        Args:
            engine_val: Engine calculated value
            independent_val: Independent calculated value
            metric_name: Name of metric for tolerance lookup
            industry_tolerances: Industry-specific tolerances
            
        Returns:
            Dict with comparison results
        """
        # Handle None values
        if engine_val is None or independent_val is None:
            return {
                'engine_value': engine_val,
                'independent_value': independent_val,
                'difference': None,
                'relative_error': None,
                'within_tolerance': False,
                'tolerance_used': 0.0,
                'tolerance_type': 'N/A',
                'reason': 'One or both values are None'
            }
        
        # Handle zero values
        if engine_val == 0 and independent_val == 0:
            return {
                'engine_value': engine_val,
                'independent_value': independent_val,
                'difference': 0.0,
                'relative_error': 0.0,
                'within_tolerance': True,
                'tolerance_used': 0.0,
                'tolerance_type': 'exact',
                'reason': 'Both values are zero'
            }
        
        # Calculate differences
        absolute_diff = abs(engine_val - independent_val)
        max_val = max(abs(engine_val), abs(independent_val))
        relative_error = absolute_diff / max_val if max_val > 0 else 0.0
        
        # Determine tolerance to use
        if metric_name in industry_tolerances:
            tolerance = industry_tolerances[metric_name]
            tolerance_type = 'absolute'
            within_tolerance = absolute_diff <= tolerance
        else:
            # Fall back to relative tolerance
            tolerance = self.default_tolerance
            tolerance_type = 'relative'
            within_tolerance = relative_error <= tolerance
        
        return {
            'engine_value': float(engine_val),
            'independent_value': float(independent_val),
            'difference': float(absolute_diff),
            'relative_error': float(relative_error),
            'within_tolerance': within_tolerance,
            'tolerance_used': float(tolerance),
            'tolerance_type': tolerance_type,
            'reason': 'Within tolerance' if within_tolerance else 'Outside tolerance'
        }
    
    def _format_tolerance_violations(self, comparison_result: Dict[str, Any]) -> str:
        """Format tolerance violations into a readable string."""
        violations = []
        
        for metric_name, comparison in comparison_result['differences'].items():
            if not comparison['within_tolerance']:
                engine_val = comparison['engine_value']
                independent_val = comparison['independent_value']
                tolerance = comparison['tolerance_used']
                tolerance_type = comparison['tolerance_type']
                
                if tolerance_type == 'absolute':
                    violations.append(
                        f"{metric_name}: {engine_val} vs {independent_val} "
                        f"(diff: {comparison['difference']:.3f}, tolerance: ±{tolerance})"
                    )
                else:
                    violations.append(
                        f"{metric_name}: {engine_val} vs {independent_val} "
                        f"(rel_error: {comparison['relative_error']:.1%}, tolerance: {tolerance:.1%})"
                    )
        
        return "; ".join(violations)


def create_indeterminate_result(shadow_result: ShadowResult, 
                               original_result: DecisionResult) -> DecisionResult:
    """
    Create an INDETERMINATE result when shadow comparison fails tolerance check.
    
    Args:
        shadow_result: Shadow comparison result
        original_result: Original engine result to use as base
        
    Returns:
        DecisionResult with INDETERMINATE status
    """
    return DecisionResult(
        pass_=False,
        status="INDETERMINATE",
        industry=original_result.industry,
        job_id=original_result.job_id,
        target_temp_C=original_result.target_temp_C,
        conservative_threshold_C=original_result.conservative_threshold_C,
        actual_hold_time_s=original_result.actual_hold_time_s,
        required_hold_time_s=original_result.required_hold_time_s,
        max_temp_C=original_result.max_temp_C,
        min_temp_C=original_result.min_temp_C,
        reasons=[shadow_result.reason] if shadow_result.reason else ["Shadow comparison tolerance violation"],
        warnings=original_result.warnings or []
    )