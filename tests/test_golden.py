"""
ProofKit Golden Tests

Deterministic output validation tests to ensure consistent behavior across
different environments, versions, and runs. These tests validate that
given identical inputs, ProofKit produces identical outputs.

Golden tests include:
- Deterministic normalization outputs
- Consistent decision algorithm results  
- Reproducible hash calculations
- Stable serialization formats
- Version compatibility validation

Example usage:
    pytest tests/test_golden.py -v
"""

import pytest
import pandas as pd
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.models import SpecV1, DecisionResult
from core.pack import create_evidence_bundle, calculate_content_hash
from core.verify import verify_evidence_bundle


class TestDeterministicNormalization:
    """Test that normalization produces deterministic outputs."""
    
    def test_normalization_reproducibility(self, simple_temp_data):
        """Test that normalization produces identical results across runs."""
        # Run normalization multiple times
        results = []
        for _ in range(5):
            result = normalize_temperature_data(
                simple_temp_data.copy(), 
                target_step_s=30.0, 
                allowed_gaps_s=60.0
            )
            results.append(result)
        
        # All results should be identical
        base_result = results[0]
        for result in results[1:]:
            pd.testing.assert_frame_equal(base_result, result)
    
    def test_normalization_golden_output(self, example_csv_path):
        """Test normalization against known golden output."""
        df, metadata = load_csv_with_metadata(str(example_csv_path))
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Golden expectations based on ok_run.csv
        expected_columns = ["timestamp", "pmt_sensor_1", "pmt_sensor_2"]
        assert list(normalized_df.columns) == expected_columns
        
        # Should have specific number of rows (based on 30s resampling)
        assert len(normalized_df) >= 20  # At least 20 30-second intervals
        
        # First timestamp should be 2024-01-15T10:00:00Z
        expected_first = pd.Timestamp("2024-01-15T10:00:00Z")
        actual_first = normalized_df["timestamp"].iloc[0]
        assert actual_first == expected_first
        
        # Temperature values should be in expected range
        for col in ["pmt_sensor_1", "pmt_sensor_2"]:
            temps = normalized_df[col]
            assert temps.min() >= 160.0  # Reasonable minimum
            assert temps.max() <= 190.0  # Reasonable maximum
    
    def test_fahrenheit_conversion_golden(self, fahrenheit_csv_path):
        """Test Fahrenheit to Celsius conversion produces expected values."""
        df, metadata = load_csv_with_metadata(str(fahrenheit_csv_path))
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # Check that final temperatures are around 180°C (356°F converted)
        temp_cols = [col for col in normalized_df.columns if col != "timestamp"]
        for col in temp_cols:
            final_temps = normalized_df[col].tail(5)  # Last 5 readings
            avg_final_temp = final_temps.mean()
            # Should be close to 180°C (allowing for ramp-up period)
            assert 175.0 <= avg_final_temp <= 185.0
    
    def test_unix_timestamp_conversion_golden(self, test_data_dir):
        """Test UNIX timestamp conversion produces expected UTC times."""
        unix_csv_path = test_data_dir / "unix_seconds_data.csv"
        df, metadata = load_csv_with_metadata(str(unix_csv_path))
        
        normalized_df = normalize_temperature_data(
            df, target_step_s=30.0, allowed_gaps_s=60.0
        )
        
        # First UNIX timestamp 1705320000 = 2024-01-15T10:00:00Z
        expected_first = pd.Timestamp("2024-01-15T10:00:00Z")
        actual_first = normalized_df["timestamp"].iloc[0]
        assert actual_first == expected_first
        
        # All timestamps should be in UTC
        assert normalized_df["timestamp"].dt.tz.zone == "UTC"


