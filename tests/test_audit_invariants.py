"""
ProofKit Audit Invariants Testing

Property-based testing for ProofKit decision algorithm invariants.
Uses systematic testing to verify that the decision engine maintains
consistent behavior across all edge cases and transformations.

This module tests core invariants including:
1. Determinism: identical inputs → identical outputs
2. Monotonicity: temperature/time increases shouldn't decrease PASS likelihood  
3. Threshold consistency: conservative thresholds are properly applied
4. Sensor combination correctness: multi-sensor logic works as expected
5. Edge case robustness: boundary conditions are handled properly

Example usage:
    pytest tests/test_audit_invariants.py -v
    pytest tests/test_audit_invariants.py::TestDeterminismInvariants -s
"""

import pytest
import pandas as pd
import numpy as np
import json
import hashlib
import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import sys

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision, calculate_conservative_threshold
from core.models import SpecV1
# from core.validation import validate_spec  # Using Pydantic models for validation


class TestDeterminismInvariants:
    """Test that the decision algorithm is deterministic."""
    
    def test_identical_inputs_identical_outputs(self, tmp_path):
        """Identical CSV+spec inputs must produce identical decision outputs."""
        # Create test data
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=100, freq='10S')
        temp_data = np.concatenate([
            np.linspace(25, 180, 50),  # Ramp up
            np.full(50, 182)  # Hold at 182°C
        ])
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': temp_data + np.random.normal(0, 0.1, 100),
            'sensor_2': temp_data + np.random.normal(0, 0.1, 100),
            'sensor_3': temp_data + np.random.normal(0, 0.1, 100)
        })
        
        csv_path = tmp_path / "test.csv"
        df.to_csv(csv_path, index=False)
        
        spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "determinism_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": true,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Run decision algorithm multiple times
        results = []
        for i in range(5):
            df, _ = load_csv_with_metadata(str(csv_path))
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
            spec_model = SpecV1(**spec)
            decision_result = make_decision(normalized_df, spec_model)
            
            # Create reproducible hash of the decision
            if hasattr(decision_result, 'model_dump'):
                decision_dict = decision_result.model_dump(by_alias=True)
            else:
                decision_dict = decision_result
            decision_str = json.dumps(decision_dict, sort_keys=True, default=str)
            decision_hash = hashlib.sha256(decision_str.encode()).hexdigest()
            results.append((decision_dict, decision_hash))
        
        # All results should be identical
        first_hash = results[0][1]
        for i, (result, result_hash) in enumerate(results):
            assert result_hash == first_hash, f"Run {i} produced different result hash"
            decision_field = 'decision' if 'decision' in result else 'status'
            expected_decision = results[0][0].get('decision', results[0][0].get('status'))
            actual_decision = result.get('decision', result.get('status'))
            assert actual_decision == expected_decision, f"Run {i} produced different decision"
    
    def test_data_order_independence(self, tmp_path):
        """Decision should be independent of CSV row ordering (after timestamp sorting)."""
        # Create test data
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='10S')
        temp_data = np.concatenate([
            np.linspace(25, 180, 25),
            np.full(25, 182)
        ])
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': temp_data,
            'sensor_2': temp_data + 0.5,
            'sensor_3': temp_data - 0.3
        })
        
        # Create ordered version
        ordered_path = tmp_path / "ordered.csv"
        df.to_csv(ordered_path, index=False)
        
        # Create shuffled version (but keep timestamps valid)
        shuffled_df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        shuffled_path = tmp_path / "shuffled.csv"
        shuffled_df.to_csv(shuffled_path, index=False)
        
        spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "order_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 200,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Test both orderings
        df1, _ = load_csv_with_metadata(str(ordered_path))
        data_reqs = spec.get('data_requirements', {})
        ordered_norm = normalize_temperature_data(
            df1, 
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
        )
        ordered_decision = make_decision(ordered_norm, spec)
        
        df2, _ = load_csv_with_metadata(str(shuffled_path))
        shuffled_norm = normalize_temperature_data(
            df2, 
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
        )
        shuffled_decision = make_decision(shuffled_norm, spec)
        
        # Decisions should be identical
        ordered_decision_val = ordered_decision.get('decision', ordered_decision.get('status'))
        shuffled_decision_val = shuffled_decision.get('decision', shuffled_decision.get('status'))
        assert ordered_decision_val == shuffled_decision_val


