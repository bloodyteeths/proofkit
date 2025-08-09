"""
Test concrete curing pass conditions within 24h window.

Requirements:
- From pass fixture: within first 24h, require temp ∈ [16,27]°C (inclusive) and RH≥95% if spec requires
- PASS if ≥95% of samples satisfy constraints
"""

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta

from core.metrics_concrete import validate_concrete_curing
from core.models import SpecV1


class TestConcretePass24HWindow:
    """Test concrete curing validation within 24-hour window."""

    def test_pass_fixture_24h_window_temp_only(self):
        """Test pass fixture meets 24h window temperature requirements without RH."""
        # Load pass fixture data
        pass_csv_path = "/Users/tamsar/Downloads/csv SaaS/audit/fixtures/concrete/pass.csv"
        pass_json_path = "/Users/tamsar/Downloads/csv SaaS/audit/fixtures/concrete/pass.json"
        
        # Load CSV data
        df = pd.read_csv(pass_csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Load spec
        import json
        with open(pass_json_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        # Define 24h window from first timestamp
        start_time = df['timestamp'].iloc[0]
        window_24h = start_time + timedelta(hours=24)
        
        # Filter to first 24h
        df_24h = df[df['timestamp'] <= window_24h].copy()
        
        # Check temperature constraints [16, 27]°C on all sensor columns
        temp_cols = [col for col in df_24h.columns if col != 'timestamp']
        
        # Calculate percentage of samples meeting temp constraints
        samples_meeting_constraints = 0
        total_samples = len(df_24h)
        
        for _, row in df_24h.iterrows():
            temp_values = [row[col] for col in temp_cols if pd.notna(row[col])]
            if temp_values:
                # All sensors must be in range for sample to pass
                all_in_range = all(16.0 <= temp <= 27.0 for temp in temp_values)
                if all_in_range:
                    samples_meeting_constraints += 1
        
        pct_ok = (samples_meeting_constraints / total_samples) * 100 if total_samples > 0 else 0
        
        # Verify ≥95% compliance
        assert pct_ok >= 95.0, f"Temperature compliance {pct_ok:.1f}% < 95% required"
        
        # Test actual validation function
        result = validate_concrete_curing(df_24h, spec)
        assert result.status == 'PASS', f"Expected PASS, got {result.status}: {result.reasons}"

    def test_pass_fixture_24h_window_with_rh_requirement(self):
        """Test pass fixture with RH requirement (should be INDETERMINATE if no RH data)."""
        # Load pass fixture data
        pass_csv_path = "/Users/tamsar/Downloads/csv SaaS/audit/fixtures/concrete/pass.csv"
        pass_json_path = "/Users/tamsar/Downloads/csv SaaS/audit/fixtures/concrete/pass.json"
        
        # Load CSV data
        df = pd.read_csv(pass_csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Load spec and modify to require humidity
        import json
        with open(pass_json_path, 'r') as f:
            spec_data = json.load(f)
        
        # Add humidity requirement
        spec_data['parameter_requirements'] = {'require_humidity': True}
        spec = SpecV1(**spec_data)
        
        # Since pass fixture has no RH data, should be INDETERMINATE
        result = validate_concrete_curing(df, spec)
        assert result.status == 'INDETERMINATE', f"Expected INDETERMINATE when RH required but missing, got {result.status}"

    def test_pass_fixture_24h_window_with_rh_data(self):
        """Test pass fixture with synthetic RH data meeting ≥95% requirement."""
        # Load pass fixture data
        pass_csv_path = "/Users/tamsar/Downloads/csv SaaS/audit/fixtures/concrete/pass.csv"
        pass_json_path = "/Users/tamsar/Downloads/csv SaaS/audit/fixtures/concrete/pass.json"
        
        # Load CSV data
        df = pd.read_csv(pass_csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Add synthetic RH data ≥95%
        df['humidity_rh'] = 96.5  # All samples at 96.5% RH
        
        # Load spec with humidity requirement
        import json
        with open(pass_json_path, 'r') as f:
            spec_data = json.load(f)
        
        spec_data['parameter_requirements'] = {'require_humidity': True}
        spec = SpecV1(**spec_data)
        
        # Define 24h window from first timestamp
        start_time = df['timestamp'].iloc[0]
        window_24h = start_time + timedelta(hours=24)
        
        # Filter to first 24h
        df_24h = df[df['timestamp'] <= window_24h].copy()
        
        # Calculate compliance for both temp and RH
        temp_cols = [col for col in df_24h.columns if col not in ['timestamp', 'humidity_rh']]
        
        samples_meeting_constraints = 0
        total_samples = len(df_24h)
        
        for _, row in df_24h.iterrows():
            temp_values = [row[col] for col in temp_cols if pd.notna(row[col])]
            rh_value = row['humidity_rh']
            
            if temp_values and pd.notna(rh_value):
                # All sensors must be in temp range [16, 27]°C AND RH ≥ 95%
                all_temp_in_range = all(16.0 <= temp <= 27.0 for temp in temp_values)
                rh_in_range = rh_value >= 95.0
                
                if all_temp_in_range and rh_in_range:
                    samples_meeting_constraints += 1
        
        pct_ok = (samples_meeting_constraints / total_samples) * 100 if total_samples > 0 else 0
        
        # Verify ≥95% compliance
        assert pct_ok >= 95.0, f"Combined temp+RH compliance {pct_ok:.1f}% < 95% required"
        
        # Test actual validation function
        result = validate_concrete_curing(df_24h, spec)
        assert result.status == 'PASS', f"Expected PASS, got {result.status}: {result.reasons}"

    def test_fail_insufficient_samples(self):
        """Test INDETERMINATE when insufficient samples (<10)."""
        # Create minimal dataset with only 5 samples
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01T10:00:00Z', periods=5, freq='1H'),
            'sensor_1': [20.0, 21.0, 22.0, 19.0, 23.0]
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_insufficient"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 172800,
                "temp_band_C": {"min": 5.0, "max": 35.0},
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 1800.0,
                "allowed_gaps_s": 7200.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 1
            }
        }
        spec = SpecV1(**spec_data)
        
        # Should be INDETERMINATE due to insufficient samples
        result = validate_concrete_curing(df, spec)
        assert result.status == 'INDETERMINATE' or result.status == 'FAIL'
        assert any("Insufficient" in reason for reason in result.reasons)

    def test_fail_temp_out_of_range(self):
        """Test FAIL when <95% of samples meet temperature constraints."""
        # Create dataset where many samples are out of [16, 27]°C range
        df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01T10:00:00Z', periods=100, freq='15min'),
            'sensor_1': [15.0] * 50 + [20.0] * 50  # 50% below 16°C, 50% in range
        })
        
        spec_data = {
            "version": "1.0",
            "industry": "concrete",
            "job": {"job_id": "test_temp_fail"},
            "spec": {
                "method": "AMBIENT_CURE",
                "target_temp_C": 18.0,
                "hold_time_s": 172800,
                "temp_band_C": {"min": 5.0, "max": 35.0},
                "sensor_uncertainty_C": 1.0
            },
            "data_requirements": {
                "max_sample_period_s": 1800.0,
                "allowed_gaps_s": 7200.0
            },
            "sensor_selection": {
                "mode": "mean",
                "require_at_least": 1
            }
        }
        spec = SpecV1(**spec_data)
        
        # Should FAIL due to insufficient temperature compliance
        result = validate_concrete_curing(df, spec)
        assert result.status == 'FAIL', f"Expected FAIL, got {result.status}"
        assert any("Temperature" in reason and ("16-27" in reason or "range" in reason) for reason in result.reasons)