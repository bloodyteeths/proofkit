#!/usr/bin/env python3
"""
Test examples compilation to ensure all examples produce valid PDFs.

Verifies that each industry has working PASS and FAIL examples that compile
successfully through the complete ProofKit pipeline.
"""

import os
import json
import pytest
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from core.normalize import normalize_temperature_data
from core.decide import decide_pass_fail
from core.render_pdf import render_proof_certificate
from core.pack import create_evidence_bundle
from core.verify import verify_evidence_bundle


class TestExamplesCompilation:
    """Test suite to verify all examples compile successfully."""
    
    @pytest.fixture(scope="class")
    def examples_dir(self) -> Path:
        """Get examples directory path."""
        return Path(__file__).parent.parent.parent / "examples"
    
    @pytest.fixture(scope="class") 
    def industry_examples(self, examples_dir: Path) -> Dict[str, Dict[str, List[Tuple[str, str]]]]:
        """
        Map of industries to their PASS/FAIL examples.
        
        Returns:
            Dict mapping industry -> {"pass": [(csv, spec)], "fail": [(csv, spec)]}
        """
        examples = {
            "powder": {
                "pass": [
                    ("powder_coat_cure_successful_180c_10min_pass.csv", "powder_coat_cure_spec_standard_180c_10min.json"),
                    ("powder_coat_cure_cumulative_hold_pass_170c_20min.csv", "powder_coat_cure_spec_cumulative_hold_170c_20min.json"),
                    ("powder_coat_cure_fahrenheit_input_356f_10min_pass.csv", "powder_coat_cure_spec_fahrenheit_input_356f_10min.json"),
                    ("powder_pass_fixed.csv", "powder_pass_spec_fixed.json")
                ],
                "fail": [
                    ("powder_coat_cure_insufficient_hold_time_fail.csv", "powder_coat_cure_spec_standard_180c_10min.json"),
                    ("powder_coat_cure_data_gaps_sensor_disconnect_fail.csv", "powder_coat_cure_spec_standard_180c_10min.json"),
                    ("powder_coat_cure_slow_ramp_rate_fail.csv", "powder_coat_cure_spec_standard_180c_10min.json"),
                    ("powder_coat_cure_sensor_failure_mid_run_fail.csv", "powder_coat_cure_spec_standard_180c_10min.json")
                ]
            },
            "autoclave": {
                "pass": [
                    ("autoclave_sterilization_pass.csv", "autoclave-medical-device-validation.json")
                ],
                "fail": [
                    ("autoclave_sterilization_fail.csv", "autoclave-medical-device-validation.json")
                ],
                "indeterminate": [
                    ("autoclave_missing_pressure_indeterminate.csv", "autoclave-medical-device-validation.json")
                ]
            },
            "concrete": {
                "pass": [
                    ("concrete_curing_pass.csv", "concrete-curing-astm-c31.json")
                ],
                "fail": [
                    ("concrete_curing_fail.csv", "concrete-curing-astm-c31.json")
                ]
            },
            "coldchain": {
                "pass": [
                    ("coldchain_storage_pass.csv", "coldchain-storage-validation.json")
                ],
                "fail": [
                    ("coldchain_storage_fail.csv", "coldchain-storage-validation.json")
                ]
            },
            "haccp": {
                "pass": [
                    ("haccp_cooling_pass.csv", "haccp-cooling-validation.json")
                ],
                "fail": [
                    ("haccp_cooling_fail.csv", "haccp-cooling-validation.json")
                ]
            },
            "sterile": {
                "pass": [
                    ("sterile_processing_pass.csv", "sterile-processing-validation.json")
                ],
                "fail": [
                    ("sterile_processing_fail.csv", "sterile-processing-validation.json")
                ]
            }
        }
        
        # Verify all files exist
        for industry, categories in examples.items():
            for category, file_pairs in categories.items():
                for csv_file, spec_file in file_pairs:
                    csv_path = examples_dir / csv_file
                    spec_path = examples_dir / spec_file
                    
                    if not csv_path.exists():
                        pytest.skip(f"Missing CSV file: {csv_path}")
                    if not spec_path.exists():
                        pytest.skip(f"Missing spec file: {spec_path}")
                        
        return examples

    @pytest.mark.parametrize("industry", ["powder", "autoclave", "concrete", "coldchain", "haccp", "sterile"])
    def test_industry_has_examples(self, industry: str, industry_examples: Dict):
        """Test that each industry has at least one PASS and one FAIL example."""
        assert industry in industry_examples, f"Missing examples for industry: {industry}"
        
        examples = industry_examples[industry]
        assert "pass" in examples and examples["pass"], f"No PASS examples for {industry}"
        assert "fail" in examples and examples["fail"], f"No FAIL examples for {industry}"
        
        print(f"✅ {industry}: {len(examples['pass'])} PASS, {len(examples['fail'])} FAIL examples")

    @pytest.mark.parametrize("industry,category,csv_file,spec_file", [
        pytest.param(industry, category, csv_file, spec_file, id=f"{industry}_{category}_{csv_file[:20]}")
        for industry, categories in {
            "powder": {
                "pass": [
                    ("powder_coat_cure_successful_180c_10min_pass.csv", "powder_coat_cure_spec_standard_180c_10min.json"),
                    ("powder_pass_fixed.csv", "powder_pass_spec_fixed.json")
                ],
                "fail": [
                    ("powder_coat_cure_insufficient_hold_time_fail.csv", "powder_coat_cure_spec_standard_180c_10min.json")
                ]
            },
            "autoclave": {
                "pass": [("autoclave_sterilization_pass.csv", "autoclave-medical-device-validation.json")],
                "fail": [("autoclave_sterilization_fail.csv", "autoclave-medical-device-validation.json")]
            },
            "concrete": {
                "pass": [("concrete_curing_pass.csv", "concrete-curing-astm-c31.json")],
                "fail": [("concrete_curing_fail.csv", "concrete-curing-astm-c31.json")]
            },
            "coldchain": {
                "pass": [("coldchain_storage_pass.csv", "coldchain-storage-validation.json")],
                "fail": [("coldchain_storage_fail.csv", "coldchain-storage-validation.json")]
            },
            "haccp": {
                "pass": [("haccp_cooling_pass.csv", "haccp-cooling-validation.json")],
                "fail": [("haccp_cooling_fail.csv", "haccp-cooling-validation.json")]
            },
            "sterile": {
                "pass": [("sterile_processing_pass.csv", "sterile-processing-validation.json")],
                "fail": [("sterile_processing_fail.csv", "sterile-processing-validation.json")]
            }
        }.items()
        for category, file_pairs in categories.items()
        for csv_file, spec_file in file_pairs
    ])
    def test_example_compiles_to_pdf(
        self, 
        industry: str, 
        category: str, 
        csv_file: str, 
        spec_file: str, 
        examples_dir: Path,
        tmp_path: Path
    ):
        """Test that each example compiles successfully through the full pipeline."""
        csv_path = examples_dir / csv_file
        spec_path = examples_dir / spec_file
        
        # Skip if files don't exist (fixture should catch this, but double-check)
        if not csv_path.exists() or not spec_path.exists():
            pytest.skip(f"Missing files: {csv_path.exists()=}, {spec_path.exists()=}")
        
        # Load specification
        with open(spec_path, 'r') as f:
            spec = json.load(f)
        
        # Step 1: Load and normalize CSV data
        df_raw = pd.read_csv(csv_path)
        assert not df_raw.empty, f"Empty CSV file: {csv_file}"
        
        df_normalized = normalize_temperature_data(df_raw, spec)
        assert not df_normalized.empty, f"Normalization failed for: {csv_file}"
        
        # Step 2: Make pass/fail decision
        decision = decide_pass_fail(df_normalized, spec)
        assert decision is not None, f"Decision failed for: {csv_file}"
        assert "result" in decision, f"No result in decision for: {csv_file}"
        
        # Step 3: Render PDF certificate
        pdf_path = tmp_path / f"{csv_file.stem}_proof.pdf"
        render_proof_certificate(
            decision=decision,
            normalized_data=df_normalized,
            spec=spec,
            output_path=str(pdf_path)
        )
        assert pdf_path.exists(), f"PDF rendering failed for: {csv_file}"
        assert pdf_path.stat().st_size > 1024, f"PDF too small for: {csv_file}"
        
        # Step 4: Create evidence bundle
        bundle_path = tmp_path / f"{csv_file.stem}_evidence.zip"
        create_evidence_bundle(
            raw_csv_path=str(csv_path),
            spec_json_path=str(spec_path),
            normalized_csv=df_normalized,
            decision_json=decision,
            proof_pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        assert bundle_path.exists(), f"Evidence bundle creation failed for: {csv_file}"
        
        # Step 5: Verify evidence bundle
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["verified"], f"Evidence verification failed for: {csv_file}"
        
        # Verify expected outcome matches
        expected_result = "pass" if category == "pass" else "fail" if category == "fail" else "indeterminate"
        actual_result = decision["result"].lower()
        
        if category != "indeterminate":  # Skip outcome check for indeterminate cases
            assert actual_result == expected_result, (
                f"Expected {expected_result} but got {actual_result} for {csv_file} "
                f"(industry: {industry}, category: {category})"
            )
        
        print(f"✅ {industry} {category}: {csv_file} -> {actual_result} (PDF: {pdf_path.stat().st_size} bytes)")

    def test_all_industries_covered(self, industry_examples: Dict):
        """Test that all 5 required industries have examples."""
        required_industries = {"powder", "autoclave", "concrete", "coldchain", "haccp", "sterile"}
        available_industries = set(industry_examples.keys())
        
        missing = required_industries - available_industries
        assert not missing, f"Missing examples for industries: {missing}"
        
        print(f"✅ All {len(required_industries)} industries have examples")

    def test_examples_directory_structure(self, examples_dir: Path):
        """Test that examples directory has proper structure."""
        assert examples_dir.exists(), f"Examples directory does not exist: {examples_dir}"
        
        # Check for README
        readme_path = examples_dir / "README.md"
        assert readme_path.exists(), "Examples README.md is missing"
        
        # Check for outputs directory
        outputs_dir = examples_dir / "outputs"
        if outputs_dir.exists():
            print(f"✅ Outputs directory exists with {len(list(outputs_dir.glob('*')))} files")
        
        # Count total files
        csv_files = list(examples_dir.glob("*.csv"))
        json_files = list(examples_dir.glob("*.json"))
        
        print(f"✅ Examples directory: {len(csv_files)} CSV files, {len(json_files)} JSON files")
        
        assert len(csv_files) >= 10, f"Expected at least 10 CSV files, found {len(csv_files)}"
        assert len(json_files) >= 5, f"Expected at least 5 JSON files, found {len(json_files)}"

    def test_specification_schemas_valid(self, examples_dir: Path):
        """Test that all JSON specifications are valid."""
        json_files = list(examples_dir.glob("*.json"))
        
        for json_file in json_files:
            if json_file.name in ["spec_example.json"]:  # Skip generic examples
                continue
                
            with open(json_file, 'r') as f:
                try:
                    spec = json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in {json_file}: {e}")
            
            # Basic schema checks
            assert "version" in spec, f"Missing version in {json_file}"
            assert "spec" in spec, f"Missing spec section in {json_file}" 
            assert "industry" in spec, f"Missing industry in {json_file}"
            
            industry = spec["industry"]
            assert industry in ["powder", "autoclave", "concrete", "coldchain", "haccp", "sterile"], (
                f"Invalid industry '{industry}' in {json_file}"
            )
            
            print(f"✅ {json_file.name}: valid {industry} specification")

    @pytest.mark.slow
    def test_performance_benchmarks(self, examples_dir: Path, tmp_path: Path):
        """Test that example compilation meets performance benchmarks."""
        import time
        
        # Test with a representative example
        csv_path = examples_dir / "powder_coat_cure_successful_180c_10min_pass.csv"
        spec_path = examples_dir / "powder_coat_cure_spec_standard_180c_10min.json"
        
        if not csv_path.exists() or not spec_path.exists():
            pytest.skip("Performance test files not available")
        
        with open(spec_path, 'r') as f:
            spec = json.load(f)
        
        df_raw = pd.read_csv(csv_path)
        
        # Benchmark normalization
        start_time = time.time()
        df_normalized = normalize_temperature_data(df_raw, spec)
        normalize_time = time.time() - start_time
        
        # Benchmark decision
        start_time = time.time()  
        decision = decide_pass_fail(df_normalized, spec)
        decide_time = time.time() - start_time
        
        # Benchmark PDF rendering
        pdf_path = tmp_path / "benchmark_proof.pdf"
        start_time = time.time()
        render_proof_certificate(decision, df_normalized, spec, str(pdf_path))
        render_time = time.time() - start_time
        
        # Performance assertions (adjust thresholds as needed)
        assert normalize_time < 2.0, f"Normalization too slow: {normalize_time:.2f}s"
        assert decide_time < 1.0, f"Decision too slow: {decide_time:.2f}s"  
        assert render_time < 5.0, f"PDF rendering too slow: {render_time:.2f}s"
        
        total_time = normalize_time + decide_time + render_time
        print(f"✅ Performance: normalize={normalize_time:.2f}s, decide={decide_time:.2f}s, render={render_time:.2f}s (total={total_time:.2f}s)")


if __name__ == "__main__":
    """Run examples compilation tests directly."""
    pytest.main([__file__, "-v", "--tb=short"])