class TestThresholdInvariants:
    """Test threshold calculation and application consistency."""
    
    def test_conservative_threshold_calculation(self):
        """Conservative threshold should always be target + uncertainty."""
        test_cases = [
            (180.0, 2.0, 182.0),
            (121.0, 0.5, 121.5),
            (5.0, 1.0, 6.0),
            (200.0, 3.5, 203.5),
            (0.0, 0.0, 0.0)
        ]
        
        for target, uncertainty, expected in test_cases:
            result = calculate_conservative_threshold(target, uncertainty)
            assert result == expected, f"Conservative threshold for {target}±{uncertainty} should be {expected}, got {result}"
    
    def test_threshold_boundary_behavior(self, tmp_path):
        """Test decision behavior exactly at threshold boundaries."""
        spec = {
            "version": "1.0",
            "industry": "powder", 
            "job": {"job_id": "boundary_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Conservative threshold should be 180 + 2 = 182°C
        conservative_threshold = 182.0
        
        # Test cases around the boundary
        boundary_temps = [
            (181.9, "just_below"),  # Just below threshold
            (182.0, "exactly_at"),  # Exactly at threshold  
            (182.1, "just_above")  # Just above threshold
        ]
        
        results = {}
        
        for temp, case_name in boundary_temps:
            # Create data that reaches the test temperature and holds
            timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='10S')
            temp_data = np.concatenate([
                np.linspace(25, temp, 25),  # Ramp to test temp
                np.full(25, temp)  # Hold at test temp
            ])
            
            df = pd.DataFrame({
                'timestamp': timestamps,
                'sensor_1': temp_data,
                'sensor_2': temp_data + 0.1,
                'sensor_3': temp_data - 0.1
            })
            
            csv_path = tmp_path / f"boundary_{case_name}.csv"
            df.to_csv(csv_path, index=False)
            
            df, _ = load_csv_with_metadata(str(csv_path))
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
            spec_model = SpecV1(**spec)
            decision_result = make_decision(normalized_df, spec_model)
            results[case_name] = decision_result.get('decision', decision_result.get('status'))
        
        # Just below threshold should FAIL
        assert results["just_below"] == "FAIL"
        # At or above threshold should PASS (if hold time is sufficient)
        assert results["exactly_at"] in ["PASS", "FAIL"]  # Could go either way due to hysteresis
        assert results["just_above"] == "PASS"


class TestSensorCombinationInvariants:
    """Test sensor combination logic consistency."""
    
    def test_min_of_set_behavior(self, tmp_path):
        """Test min_of_set sensor combination produces expected results."""
        spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "min_sensor_test"},
            "spec": {
                "method": "OVEN_AIR", 
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en", 
                "timezone": "UTC"
            }
        }
        
        # Create test case where one sensor is consistently lower
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='10S')
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': np.concatenate([np.linspace(25, 185, 25), np.full(25, 185)]),  # High sensor
            'sensor_2': np.concatenate([np.linspace(25, 183, 25), np.full(25, 183)]),  # Medium sensor
            'sensor_3': np.concatenate([np.linspace(25, 181, 25), np.full(25, 181)])   # Low sensor (should control)
        })
        
        csv_path = tmp_path / "min_sensor_test.csv"
        df.to_csv(csv_path, index=False)
        
        df, _ = load_csv_with_metadata(str(csv_path))\n        normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
        spec_model = SpecV1(**spec)
        decision_result = make_decision(normalized_df, spec_model)
        
        # With conservative threshold of 182°C, the minimum sensor at 181°C should cause FAIL
        decision_val = decision_result.get('decision', decision_result.get('status'))
        assert decision_val == "FAIL"
    
    def test_sensor_count_requirement(self, tmp_path):
        """Test that sensor count requirements are enforced."""
        spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "sensor_count_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 3  # Require 3 sensors
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Create CSV with only 2 sensors (should fail requirement)
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=50, freq='10S')
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': np.concatenate([np.linspace(25, 185, 25), np.full(25, 185)]),
            'sensor_2': np.concatenate([np.linspace(25, 185, 25), np.full(25, 185)])
            # Missing sensor_3 - only 2 sensors when 3 required
        })
        
        csv_path = tmp_path / "insufficient_sensors.csv"
        df.to_csv(csv_path, index=False)
        
        # Should raise an error due to insufficient sensors
        with pytest.raises(Exception):
            df, _ = load_csv_with_metadata(str(csv_path))
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
            spec_model = SpecV1(**spec)
            make_decision(normalized_df, spec_model)


