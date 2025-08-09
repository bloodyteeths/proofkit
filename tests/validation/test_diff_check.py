"""
Tests for Differential Verification System

Tests the differential checker to ensure it correctly compares
engine calculations against independent implementations.
"""

import pytest
import json
import tempfile
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.diff_check import DifferentialChecker, load_test_cases
from validation.independent.powder_hold import calculate_hold_time
from validation.independent.haccp_cooling import validate_cooling_phases
from validation.independent.coldchain_daily import calculate_daily_compliance
from validation.independent.autoclave_fo import calculate_fo_value


class TestDifferentialChecker:
    """Test the DifferentialChecker class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.checker = DifferentialChecker(tolerance=0.05)
    
    def test_compare_values_exact_match(self):
        """Test comparing identical values."""
        result = self.checker._compare_values(100.0, 100.0, 'test_metric')
        
        assert result['match'] is True
        assert result['within_tolerance'] is True
        assert result['relative_error'] == 0.0
        assert result['difference'] == 0.0
        assert 'exactly' in result['notes'].lower()
    
    def test_compare_values_within_tolerance(self):
        """Test comparing values within tolerance."""
        # 3% difference, should be within 5% tolerance
        result = self.checker._compare_values(100.0, 103.0, 'test_metric')
        
        assert result['match'] is False
        assert result['within_tolerance'] is True
        assert result['relative_error'] == 0.03
        assert result['difference'] == 3.0
        assert 'within tolerance' in result['notes'].lower()
    
    def test_compare_values_outside_tolerance(self):
        """Test comparing values outside tolerance."""
        # 10% difference, should be outside 5% tolerance
        result = self.checker._compare_values(100.0, 110.0, 'test_metric')
        
        assert result['match'] is False
        assert result['within_tolerance'] is False
        assert result['relative_error'] == 0.1
        assert result['difference'] == 10.0
        assert 'outside tolerance' in result['notes'].lower()
    
    def test_compare_values_zero_handling(self):
        """Test handling of zero values."""
        # Both zero
        result1 = self.checker._compare_values(0.0, 0.0, 'test_metric')
        assert result1['match'] is True
        assert result1['within_tolerance'] is True
        
        # One zero, one non-zero
        result2 = self.checker._compare_values(0.0, 1.0, 'test_metric')
        assert result2['match'] is False
        assert result2['relative_error'] == 1.0
    
    def test_compare_values_none_handling(self):
        """Test handling of None values."""
        result1 = self.checker._compare_values(None, 100.0, 'test_metric')
        assert result1['match'] is False
        assert result1['within_tolerance'] is False
        assert 'none' in result1['notes'].lower()
        
        result2 = self.checker._compare_values(100.0, None, 'test_metric')
        assert result2['match'] is False
        assert result2['within_tolerance'] is False
    
    def test_tolerance_adjustment(self):
        """Test different tolerance values."""
        strict_checker = DifferentialChecker(tolerance=0.01)  # 1%
        loose_checker = DifferentialChecker(tolerance=0.10)   # 10%
        
        # 5% difference
        engine_val, independent_val = 100.0, 105.0
        
        strict_result = strict_checker._compare_values(engine_val, independent_val, 'test')
        loose_result = loose_checker._compare_values(engine_val, independent_val, 'test')
        
        assert strict_result['within_tolerance'] is False
        assert loose_result['within_tolerance'] is True
    
    def test_industry_specific_tolerances(self):
        """Test industry-specific tolerance application."""
        checker = DifferentialChecker(tolerance=0.05)  # 5% default
        
        # Test powder hold time tolerance (±1s absolute)
        powder_result = checker._compare_values(600.0, 600.5, 'hold_time_s', 'powder')
        assert powder_result['within_tolerance'] is True  # 0.5s difference < 1s
        assert powder_result['tolerance_type'] == 'absolute'
        assert powder_result['tolerance_used'] == 1.0
        
        powder_result_fail = checker._compare_values(600.0, 601.5, 'hold_time_s', 'powder')
        assert powder_result_fail['within_tolerance'] is False  # 1.5s difference > 1s
        
        # Test autoclave F0 tolerance (±0.1 absolute)
        autoclave_result = checker._compare_values(15.0, 15.05, 'fo_value', 'autoclave')
        assert autoclave_result['within_tolerance'] is True  # 0.05 < 0.1
        
        autoclave_result_fail = checker._compare_values(15.0, 15.2, 'fo_value', 'autoclave')
        assert autoclave_result_fail['within_tolerance'] is False  # 0.2 > 0.1
        
        # Test HACCP phase timing (±30s absolute)
        haccp_result = checker._compare_values(7200.0, 7220.0, 'phase1_time_s', 'haccp')
        assert haccp_result['within_tolerance'] is True  # 20s < 30s
        
        haccp_result_fail = checker._compare_values(7200.0, 7250.0, 'phase1_time_s', 'haccp')
        assert haccp_result_fail['within_tolerance'] is False  # 50s > 30s
        
        # Test cold chain compliance (±0.5% absolute)
        coldchain_result = checker._compare_values(95.0, 95.3, 'overall_compliance_pct', 'coldchain')
        assert coldchain_result['within_tolerance'] is True  # 0.3% < 0.5%
        
        coldchain_result_fail = checker._compare_values(95.0, 95.8, 'overall_compliance_pct', 'coldchain')
        assert coldchain_result_fail['within_tolerance'] is False  # 0.8% > 0.5%
    
    def test_default_tolerance_fallback(self):
        """Test fallback to default tolerance for unmapped metrics."""
        checker = DifferentialChecker(tolerance=0.05)  # 5% default
        
        # Unknown metric should use default relative tolerance
        result = checker._compare_values(100.0, 103.0, 'unknown_metric', 'powder')
        assert result['within_tolerance'] is True  # 3% < 5%
        assert result['tolerance_type'] == 'default'
        assert result['tolerance_used'] == 0.05
        
        # Unknown industry should use default tolerance
        result2 = checker._compare_values(100.0, 107.0, 'hold_time_s', 'unknown_industry')
        assert result2['within_tolerance'] is False  # 7% > 5%
        assert result2['tolerance_type'] == 'default'


class TestIndependentCalculators:
    """Test the independent calculators work correctly."""
    
    def setup_method(self):
        """Setup test data."""
        # Create synthetic temperature data
        self.timestamps = pd.date_range('2024-01-01 00:00:00', periods=100, freq='1min')
        
        # Powder coating profile: ramp up, hold, cool down
        temps = []
        for i in range(100):
            if i < 30:  # Ramp up
                temp = 20 + (180 - 20) * (i / 30)
            elif i < 70:  # Hold at 180°C
                temp = 180 + np.random.normal(0, 1)  # Small noise
            else:  # Cool down
                temp = 180 - (180 - 20) * ((i - 70) / 30)
            temps.append(temp)
        
        self.temperatures = np.array(temps)
    
    def test_powder_hold_calculation(self):
        """Test powder coating hold time calculation."""
        hold_time = calculate_hold_time(
            self.timestamps.values,
            self.temperatures,
            threshold=178.0,  # Target + uncertainty
            hysteresis=2.0,
            continuous_only=True
        )
        
        # Should be approximately 40 minutes (from index 30 to 70)
        expected_hold = 40 * 60  # 40 minutes in seconds
        assert abs(hold_time - expected_hold) < 300  # Within 5 minutes
    
    def test_haccp_cooling_phases(self):
        """Test HACCP cooling phase validation."""
        # Create cooling profile from 60°C to 5°C
        cooling_temps = np.linspace(60, 5, 100)
        timestamps = pd.date_range('2024-01-01 12:00:00', periods=100, freq='5min')
        
        phases = validate_cooling_phases(timestamps.values, cooling_temps)
        
        assert 'phase1_pass' in phases
        assert 'phase2_pass' in phases
        assert isinstance(phases['phase1_actual_time_s'], (float, type(None)))
        assert isinstance(phases['phase2_actual_time_s'], (float, type(None)))
    
    def test_coldchain_daily_compliance(self):
        """Test cold chain daily compliance calculation."""
        # Create 24-hour temperature profile mostly in range [2,8]°C
        temps = np.random.normal(5.0, 1.0, 1440)  # 1 minute intervals for 24 hours
        timestamps = pd.date_range('2024-01-01 00:00:00', periods=1440, freq='1min')
        
        daily_stats = calculate_daily_compliance(
            timestamps.values, temps, min_temp_C=2.0, max_temp_C=8.0
        )
        
        assert 'overall_compliance_pct' in daily_stats
        assert 'total_days' in daily_stats
        assert daily_stats['total_days'] >= 1
        assert 0 <= daily_stats['overall_compliance_pct'] <= 100
    
    def test_autoclave_fo_calculation(self):
        """Test autoclave F0 value calculation."""
        # Create sterilization profile: ramp to 121°C, hold, cool
        temps = []
        for i in range(100):
            if i < 20:  # Ramp up
                temp = 20 + (121 - 20) * (i / 20)
            elif i < 80:  # Hold at 121°C
                temp = 121
            else:  # Cool down
                temp = 121 - (121 - 20) * ((i - 80) / 20)
            temps.append(temp)
        
        timestamps = pd.date_range('2024-01-01 10:00:00', periods=100, freq='1min')
        
        fo_result = calculate_fo_value(
            timestamps.values, np.array(temps), reference_temp_C=121.0, z_value_C=10.0
        )
        
        assert fo_result['fo_value'] > 0
        assert 'total_time_s' in fo_result
        assert 'effective_time_s' in fo_result
        assert fo_result['reference_temp_C'] == 121.0
        assert fo_result['z_value_C'] == 10.0


class TestDifferentialIntegration:
    """Test full differential checking integration."""
    
    def setup_method(self):
        """Setup integration test fixtures."""
        self.checker = DifferentialChecker(tolerance=0.05)
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def teardown_method(self):
        """Cleanup temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_files(self, industry: str):
        """Create temporary CSV and spec files for testing."""
        # Create CSV data
        timestamps = pd.date_range('2024-01-01 00:00:00', periods=50, freq='2min')
        
        if industry == 'powder':
            # Powder coating cure profile
            temps = []
            for i in range(50):
                if i < 15:  # Ramp up
                    temp = 20 + (180 - 20) * (i / 15)
                elif i < 35:  # Hold
                    temp = 180 + np.random.normal(0, 0.5)
                else:  # Cool down
                    temp = 180 - (180 - 20) * ((i - 35) / 15)
                temps.append(temp)
        else:
            # Generic temperature profile
            temps = np.random.normal(50, 5, 50)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'temperature': temps
        })
        
        csv_path = self.temp_path / f"{industry}_test.csv"
        df.to_csv(csv_path, index=False)
        
        # Create spec file
        if industry == 'powder':
            spec_data = {
                "version": "1.0",
                "industry": "powder",
                "job": {"job_id": "test_001"},
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 180.0,
                    "hold_time_s": 600,
                    "sensor_uncertainty_C": 2.0
                },
                "data_requirements": {
                    "max_sample_period_s": 300,
                    "allowed_gaps_s": 600
                },
                "sensor_selection": {
                    "mode": "min_of_set",
                    "require_at_least": 1
                },
                "logic": {
                    "continuous": True,
                    "max_total_dips_s": 0
                }
            }
        else:
            spec_data = {
                "version": "1.0",
                "industry": industry,
                "job": {"job_id": "test_001"},
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 50.0,
                    "hold_time_s": 300,
                    "sensor_uncertainty_C": 1.0
                }
            }
        
        spec_path = self.temp_path / f"{industry}_test_spec.json"
        with open(spec_path, 'w') as f:
            json.dump(spec_data, f, indent=2)
        
        return str(csv_path), str(spec_path)
    
    @patch('scripts.diff_check.powder_engine.validate_powder_coating_cure')
    def test_powder_differential_check(self, mock_engine):
        """Test powder coating differential check."""
        # Setup mock engine result
        mock_result = Mock()
        mock_result.pass_ = True
        mock_result.actual_hold_time_s = 1200.0
        mock_engine.return_value = mock_result
        
        csv_path, spec_path = self.create_test_files('powder')
        
        result = self.checker.check_powder_coating(csv_path, spec_path)
        
        assert result['status'] == 'SUCCESS'
        assert result['industry'] == 'powder'
        assert 'engine_result' in result
        assert 'independent_result' in result
        assert 'comparisons' in result
    
    def test_load_test_cases(self):
        """Test loading test cases from directory."""
        # Create example files
        csv_path, spec_path = self.create_test_files('powder')
        
        test_cases = load_test_cases(str(self.temp_path))
        
        assert len(test_cases) >= 1
        
        powder_case = next((case for case in test_cases if case['industry'] == 'powder'), None)
        assert powder_case is not None
        assert 'csv_path' in powder_case
        assert 'spec_path' in powder_case
    
    def test_run_diff_check_summary(self):
        """Test running differential check and generating summary."""
        # Create test files
        csv_path, spec_path = self.create_test_files('powder')
        
        test_cases = [{
            'industry': 'powder',
            'csv_path': csv_path,
            'spec_path': spec_path
        }]
        
        # Mock the engine calls to avoid dependencies
        with patch('scripts.diff_check.powder_engine.validate_powder_coating_cure') as mock_engine:
            mock_result = Mock()
            mock_result.pass_ = True
            mock_result.actual_hold_time_s = 1200.0
            mock_engine.return_value = mock_result
            
            results = self.checker.run_diff_check(test_cases)
        
        assert 'summary' in results
        assert 'results' in results
        assert 'tolerance' in results
        assert 'timestamp' in results
        
        summary = results['summary']
        assert summary['total_cases'] == 1
        assert summary['successful_cases'] >= 0
        assert 'by_industry' in summary


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.checker = DifferentialChecker(tolerance=0.05)
    
    def test_empty_data_handling(self):
        """Test handling of empty datasets."""
        empty_timestamps = np.array([])
        empty_temperatures = np.array([])
        
        # Test independent calculators with empty data
        hold_time = calculate_hold_time(empty_timestamps, empty_temperatures, 100.0)
        assert hold_time == 0.0
        
        daily_stats = calculate_daily_compliance(empty_timestamps, empty_temperatures)
        assert 'errors' in daily_stats
        assert len(daily_stats['errors']) > 0
    
    def test_nan_temperature_handling(self):
        """Test handling of NaN temperatures."""
        timestamps = pd.date_range('2024-01-01', periods=10, freq='1min')
        temperatures = np.array([20, 25, np.nan, 30, np.nan, 35, 40, np.nan, 45, 50])
        
        fo_result = calculate_fo_value(timestamps.values, temperatures, 121.0, 10.0)
        
        # Should handle NaN values gracefully
        assert fo_result['fo_value'] >= 0
        assert fo_result['num_data_points'] < len(temperatures)  # NaN values excluded
    
    def test_single_data_point(self):
        """Test handling of single data point."""
        timestamps = pd.date_range('2024-01-01', periods=1, freq='1min')
        temperatures = np.array([50.0])
        
        hold_time = calculate_hold_time(timestamps.values, temperatures, 40.0)
        assert hold_time == 0.0  # Can't calculate hold time with single point
        
        fo_result = calculate_fo_value(timestamps.values, temperatures, 121.0, 10.0)
        assert fo_result['fo_value'] == 0.0  # Can't integrate with single point
    
    def test_mismatched_array_lengths(self):
        """Test error handling for mismatched array lengths."""
        timestamps = np.array([1, 2, 3])
        temperatures = np.array([20, 25])  # Different length
        
        with pytest.raises(ValueError, match="must have same length"):
            calculate_hold_time(timestamps, temperatures, 100.0)
        
        with pytest.raises(ValueError, match="must have same length"):
            calculate_fo_value(timestamps, temperatures, 121.0, 10.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])