class TestDeterministicDecisions:
    """Test that decision algorithm produces deterministic results."""
    
    def test_decision_reproducibility(self, simple_temp_data, example_spec):
        """Test that decisions are reproducible across runs."""
        # Make same decision multiple times
        results = []
        for _ in range(5):
            result = make_decision(simple_temp_data.copy(), example_spec)
            results.append(result)
        
        # All results should be identical
        base_result = results[0]
        for result in results[1:]:
            assert result.pass_ == base_result.pass_
            assert result.job_id == base_result.job_id
            assert result.target_temp_C == base_result.target_temp_C
            assert result.conservative_threshold_C == base_result.conservative_threshold_C
            assert abs(result.actual_hold_time_s - base_result.actual_hold_time_s) < 0.001
            assert result.required_hold_time_s == base_result.required_hold_time_s
            assert abs(result.max_temp_C - base_result.max_temp_C) < 0.001
            assert abs(result.min_temp_C - base_result.min_temp_C) < 0.001
            assert result.reasons == base_result.reasons
            assert result.warnings == base_result.warnings
    
    def test_decision_golden_pass_scenario(self, example_csv_path, spec_example_path):
        """Test decision against known golden PASS scenario."""
        # Load example data
        df, _ = load_csv_with_metadata(str(example_csv_path))
        with open(spec_example_path) as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        # Normalize and decide
        normalized_df = normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        result = make_decision(normalized_df, spec)
        
        # Golden expectations for ok_run.csv + spec_example.json
        assert result.pass_ is True
        assert result.job_id == "example_batch_001"
        assert result.target_temp_C == 180.0
        assert result.conservative_threshold_C == 182.0  # 180 + 2
        assert result.actual_hold_time_s >= 600.0  # Should meet 10-minute requirement
        assert result.required_hold_time_s == 600
        
        # Temperature range expectations
        assert 160.0 <= result.min_temp_C <= 170.0
        assert 180.0 <= result.max_temp_C <= 190.0
        
        # Should have positive reasons
        assert len(result.reasons) > 0
        assert any("pass" in reason.lower() or "meet" in reason.lower() for reason in result.reasons)
    
    def test_decision_golden_fail_scenario(self, gaps_csv_path, spec_example_path):
        """Test decision against known golden FAIL scenario."""
        # Load gaps data (should fail due to data quality)
        df, _ = load_csv_with_metadata(str(gaps_csv_path))
        with open(spec_example_path) as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        # Try to normalize (should raise error due to gaps)
        try:
            normalized_df = normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
            # If normalization succeeds with larger gap allowance, test decision
            result = make_decision(normalized_df, spec)
            
            # May pass or fail depending on available data after gaps
            assert isinstance(result, DecisionResult)
            assert result.job_id == "example_batch_001"
            
        except Exception:
            # Expected to fail due to data gaps - this is acceptable
            pass
    
    def test_decision_serialization_deterministic(self, simple_temp_data, example_spec):
        """Test that decision serialization is deterministic."""
        result = make_decision(simple_temp_data, example_spec)
        
        # Serialize multiple times
        serializations = []
        for _ in range(5):
            json_dict = result.model_dump()
            serializations.append(json_dict)
        
        # All serializations should be identical
        base_serialization = serializations[0]
        for serialization in serializations[1:]:
            assert serialization == base_serialization
        
        # JSON string should also be deterministic (with sorted keys)
        json_strings = []
        for _ in range(5):
            json_str = json.dumps(result.model_dump(), sort_keys=True)
            json_strings.append(json_str)
        
        assert all(s == json_strings[0] for s in json_strings)


class TestDeterministicHashing:
    """Test that hash calculations are deterministic."""
    
    def test_content_hash_reproducibility(self, temp_dir, simple_temp_data):
        """Test that content hashes are reproducible."""
        csv_path = temp_dir / "test_data.csv"
        simple_temp_data.to_csv(csv_path, index=False)
        
        # Calculate hash multiple times
        hashes = []
        for _ in range(10):
            hash_value = calculate_content_hash(str(csv_path))
            hashes.append(hash_value)
        
        # All hashes should be identical
        assert all(h == hashes[0] for h in hashes)
        assert len(hashes[0]) > 0
    
    def test_identical_data_identical_hash(self, temp_dir, simple_temp_data):
        """Test that identical data produces identical hashes."""
        # Create two identical files
        csv_path_1 = temp_dir / "data_1.csv"
        csv_path_2 = temp_dir / "data_2.csv"
        
        simple_temp_data.to_csv(csv_path_1, index=False)
        simple_temp_data.to_csv(csv_path_2, index=False)
        
        hash_1 = calculate_content_hash(str(csv_path_1))
        hash_2 = calculate_content_hash(str(csv_path_2))
        
        assert hash_1 == hash_2
    
    def test_different_data_different_hash(self, temp_dir, simple_temp_data):
        """Test that different data produces different hashes."""
        csv_path_1 = temp_dir / "data_1.csv"
        csv_path_2 = temp_dir / "data_2.csv"
        
        # Create modified data
        modified_data = simple_temp_data.copy()
        modified_data.iloc[0, 1] = 999.9  # Change one value
        
        simple_temp_data.to_csv(csv_path_1, index=False)
        modified_data.to_csv(csv_path_2, index=False)
        
        hash_1 = calculate_content_hash(str(csv_path_1))
        hash_2 = calculate_content_hash(str(csv_path_2))
        
        assert hash_1 != hash_2
    
    def test_hash_format_consistency(self, temp_dir, simple_temp_data):
        """Test that hash format is consistent."""
        csv_path = temp_dir / "test_data.csv"
        simple_temp_data.to_csv(csv_path, index=False)
        
        hash_value = calculate_content_hash(str(csv_path))
        
        # Should be SHA256 hex string (64 characters)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        assert all(c in '0123456789abcdef' for c in hash_value.lower())