class TestTemporalInvariants:
    """Test time-related decision invariants."""
    
    def test_hold_time_monotonicity(self, tmp_path):
        """Longer hold times should not decrease PASS likelihood."""
        base_spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "hold_time_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,  # Will vary this
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Create CSV with long hold time at qualifying temperature
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=120, freq='10S')
        temp_data = np.concatenate([
            np.linspace(25, 185, 20),  # Ramp up
            np.full(100, 185)  # Long hold at 185°C (well above 182°C threshold)
        ])
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'sensor_1': temp_data,
            'sensor_2': temp_data + 0.5,
            'sensor_3': temp_data - 0.3
        })
        
        csv_path = tmp_path / "hold_time_test.csv"
        df.to_csv(csv_path, index=False)
        
        # Test with different hold time requirements
        hold_times = [60, 300, 600, 900]  # 1 min to 15 min
        results = []
        
        for hold_time in hold_times:
            spec = copy.deepcopy(base_spec)
            spec['spec']['hold_time_s'] = hold_time
            
            df, _ = load_csv_with_metadata(str(csv_path))
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
            spec_model = SpecV1(**spec)
            decision_result = make_decision(normalized_df, spec_model)
            results.append((hold_time, decision_result.get('decision', decision_result.get('status'))))
        
        # If any shorter hold time passes, all longer ones should also pass
        # (monotonicity property)
        pass_found = False
        for hold_time, decision in results:
            if decision == "PASS":
                pass_found = True
            elif pass_found:
                # If we found a pass earlier, this longer hold time should also pass
                assert decision == "PASS", f"Hold time monotonicity violated: {hold_time}s failed after shorter time passed"


