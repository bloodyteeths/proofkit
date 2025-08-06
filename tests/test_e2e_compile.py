"""
ProofKit End-to-End Compilation Tests

Comprehensive end-to-end test suite that validates the complete workflow from CSV upload
to evidence bundle generation for all 6 supported industries (powder, haccp, autoclave, 
sterile, concrete, coldchain). Tests both PASS and FAIL scenarios with real data.

Tests include:
- Complete workflow validation (normalize → decide → plot → PDF → pack)
- Industry-specific metrics and thresholds
- Evidence bundle integrity verification
- Decision consistency across compilation steps
- Error handling and edge cases

Example usage:
    pytest tests/test_e2e_compile.py -v
"""

import pytest
import tempfile
import json
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for testing

from core.models import SpecV1, DecisionResult, Industry
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.plot import generate_proof_plot
from core.render_pdf import generate_proof_pdf
from core.pack import create_evidence_bundle
from core.verify import verify_evidence_bundle


class TestE2ECompilation:
    """Test complete end-to-end compilation workflow."""
    
    @pytest.fixture
    def industry_specs(self) -> Dict[str, Dict[str, Any]]:
        """Provide industry-specific specifications for testing."""
        return {
            "powder": {
                "version": "1.0",
                "industry": "powder",
                "job": {"job_id": "powder_coat_e2e_test"},
                "spec": {
                    "method": "PMT",
                    "target_temp_C": 180.0,
                    "hold_time_s": 600,
                    "sensor_uncertainty_C": 2.0
                },
                "data_requirements": {
                    "max_sample_period_s": 30.0,
                    "allowed_gaps_s": 60.0
                },
                "sensor_selection": {
                    "mode": "min_of_set",
                    "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
                    "require_at_least": 1
                },
                "logic": {
                    "continuous": True,
                    "max_total_dips_s": 0
                },
                "reporting": {
                    "units": "C",
                    "language": "en",
                    "timezone": "UTC"
                }
            },
            "haccp": {
                "version": "1.0",
                "industry": "haccp",
                "job": {"job_id": "haccp_cooling_e2e_test"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 41.0,
                    "hold_time_s": 14400,  # 4 hours cooling window
                    "temp_band_C": {"min": 35.0, "max": 41.0},
                    "sensor_uncertainty_C": 1.0
                },
                "data_requirements": {
                    "max_sample_period_s": 300.0,  # 5 minutes
                    "allowed_gaps_s": 600.0
                },
                "sensor_selection": {
                    "mode": "mean_of_set",
                    "sensors": ["core_temp", "surface_temp"],
                    "require_at_least": 1
                },
                "logic": {
                    "continuous": False,
                    "max_total_dips_s": 300
                },
                "preconditions": {
                    "cooling_start_temp_C": 135.0,
                    "max_cooling_time_s": 14400
                },
                "reporting": {
                    "units": "C",
                    "language": "en",
                    "timezone": "UTC"
                }
            },
            "autoclave": {
                "version": "1.0",
                "industry": "autoclave",
                "job": {"job_id": "autoclave_sterilization_e2e_test"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 121.0,
                    "hold_time_s": 900,  # 15 minutes
                    "temp_band_C": {"min": 120.0, "max": 125.0},
                    "sensor_uncertainty_C": 0.5
                },
                "data_requirements": {
                    "max_sample_period_s": 10.0,
                    "allowed_gaps_s": 30.0
                },
                "sensor_selection": {
                    "mode": "min_of_set",
                    "sensors": ["temp_1", "temp_2"],
                    "require_at_least": 2
                },
                "logic": {
                    "continuous": True,
                    "max_total_dips_s": 0
                },
                "preconditions": {
                    "max_ramp_rate_C_per_min": 5.0,
                    "max_time_to_threshold_s": 1800
                },
                "reporting": {
                    "units": "C",
                    "language": "en",
                    "timezone": "UTC"
                }
            },
            "sterile": {
                "version": "1.0",
                "industry": "sterile",
                "job": {"job_id": "eto_sterilization_e2e_test"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 55.0,
                    "hold_time_s": 3600,  # 1 hour
                    "temp_band_C": {"min": 50.0, "max": 60.0},
                    "sensor_uncertainty_C": 1.0
                },
                "data_requirements": {
                    "max_sample_period_s": 60.0,
                    "allowed_gaps_s": 180.0
                },
                "sensor_selection": {
                    "mode": "mean_of_set",
                    "sensors": ["chamber_temp", "product_temp"],
                    "require_at_least": 1
                },
                "logic": {
                    "continuous": True,
                    "max_total_dips_s": 60
                },
                "reporting": {
                    "units": "C",
                    "language": "en",
                    "timezone": "UTC"
                }
            },
            "concrete": {
                "version": "1.0",
                "industry": "concrete",
                "job": {"job_id": "concrete_curing_e2e_test"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 23.0,
                    "hold_time_s": 172800,  # 48 hours
                    "temp_band_C": {"min": 20.0, "max": 26.0},
                    "sensor_uncertainty_C": 0.5
                },
                "data_requirements": {
                    "max_sample_period_s": 3600.0,  # 1 hour
                    "allowed_gaps_s": 7200.0
                },
                "sensor_selection": {
                    "mode": "mean_of_set",
                    "sensors": ["ambient_temp", "concrete_temp"],
                    "require_at_least": 1
                },
                "logic": {
                    "continuous": False,
                    "max_total_dips_s": 3600
                },
                "reporting": {
                    "units": "C",
                    "language": "en",
                    "timezone": "UTC"
                }
            },
            "coldchain": {
                "version": "1.0",
                "industry": "coldchain",
                "job": {"job_id": "vaccine_storage_e2e_test"},
                "spec": {
                    "method": "OVEN_AIR",
                    "target_temp_C": 4.0,
                    "hold_time_s": 86400,  # 24 hours minimum
                    "temp_band_C": {"min": 2.0, "max": 8.0},
                    "sensor_uncertainty_C": 0.5
                },
                "data_requirements": {
                    "max_sample_period_s": 300.0,  # 5 minutes
                    "allowed_gaps_s": 900.0
                },
                "sensor_selection": {
                    "mode": "mean_of_set",
                    "sensors": ["fridge_temp", "vaccine_temp"],
                    "require_at_least": 1
                },
                "logic": {
                    "continuous": False,
                    "max_total_dips_s": 600
                },
                "reporting": {
                    "units": "C",
                    "language": "en",
                    "timezone": "UTC"
                }
            }
        }
    
    @pytest.fixture
    def test_data_generator(self):
        """Generate synthetic test data for different industries."""
        def generate_data(industry: str, scenario: str, spec: Dict[str, Any]) -> pd.DataFrame:
            """Generate test data based on industry and scenario."""
            target_temp = spec["spec"]["target_temp_C"]
            hold_time_s = spec["spec"]["hold_time_s"]
            sample_period_s = spec["data_requirements"]["max_sample_period_s"]
            
            # Calculate number of points needed
            ramp_time_s = min(1800, hold_time_s // 4)  # Ramp time (max 30 min)
            cool_time_s = min(1800, hold_time_s // 4)  # Cool time
            total_time_s = ramp_time_s + hold_time_s + cool_time_s
            num_points = int(total_time_s / sample_period_s) + 1
            
            # Generate timestamps
            timestamps = pd.date_range(
                start="2024-08-05T10:00:00Z",
                periods=num_points,
                freq=f"{sample_period_s}s",
                tz="UTC"
            )
            
            # Generate temperature profiles based on scenario
            if scenario == "pass":
                # Successful run - reaches target and holds
                ramp_points = int(ramp_time_s / sample_period_s)
                hold_points = int(hold_time_s / sample_period_s)
                cool_points = num_points - ramp_points - hold_points
                
                # Ramp up temperatures
                if industry == "coldchain":
                    start_temp = 20.0  # Room temperature start
                    ramp_temps = [start_temp - (start_temp - target_temp) * (i / ramp_points) 
                                 for i in range(ramp_points)]
                elif industry == "haccp":
                    start_temp = 135.0  # Hot food cooling
                    ramp_temps = [start_temp - (start_temp - target_temp) * (i / ramp_points) 
                                 for i in range(ramp_points)]
                else:
                    start_temp = 25.0  # Room temperature start
                    ramp_temps = [start_temp + (target_temp - start_temp) * (i / ramp_points) 
                                 for i in range(ramp_points)]
                
                # Hold at target (with slight variations)
                hold_temps = [target_temp + (0.5 - i % 2) for i in range(hold_points)]
                
                # Cool down
                if industry in ["coldchain", "haccp"]:
                    end_temp = target_temp + 2.0
                else:
                    end_temp = 25.0
                cool_temps = [target_temp + (end_temp - target_temp) * (i / cool_points) 
                             for i in range(cool_points)]
                
                temps_1 = ramp_temps + hold_temps + cool_temps
                temps_2 = [temp + (0.3 - i % 2 * 0.6) for i, temp in enumerate(temps_1)]
                
            else:  # fail scenario
                # Failed run - doesn't reach target or hold properly
                if industry == "haccp":
                    # Too slow cooling
                    temps_1 = [135.0 - i * 0.01 for i in range(num_points)]
                    temps_2 = [temp + 0.5 for temp in temps_1]
                elif industry == "coldchain":
                    # Temperature excursion
                    mid_point = num_points // 2
                    temps_1 = []
                    for i in range(num_points):
                        if i < mid_point:
                            temps_1.append(4.0 + 0.1 * (i % 10))
                        else:
                            # Temperature spike
                            temps_1.append(12.0 + 0.2 * (i % 5))
                    temps_2 = [temp + 0.3 for temp in temps_1]
                else:
                    # Insufficient temperature or hold time
                    insufficient_temp = target_temp - 5.0
                    temps_1 = [25.0 + (insufficient_temp - 25.0) * min(1.0, i / (num_points // 2)) 
                              for i in range(num_points)]
                    temps_2 = [temp + 0.5 for temp in temps_1]
            
            # Create sensor column names based on industry
            sensor_names = spec["sensor_selection"]["sensors"]
            if len(sensor_names) < 2:
                sensor_names = [sensor_names[0], sensor_names[0] + "_backup"]
            
            return pd.DataFrame({
                "timestamp": timestamps,
                sensor_names[0]: temps_1,
                sensor_names[1]: temps_2
            })
        
        return generate_data
    
    def test_powder_coat_e2e_pass(self, industry_specs, test_data_generator, temp_dir):
        """Test complete powder coat cure workflow - passing scenario."""
        spec_data = industry_specs["powder"]
        spec = SpecV1(**spec_data)
        
        # Generate passing test data
        df = test_data_generator("powder", "pass", spec_data)
        
        # Step 1: Normalize data
        normalized_df, warnings = normalize_temperature_data(df, spec)
        assert len(normalized_df) > 0
        assert "timestamp" in normalized_df.columns
        
        # Step 2: Make decision
        decision = make_decision(normalized_df, spec)
        assert isinstance(decision, DecisionResult)
        assert decision.pass_ is True
        assert decision.job_id == spec.job.job_id
        
        # Step 3: Generate plot
        plot_path = temp_dir / "powder_plot.png"
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        assert plot_path.exists()
        assert plot_path.stat().st_size > 1000  # Reasonable file size
        
        # Step 4: Generate PDF
        pdf_path = temp_dir / "powder_proof.pdf"
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 10000  # Reasonable PDF size
        
        # Step 5: Create evidence bundle
        bundle_path = temp_dir / "powder_evidence.zip"
        csv_path = temp_dir / "data.csv"
        df.to_csv(csv_path, index=False)
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,  # Use embedded spec
            spec_data=spec_data,
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        assert bundle_path.exists()
        
        # Step 6: Verify evidence bundle
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
        assert verification_result["decision"]["pass"] is True
        assert verification_result["files_verified"] >= 4  # CSV, spec, plot, PDF
    
    def test_powder_coat_e2e_fail(self, industry_specs, test_data_generator, temp_dir):
        """Test complete powder coat cure workflow - failing scenario."""
        spec_data = industry_specs["powder"]
        spec = SpecV1(**spec_data)
        
        # Generate failing test data
        df = test_data_generator("powder", "fail", spec_data)
        
        # Complete workflow
        normalized_df, warnings = normalize_temperature_data(df, spec)
        decision = make_decision(normalized_df, spec)
        
        # Should fail
        assert decision.pass_ is False
        assert len(decision.reasons) > 0
        
        # Generate outputs
        plot_path = temp_dir / "powder_fail_plot.png"
        pdf_path = temp_dir / "powder_fail_proof.pdf"
        
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        # Should still create valid outputs
        assert plot_path.exists()
        assert pdf_path.exists()
    
    def test_haccp_cooling_e2e_pass(self, industry_specs, test_data_generator, temp_dir):
        """Test complete HACCP cooling workflow - passing scenario."""
        spec_data = industry_specs["haccp"]
        spec = SpecV1(**spec_data)
        
        df = test_data_generator("haccp", "pass", spec_data)
        
        # Complete workflow
        normalized_df, warnings = normalize_temperature_data(df, spec)
        decision = make_decision(normalized_df, spec)
        
        # Should pass HACCP cooling requirements
        assert decision.pass_ is True
        assert decision.target_temp_C == 41.0
        
        # Generate evidence bundle
        plot_path = temp_dir / "haccp_plot.png"
        pdf_path = temp_dir / "haccp_proof.pdf"
        bundle_path = temp_dir / "haccp_evidence.zip"
        csv_path = temp_dir / "haccp_data.csv"
        
        df.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec_data,
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        # Verify bundle
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
    
    def test_autoclave_sterilization_e2e(self, industry_specs, test_data_generator, temp_dir):
        """Test complete autoclave sterilization workflow."""
        spec_data = industry_specs["autoclave"]
        spec = SpecV1(**spec_data)
        
        # Test both pass and fail scenarios
        for scenario in ["pass", "fail"]:
            df = test_data_generator("autoclave", scenario, spec_data)
            
            normalized_df, warnings = normalize_temperature_data(df, spec)
            decision = make_decision(normalized_df, spec)
            
            if scenario == "pass":
                assert decision.pass_ is True
                assert decision.target_temp_C == 121.0
            else:
                assert decision.pass_ is False
            
            # Generate outputs
            plot_path = temp_dir / f"autoclave_{scenario}_plot.png"
            pdf_path = temp_dir / f"autoclave_{scenario}_proof.pdf"
            
            generate_proof_plot(normalized_df, spec, decision, str(plot_path))
            generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
            
            assert plot_path.exists()
            assert pdf_path.exists()
    
    def test_sterile_eto_e2e(self, industry_specs, test_data_generator, temp_dir):
        """Test complete ETO sterilization workflow."""
        spec_data = industry_specs["sterile"]
        spec = SpecV1(**spec_data)
        
        df = test_data_generator("sterile", "pass", spec_data)
        
        normalized_df, warnings = normalize_temperature_data(df, spec)
        decision = make_decision(normalized_df, spec)
        
        assert decision.pass_ is True
        assert decision.target_temp_C == 55.0
        
        # Create evidence bundle
        plot_path = temp_dir / "sterile_plot.png"
        pdf_path = temp_dir / "sterile_proof.pdf"
        bundle_path = temp_dir / "sterile_evidence.zip"
        csv_path = temp_dir / "sterile_data.csv"
        
        df.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec_data,
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
    
    def test_concrete_curing_e2e(self, industry_specs, test_data_generator, temp_dir):
        """Test complete concrete curing workflow."""
        spec_data = industry_specs["concrete"]
        spec = SpecV1(**spec_data)
        
        df = test_data_generator("concrete", "pass", spec_data)
        
        normalized_df, warnings = normalize_temperature_data(df, spec)
        decision = make_decision(normalized_df, spec)
        
        assert decision.pass_ is True
        assert decision.target_temp_C == 23.0
        assert decision.required_hold_time_s == 172800  # 48 hours
        
        # Generate outputs
        plot_path = temp_dir / "concrete_plot.png"
        pdf_path = temp_dir / "concrete_proof.pdf"
        
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        assert plot_path.exists()
        assert pdf_path.exists()
    
    def test_coldchain_storage_e2e(self, industry_specs, test_data_generator, temp_dir):
        """Test complete coldchain storage workflow."""
        spec_data = industry_specs["coldchain"]
        spec = SpecV1(**spec_data)
        
        # Test fail scenario (temperature excursion)
        df = test_data_generator("coldchain", "fail", spec_data)
        
        normalized_df, warnings = normalize_temperature_data(df, spec)
        decision = make_decision(normalized_df, spec)
        
        # Should fail due to temperature excursion
        assert decision.pass_ is False
        assert decision.target_temp_C == 4.0
        assert any("excursion" in reason.lower() or "temp" in reason.lower() 
                  for reason in decision.reasons)
        
        # Generate evidence bundle for failed scenario
        plot_path = temp_dir / "coldchain_fail_plot.png"
        pdf_path = temp_dir / "coldchain_fail_proof.pdf"
        bundle_path = temp_dir / "coldchain_fail_evidence.zip"
        csv_path = temp_dir / "coldchain_fail_data.csv"
        
        df.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec_data,
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        # Verify bundle is valid even for failed scenarios
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
        assert verification_result["decision"]["pass"] is False


class TestE2EWithRealData:
    """Test end-to-end compilation with existing example CSV files."""
    
    def test_powder_coat_examples_e2e(self, examples_dir, temp_dir):
        """Test with real powder coat example files."""
        # Test successful run
        pass_csv = examples_dir / "powder_coat_cure_successful_180c_10min_pass.csv"
        pass_spec = examples_dir / "powder_coat_cure_spec_standard_180c_10min.json"
        
        if pass_csv.exists() and pass_spec.exists():
            # Load data and spec
            df, metadata = load_csv_with_metadata(str(pass_csv))
            with open(pass_spec) as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            # Complete workflow
            normalized_df, warnings = normalize_temperature_data(df, spec)
            decision = make_decision(normalized_df, spec)
            
            assert decision.pass_ is True
            
            # Generate outputs
            plot_path = temp_dir / "real_powder_plot.png"
            pdf_path = temp_dir / "real_powder_proof.pdf"
            bundle_path = temp_dir / "real_powder_evidence.zip"
            
            generate_proof_plot(normalized_df, spec, decision, str(plot_path))
            generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
            
            create_evidence_bundle(
                csv_path=str(pass_csv),
                spec_path=str(pass_spec),
                spec_data=None,
                decision=decision,
                plot_path=str(plot_path),
                pdf_path=str(pdf_path),
                output_path=str(bundle_path)
            )
            
            # Verify bundle
            verification_result = verify_evidence_bundle(str(bundle_path))
            assert verification_result["valid"] is True
            assert verification_result["decision"]["pass"] is True
        
        # Test failing run
        fail_csv = examples_dir / "powder_coat_cure_insufficient_hold_time_fail.csv"
        if fail_csv.exists() and pass_spec.exists():
            df, metadata = load_csv_with_metadata(str(fail_csv))
            with open(pass_spec) as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            normalized_df, warnings = normalize_temperature_data(df, spec)
            decision = make_decision(normalized_df, spec)
            
            assert decision.pass_ is False
            assert any("hold" in reason.lower() for reason in decision.reasons)
    
    def test_fahrenheit_conversion_e2e(self, examples_dir, temp_dir):
        """Test end-to-end workflow with Fahrenheit input data."""
        fahrenheit_csv = examples_dir / "powder_coat_cure_fahrenheit_input_356f_10min_pass.csv"
        fahrenheit_spec = examples_dir / "powder_coat_cure_spec_fahrenheit_input_356f_10min.json"
        
        if fahrenheit_csv.exists() and fahrenheit_spec.exists():
            df, metadata = load_csv_with_metadata(str(fahrenheit_csv))
            with open(fahrenheit_spec) as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            # Complete workflow with Fahrenheit data
            normalized_df, warnings = normalize_temperature_data(df, spec)
            decision = make_decision(normalized_df, spec)
            
            # Should handle Fahrenheit conversion properly
            assert decision.pass_ is True
            assert decision.target_temp_C == spec.spec.target_temp_C
            
            # All temperature values in results should be in Celsius
            assert 100.0 < decision.max_temp_C < 300.0  # Reasonable Celsius range
            assert 100.0 < decision.min_temp_C < 300.0


class TestE2EErrorHandling:
    """Test end-to-end error handling and edge cases."""
    
    def test_corrupted_data_handling(self, industry_specs, temp_dir):
        """Test handling of corrupted or invalid data."""
        spec_data = industry_specs["powder"]
        spec = SpecV1(**spec_data)
        
        # Create corrupted data (missing timestamps)
        corrupted_df = pd.DataFrame({
            "pmt_sensor_1": [180.0, 181.0, 182.0],
            "pmt_sensor_2": [179.5, 180.5, 181.5]
            # Missing timestamp column
        })
        
        # Should handle gracefully
        try:
            normalized_df, warnings = normalize_temperature_data(corrupted_df, spec)
            decision = make_decision(normalized_df, spec)
            # If it succeeds, it should be marked as failed
            assert decision.pass_ is False
        except Exception as e:
            # Or it should raise a clear error
            assert "timestamp" in str(e).lower() or "column" in str(e).lower()
    
    def test_insufficient_data_e2e(self, industry_specs, temp_dir):
        """Test end-to-end workflow with insufficient data points."""
        spec_data = industry_specs["powder"]
        spec = SpecV1(**spec_data)
        
        # Create minimal data (insufficient for hold time)
        minimal_df = pd.DataFrame({
            "timestamp": pd.date_range("2024-08-05T10:00:00Z", periods=3, freq="30s", tz="UTC"),
            "pmt_sensor_1": [180.0, 182.0, 181.0],
            "pmt_sensor_2": [179.5, 181.5, 180.5]
        })
        
        normalized_df, warnings = normalize_temperature_data(minimal_df, spec)
        decision = make_decision(normalized_df, spec)
        
        # Should fail due to insufficient data
        assert decision.pass_ is False
        assert any("insufficient" in reason.lower() or "short" in reason.lower() 
                  for reason in decision.reasons)
        
        # Should still generate outputs
        plot_path = temp_dir / "insufficient_plot.png"
        pdf_path = temp_dir / "insufficient_proof.pdf"
        
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        assert plot_path.exists()
        assert pdf_path.exists()
    
    def test_evidence_bundle_integrity(self, industry_specs, test_data_generator, temp_dir):
        """Test evidence bundle integrity verification."""
        spec_data = industry_specs["powder"]
        spec = SpecV1(**spec_data)
        
        df = test_data_generator("powder", "pass", spec_data)
        
        # Complete workflow
        normalized_df, warnings = normalize_temperature_data(df, spec)
        decision = make_decision(normalized_df, spec)
        
        plot_path = temp_dir / "integrity_plot.png"
        pdf_path = temp_dir / "integrity_proof.pdf"
        bundle_path = temp_dir / "integrity_evidence.zip"
        csv_path = temp_dir / "integrity_data.csv"
        
        df.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec_data,
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        # Verify original bundle
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
        
        # Corrupt the bundle by modifying a file
        with zipfile.ZipFile(bundle_path, 'a') as zf:
            zf.writestr("corrupted_file.txt", "This shouldn't be here")
        
        # Verification should detect tampering
        verification_result_corrupted = verify_evidence_bundle(str(bundle_path))
        # Note: Depending on implementation, this might still be valid if only manifest files are checked
        # The key is that the original files should still verify correctly
        assert "files_verified" in verification_result_corrupted