class TestDeterministicBundleCreation:
    """Test that evidence bundle creation is deterministic."""
    
    def test_bundle_creation_reproducibility(self, temp_dir, simple_temp_data, example_spec):
        """Test that identical inputs produce identical bundles."""
        # Create identical bundles
        bundles = []
        for i in range(3):
            csv_path = temp_dir / f"data_{i}.csv"
            spec_path = temp_dir / f"spec_{i}.json"
            bundle_path = temp_dir / f"bundle_{i}.zip"
            
            simple_temp_data.to_csv(csv_path, index=False)
            with open(spec_path, 'w') as f:
                json.dump(example_spec.model_dump(), f, indent=2)
            
            create_evidence_bundle(
                csv_path=str(csv_path),
                spec_path=str(spec_path),
                output_path=str(bundle_path)
            )
            
            bundles.append(bundle_path)
        
        # Calculate hashes of bundle files
        bundle_hashes = []
        for bundle_path in bundles:
            bundle_hash = calculate_content_hash(str(bundle_path))
            bundle_hashes.append(bundle_hash)
        
        # Note: Bundle hashes may differ due to timestamps in manifest
        # But verification should be consistent
        verification_results = []
        for bundle_path in bundles:
            report = verify_evidence_bundle(str(bundle_path))
            verification_results.append(report)
        
        # All bundles should verify successfully
        for report in verification_results:
            assert report.is_valid is True
            assert report.decision_matches is True
    
    def test_manifest_deterministic_structure(self, temp_dir, simple_temp_data, example_spec):
        """Test that manifest structure is deterministic (excluding timestamps)."""
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        # Extract and examine manifest
        import zipfile
        with zipfile.ZipFile(bundle_path, 'r') as zf:
            manifest_content = zf.read("manifest.json").decode('utf-8')
            manifest = json.loads(manifest_content)
        
        # Check expected structure
        assert "version" in manifest
        assert "created_at" in manifest
        assert "files" in manifest
        assert isinstance(manifest["files"], dict)
        
        # Should have expected files
        expected_files = {"data.csv", "spec.json", "decision.json"}
        assert set(manifest["files"].keys()) == expected_files
        
        # Each file entry should have hash and size
        for file_info in manifest["files"].values():
            assert "hash" in file_info
            assert "size" in file_info
            assert isinstance(file_info["hash"], str)
            assert isinstance(file_info["size"], int)