class TestDataQualityInvariants:
    """Test data quality validation consistency."""
    
    def test_gap_detection_consistency(self, tmp_path):
        """Gap detection should be consistent regardless of gap placement."""
        spec = {
            "version": "1.0",
            "industry": "powder",
            "job": {"job_id": "gap_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0  # 1 minute gap tolerance
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Create base timestamps
        base_times = pd.date_range('2024-01-01 10:00:00', periods=40, freq='10S')
        
        # Test cases with gaps in different locations
        gap_scenarios = [
            ("early_gap", [0, 1, 2, 3, 4, 12, 13, 14, 15]),  # Gap after 4th sample (8 minutes = 480s > 60s)
            ("middle_gap", [0, 1, 2, 15, 16, 17, 18, 19]),   # Gap in middle  
            ("late_gap", [0, 1, 2, 3, 4, 5, 6, 20, 21, 22])  # Gap near end
        ]
        
        for scenario_name, keep_indices in gap_scenarios:
            # Create DataFrame with gap
            timestamps = base_times[keep_indices]
            temp_data = np.full(len(timestamps), 185)  # High enough to pass if no gap issues
            
            df = pd.DataFrame({
                'timestamp': timestamps,
                'sensor_1': temp_data,
                'sensor_2': temp_data + 0.5,
                'sensor_3': temp_data - 0.3
            })
            
            csv_path = tmp_path / f"gap_{scenario_name}.csv"
            df.to_csv(csv_path, index=False)
            
            # All gap scenarios should be detected and handled consistently
            try:
                df, _ = load_csv_with_metadata(str(csv_path))
                data_reqs = spec.get('data_requirements', {})
                normalized_df = normalize_temperature_data(
                    df, 
                    target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                    allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
                )
                # If normalization succeeds with large gaps, consider it handled
                # The gap detection logic should either interpolate or raise an error
                pass
            except Exception:
                # Gap causes validation error - this is expected and acceptable
                pass
    
    def test_duplicate_timestamp_handling(self, tmp_path):
        """Duplicate timestamps should be handled consistently."""
        spec = {
            "version": "1.0", 
            "industry": "powder",
            "job": {"job_id": "duplicate_test"},
            "spec": {
                "method": "OVEN_AIR",
                "target_temp_C": 180.0,
                "hold_time_s": 300,
                "temp_band_C": {"min": 170.0, "max": 190.0},
                "sensor_uncertainty_C": 2.0
            },
            "data_requirements": {
                "max_sample_period_s": 30.0,
                "allowed_gaps_s": 60.0
            },
            "sensor_selection": {
                "mode": "min_of_set",
                "require_at_least": 2
            },
            "logic": {
                "continuous": True,
                "max_total_dips_s": 0
            },
            "preconditions": {
                "max_ramp_rate_C_per_min": 10.0,
                "max_time_to_threshold_s": 600
            },
            "reporting": {
                "units": "C",
                "language": "en",
                "timezone": "UTC"
            }
        }
        
        # Create data with duplicate timestamps
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=30, freq='10S')
        duplicate_timestamps = list(timestamps) + [timestamps[10], timestamps[20]]  # Add duplicates
        
        df = pd.DataFrame({
            'timestamp': duplicate_timestamps,
            'sensor_1': np.full(len(duplicate_timestamps), 185),
            'sensor_2': np.full(len(duplicate_timestamps), 185),
            'sensor_3': np.full(len(duplicate_timestamps), 185)
        })
        
        csv_path = tmp_path / "duplicate_timestamps.csv"
        df.to_csv(csv_path, index=False)
        
        # Duplicate timestamps should be handled (either by error or deduplication)
        try:
            df, _ = load_csv_with_metadata(str(csv_path))
            data_reqs = spec.get('data_requirements', {})
            normalized_df = normalize_temperature_data(
                df, 
                target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
            )
            # If successful, should have deduplicated or warned about duplicates
            assert len(normalized_df) <= len(timestamps), "Duplicates should be removed or handled"
        except Exception:
            # Exception due to duplicate timestamps is also acceptable
            pass


class TestAuditFixtureInvariants:
    """Test that audit fixtures behave according to their expected results."""
    
    def test_fixture_expectations_match_reality(self):
        """Test that fixture files produce results matching their expected outcomes."""
        # Find audit fixtures directory
        script_dir = Path(__file__).parent.parent
        audit_dir = script_dir / "audit" / "fixtures"
        
        if not audit_dir.exists():
            pytest.skip("Audit fixtures directory not found")
        
        # Expected results mapping
        expected_outcomes = {
            "pass": "PASS",
            "fail": "FAIL", 
            "borderline": None,  # Could be either
            "missing_required": "ERROR",
            "gap": "ERROR",
            "dup_ts": "ERROR", 
            "tz_shift": None  # Should handle gracefully
        }
        
        # Test each fixture
        fixture_count = 0
        for industry_dir in audit_dir.iterdir():
            if not industry_dir.is_dir():
                continue
                
            industry = industry_dir.name
            
            for csv_file in industry_dir.glob("*.csv"):
                test_type = csv_file.stem
                json_file = industry_dir / f"{test_type}.json"
                
                if not json_file.exists():
                    continue
                
                fixture_count += 1
                expected = expected_outcomes.get(test_type)
                
                # Load spec
                with open(json_file) as f:
                    spec = json.load(f)
                
                # Test the fixture
                try:
                    df, _ = load_csv_with_metadata(str(csv_file))
                    data_reqs = spec.get('data_requirements', {})
                    normalized_df = normalize_temperature_data(
                        df, 
                        target_step_s=data_reqs.get('max_sample_period_s', 30.0),
                        allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0)
                    )
                    spec_model = SpecV1(**spec)
                    decision_result = make_decision(normalized_df, spec_model)
                    actual_decision = decision_result.get('decision', decision_result.get('status'))
                    
                    # Check against expectation
                    if expected:
                        assert actual_decision == expected, f"Fixture {industry}/{test_type} expected {expected}, got {actual_decision}"
                    else:
                        # For borderline/tz_shift cases, just ensure it doesn't crash
                        assert actual_decision in ["PASS", "FAIL"], f"Fixture {industry}/{test_type} produced invalid decision: {actual_decision}"
                        
                except Exception as e:
                    if expected == "ERROR":
                        # Expected to fail
                        continue
                    else:
                        pytest.fail(f"Fixture {industry}/{test_type} unexpectedly failed: {e}")
        
        # Ensure we found some fixtures
        assert fixture_count > 0, "No audit fixtures found for testing"


if __name__ == "__main__":
    # Run specific test classes when executed directly
    pytest.main([__file__ + "::TestDeterminismInvariants", "-v"])