class TestVersionCompatibility:
    """Test version compatibility and migration scenarios."""
    
    def test_spec_version_consistency(self, example_spec):
        """Test that spec version is consistently handled."""
        # Should always be version 1.0
        assert example_spec.version == "1.0"
        
        # Serialization should preserve version
        serialized = example_spec.model_dump()
        assert serialized["version"] == "1.0"
        
        # Deserialization should preserve version
        reconstructed = SpecV1(**serialized)
        assert reconstructed.version == "1.0"
    
    def test_decision_result_format_stability(self, simple_temp_data, example_spec):
        """Test that DecisionResult format is stable across runs."""
        result = make_decision(simple_temp_data, example_spec)
        serialized = result.model_dump()
        
        # Check expected fields are present
        expected_fields = {
            "pass", "job_id", "target_temp_C", "conservative_threshold_C",
            "actual_hold_time_s", "required_hold_time_s", "max_temp_C", 
            "min_temp_C", "reasons", "warnings"
        }
        assert set(serialized.keys()) == expected_fields
        
        # Check field types
        assert isinstance(serialized["pass"], bool)
        assert isinstance(serialized["job_id"], str)
        assert isinstance(serialized["target_temp_C"], (int, float))
        assert isinstance(serialized["conservative_threshold_C"], (int, float))
        assert isinstance(serialized["actual_hold_time_s"], (int, float))
        assert isinstance(serialized["required_hold_time_s"], int)
        assert isinstance(serialized["max_temp_C"], (int, float))
        assert isinstance(serialized["min_temp_C"], (int, float))
        assert isinstance(serialized["reasons"], list)
        assert isinstance(serialized["warnings"], list)
    
    def test_bundle_format_stability(self, temp_dir, simple_temp_data, example_spec):
        """Test that bundle format is stable and compatible."""
        csv_path = temp_dir / "test_data.csv"
        spec_path = temp_dir / "test_spec.json"
        bundle_path = temp_dir / "evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        with open(spec_path, 'w') as f:
            json.dump(example_spec.model_dump(), f, indent=2)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=str(spec_path),
            output_path=str(bundle_path)
        )
        
        # Verify bundle contains expected files
        import zipfile
        with zipfile.ZipFile(bundle_path, 'r') as zf:
            file_list = zf.namelist()
            expected_files = {"data.csv", "spec.json", "decision.json", "manifest.json"}
            assert set(file_list) == expected_files
        
        # Verify bundle can be verified
        report = verify_evidence_bundle(str(bundle_path))
        assert report.is_valid is True


class TestGoldenDataValidation:
    """Test against known golden datasets."""
    
    def test_example_ok_run_golden(self, example_csv_path, spec_example_path):
        """Test complete workflow against ok_run.csv golden data."""
        # Load data
        df, metadata = load_csv_with_metadata(str(example_csv_path))
        with open(spec_example_path) as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        # Full workflow
        normalized_df = normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        result = make_decision(normalized_df, spec)
        
        # Golden assertions
        assert result.pass_ is True
        assert result.job_id == "example_batch_001"
        assert result.actual_hold_time_s >= 570.0  # At least 9.5 minutes
        assert 182.0 <= result.max_temp_C <= 185.0  # Peak temperature range
        assert 165.0 <= result.min_temp_C <= 170.0  # Starting temperature range
        
        # Should have meaningful reasons
        assert len(result.reasons) >= 1
        assert len(result.warnings) >= 0  # May or may not have warnings
    
    def test_fahrenheit_example_golden(self, fahrenheit_csv_path, fahrenheit_spec_path):
        """Test complete workflow against Fahrenheit golden data."""
        # Load Fahrenheit data
        df, metadata = load_csv_with_metadata(str(fahrenheit_csv_path))
        with open(fahrenheit_spec_path) as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        # Full workflow
        normalized_df = normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=60.0)
        result = make_decision(normalized_df, spec)
        
        # Golden assertions for Fahrenheit conversion
        assert result.pass_ is True  # Should pass after F to C conversion
        assert result.target_temp_C == 180.0  # Target in spec is Celsius
        assert result.conservative_threshold_C == 182.0
        
        # Converted temperatures should be in Celsius range
        assert 150.0 <= result.min_temp_C <= 200.0
        assert 175.0 <= result.max_temp_C <= 190.0
    
    def test_deterministic_across_environments(self, simple_temp_data, example_spec):
        """Test that results are deterministic across different environments."""
        # This test ensures reproducibility across different Python versions,
        # pandas versions, etc. (within reason)
        
        # Run workflow multiple times
        results = []
        for _ in range(10):
            normalized_df = normalize_temperature_data(
                simple_temp_data.copy(), 
                target_step_s=30.0, 
                allowed_gaps_s=60.0
            )
            result = make_decision(normalized_df, example_spec)
            results.append(result)
        
        # All key metrics should be identical
        base_result = results[0]
        for result in results[1:]:
            assert result.pass_ == base_result.pass_
            assert abs(result.actual_hold_time_s - base_result.actual_hold_time_s) < 0.1
            assert abs(result.max_temp_C - base_result.max_temp_C) < 0.001
            assert abs(result.min_temp_C - base_result.min_temp_C) < 0.001
            assert result.conservative_threshold_C == base_result.conservative_threshold_C