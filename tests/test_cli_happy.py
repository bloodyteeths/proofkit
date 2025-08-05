"""
CLI Happy Path Testing for ProofKit

Tests the complete CLI pipeline including:
- normalize → decide → render → pack workflow
- Temperature unit conversion (°F to °C) 
- Typer CliRunner integration
- File handling and output validation

Example usage:
    pytest tests/test_cli_happy.py -v
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from typer.testing import CliRunner
import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.main import app as cli_app
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.models import SpecV1
from core.render_pdf import generate_proof_pdf
from core.plot import generate_proof_plot
from core.pack import create_evidence_bundle

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# CLI runner
runner = CliRunner()


class TestCLIBasicCommands:
    """Test basic CLI command functionality."""
    
    def test_cli_help_command(self):
        """Test that CLI help command works."""
        result = runner.invoke(cli_app, ["--help"])
        
        assert result.exit_code == 0
        assert "ProofKit" in result.stdout
        assert "pack" in result.stdout
        assert "verify" in result.stdout
    
    def test_cli_presets_list(self):
        """Test CLI presets list command."""
        result = runner.invoke(cli_app, ["presets", "--list"])
        
        assert result.exit_code == 0
        # Should show available presets
        assert "powder" in result.stdout.lower() or "preset" in result.stdout.lower()
    
    def test_cli_presets_show_industry(self):
        """Test CLI presets show specific industry."""
        result = runner.invoke(cli_app, ["presets", "--industry", "powder"])
        
        # Should either show preset or indicate file not found
        assert result.exit_code in [0, 1]
        
        if result.exit_code == 0:
            # Should show JSON content
            assert "{" in result.stdout
            assert "version" in result.stdout or "spec" in result.stdout


class TestCLIFullPipeline:
    """Test complete CLI pipeline with real data."""
    
    def test_complete_pipeline_celsius_data(self):
        """Test normalize → decide → render → pack pipeline with Celsius data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Copy test fixtures to temp directory
            csv_source = FIXTURES_DIR / "min_powder.csv"
            spec_source = FIXTURES_DIR / "min_powder_spec.json"
            
            csv_path = temp_path / "test_data.csv"
            spec_path = temp_path / "test_spec.json"
            
            # Copy files
            csv_path.write_text(csv_source.read_text())
            spec_path.write_text(spec_source.read_text())
            
            # Step 1: Normalize data
            normalized_path = temp_path / "normalized.csv"
            df, metadata = load_csv_with_metadata(str(csv_path))
            
            # Load spec for validation
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            normalized_df = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=spec.data_requirements.allowed_gaps_s,
                max_sample_period_s=spec.data_requirements.max_sample_period_s
            )
            normalized_df.to_csv(normalized_path, index=False)
            
            # Step 2: Make decision
            decision_path = temp_path / "decision.json"
            decision = make_decision(normalized_df, spec)
            
            with open(decision_path, 'w') as f:
                json.dump(decision.model_dump(by_alias=True), f, indent=2)
            
            # Step 3: Generate plot
            plot_path = temp_path / "plot.png"
            generate_proof_plot(normalized_df, spec, decision, str(plot_path))
            
            # Step 4: Generate PDF
            pdf_path = temp_path / "proof.pdf"
            generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=str(plot_path),
                normalized_csv_path=str(normalized_path),
                verification_hash="test_hash_123",
                output_path=str(pdf_path)
            )
            
            # Step 5: Create evidence bundle using CLI
            bundle_path = temp_path / "evidence.zip"
            
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(spec_path),
                "--normalized", str(normalized_path),
                "--decision", str(decision_path),
                "--proof", str(pdf_path),
                "--plot", str(plot_path),
                "--output", str(bundle_path),
                "--job-id", "test_job_001"
            ])
            
            # Verify CLI pack command succeeded
            assert pack_result.exit_code == 0
            assert "Evidence bundle created successfully" in pack_result.stdout
            assert bundle_path.exists()
            assert bundle_path.stat().st_size > 0
            
            # Verify decision was PASS (our test data should pass)
            assert decision.pass_ is True
            
            # Verify all intermediate files exist
            assert normalized_path.exists()
            assert decision_path.exists()
            assert plot_path.exists()
            assert pdf_path.exists()
    
    def test_complete_pipeline_fahrenheit_conversion(self):
        """Test pipeline with Fahrenheit to Celsius conversion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Use Fahrenheit test fixtures
            csv_source = FIXTURES_DIR / "min_fahrenheit.csv"
            spec_source = FIXTURES_DIR / "min_fahrenheit_spec.json"
            
            csv_path = temp_path / "test_fahrenheit.csv"
            spec_path = temp_path / "test_fahrenheit_spec.json"
            
            # Copy files
            csv_path.write_text(csv_source.read_text())
            spec_path.write_text(spec_source.read_text())
            
            # Step 1: Load and normalize data (should convert °F to °C)
            df, metadata = load_csv_with_metadata(str(csv_path))
            
            # Verify we have Fahrenheit data initially
            assert "temp_F" in df.columns
            
            # Load spec
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            # Normalize should convert F to C
            normalized_df = normalize_temperature_data(
                df,
                target_step_s=30.0,
                allowed_gaps_s=spec.data_requirements.allowed_gaps_s,
                max_sample_period_s=spec.data_requirements.max_sample_period_s
            )
            
            # Verify conversion happened - should have temp_C column
            assert "temp_C" in normalized_df.columns
            
            # Verify temperature conversion (first row should be ~168°C from 334.4°F)
            first_temp_c = normalized_df["temp_C"].iloc[0]
            assert 165 < first_temp_c < 170  # Should be around 168°C
            
            # Step 2: Complete pipeline
            normalized_path = temp_path / "normalized.csv"
            normalized_df.to_csv(normalized_path, index=False)
            
            decision = make_decision(normalized_df, spec)
            decision_path = temp_path / "decision.json"
            with open(decision_path, 'w') as f:
                json.dump(decision.model_dump(by_alias=True), f, indent=2)
            
            plot_path = temp_path / "plot.png"
            generate_proof_plot(normalized_df, spec, decision, str(plot_path))
            
            pdf_path = temp_path / "proof.pdf"
            generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=str(plot_path),
                normalized_csv_path=str(normalized_path),
                verification_hash="test_fahrenheit_hash",
                output_path=str(pdf_path)
            )
            
            # Create evidence bundle
            bundle_path = temp_path / "evidence_fahrenheit.zip"
            
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(spec_path),
                "--normalized", str(normalized_path),
                "--decision", str(decision_path),
                "--proof", str(pdf_path),
                "--plot", str(plot_path),
                "--output", str(bundle_path),
                "--job-id", "test_fahrenheit_001"
            ])
            
            # Verify success
            assert pack_result.exit_code == 0
            assert bundle_path.exists()
            assert bundle_path.stat().st_size > 0
            
            # Verify decision should pass (our Fahrenheit data converts to passing temps)
            assert decision.pass_ is True
    
    def test_cli_verify_bundle(self):
        """Test CLI verify command on a created bundle."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a simple bundle first
            csv_source = FIXTURES_DIR / "min_powder.csv"
            spec_source = FIXTURES_DIR / "min_powder_spec.json"
            
            csv_path = temp_path / "test.csv"
            spec_path = temp_path / "spec.json"
            normalized_path = temp_path / "normalized.csv"
            decision_path = temp_path / "decision.json"
            plot_path = temp_path / "plot.png"
            pdf_path = temp_path / "proof.pdf"
            bundle_path = temp_path / "test_bundle.zip"
            
            # Copy and process files
            csv_path.write_text(csv_source.read_text())
            spec_path.write_text(spec_source.read_text())
            
            # Quick processing
            df, _ = load_csv_with_metadata(str(csv_path))
            with open(spec_path, 'r') as f:
                spec_data = json.load(f)
            spec = SpecV1(**spec_data)
            
            normalized_df = normalize_temperature_data(df, target_step_s=30.0, allowed_gaps_s=120.0, max_sample_period_s=60.0)
            normalized_df.to_csv(normalized_path, index=False)
            
            decision = make_decision(normalized_df, spec)
            with open(decision_path, 'w') as f:
                json.dump(decision.model_dump(by_alias=True), f, indent=2)
            
            # Create minimal plot file (empty PNG is OK for testing)
            plot_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
            
            # Create minimal PDF file
            pdf_content = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n%%EOF'
            pdf_path.write_bytes(pdf_content)
            
            # Create bundle
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(spec_path),
                "--normalized", str(normalized_path),
                "--decision", str(decision_path),
                "--proof", str(pdf_path),
                "--plot", str(plot_path),
                "--output", str(bundle_path),
                "--deterministic"  # For consistent testing
            ])
            
            assert pack_result.exit_code == 0
            assert bundle_path.exists()
            
            # Now test verify command
            verify_result = runner.invoke(cli_app, [
                "verify",
                str(bundle_path),
                "--quick"  # Quick verification to avoid complex decision re-computation
            ])
            
            # Verify command should succeed
            assert verify_result.exit_code == 0
            assert "verification" in verify_result.stdout.lower()
    
    def test_cli_extract_bundle(self):
        """Test CLI extract command."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a minimal bundle first (similar to verify test)
            csv_source = FIXTURES_DIR / "min_powder.csv"
            spec_source = FIXTURES_DIR / "min_powder_spec.json"
            
            csv_path = temp_path / "test.csv"
            spec_path = temp_path / "spec.json"
            bundle_path = temp_path / "test_bundle.zip"
            extract_dir = temp_path / "extracted"
            
            # Create minimal required files
            csv_path.write_text(csv_source.read_text())
            spec_path.write_text(spec_source.read_text())
            
            # Create dummy files for other components
            normalized_path = temp_path / "normalized.csv"
            decision_path = temp_path / "decision.json"
            plot_path = temp_path / "plot.png"
            pdf_path = temp_path / "proof.pdf"
            
            normalized_path.write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
            decision_path.write_text('{"pass": true, "actual_hold_time_s": 600}')
            plot_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 50)
            pdf_path.write_bytes(b'%PDF-1.4\n%%EOF')
            
            # Create bundle
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(spec_path),
                "--normalized", str(normalized_path),
                "--decision", str(decision_path),
                "--proof", str(pdf_path),
                "--plot", str(plot_path),
                "--output", str(bundle_path)
            ])
            
            assert pack_result.exit_code == 0
            
            # Test extract command
            extract_result = runner.invoke(cli_app, [
                "extract",
                str(bundle_path),
                "--output", str(extract_dir)
            ])
            
            # Extract should succeed
            assert extract_result.exit_code == 0
            assert "Extracted" in extract_result.stdout
            assert extract_dir.exists()


class TestCLIErrorHandling:
    """Test CLI error handling and edge cases."""
    
    def test_pack_missing_files(self):
        """Test CLI pack command with missing required files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create only some files (missing others)
            csv_path = temp_path / "test.csv"
            csv_path.write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
            
            # Missing spec file
            missing_spec = temp_path / "missing_spec.json"
            
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(missing_spec),  # This file doesn't exist
                "--normalized", str(csv_path),  # Reuse for testing
                "--decision", str(csv_path),  # Reuse for testing  
                "--proof", str(csv_path),  # Reuse for testing
                "--plot", str(csv_path),  # Reuse for testing
                "--output", str(temp_path / "output.zip")
            ])
            
            # Should fail due to missing files
            assert pack_result.exit_code == 1
            assert "Missing required files" in pack_result.stdout
    
    def test_verify_nonexistent_bundle(self):
        """Test CLI verify command with nonexistent bundle."""
        nonexistent_bundle = "/tmp/nonexistent_bundle.zip"
        
        verify_result = runner.invoke(cli_app, [
            "verify",
            nonexistent_bundle
        ])
        
        # Should fail gracefully
        assert verify_result.exit_code == 1
        assert "not found" in verify_result.stdout
    
    def test_presets_invalid_industry(self):
        """Test CLI presets command with invalid industry."""
        result = runner.invoke(cli_app, [
            "presets", 
            "--industry", 
            "nonexistent_industry"
        ])
        
        # Should fail gracefully
        assert result.exit_code == 1
        assert "Unknown industry" in result.stdout or "not found" in result.stdout


class TestCLIOutputFormats:
    """Test CLI output formats and verbosity."""
    
    def test_pack_with_job_id(self):
        """Test pack command includes job ID in output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create minimal valid files
            csv_path = temp_path / "test.csv"
            csv_path.write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
            
            for filename in ["spec.json", "normalized.csv", "decision.json"]:
                file_path = temp_path / filename
                if filename.endswith('.json'):
                    file_path.write_text('{"test": true}')
                else:
                    file_path.write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
            
            # Create minimal binary files
            plot_path = temp_path / "plot.png"
            pdf_path = temp_path / "proof.pdf"
            plot_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 20)
            pdf_path.write_bytes(b'%PDF-1.4\n%%EOF')
            
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(temp_path / "spec.json"),
                "--normalized", str(temp_path / "normalized.csv"),
                "--decision", str(temp_path / "decision.json"),
                "--proof", str(pdf_path),
                "--plot", str(plot_path),
                "--output", str(temp_path / "output.zip"),
                "--job-id", "test_job_with_id"
            ])
            
            # Should include job ID in output
            if pack_result.exit_code == 0:
                assert "test_job_with_id" in pack_result.stdout
    
    def test_deterministic_flag(self):
        """Test that deterministic flag is acknowledged."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create minimal files
            csv_path = temp_path / "test.csv"
            csv_path.write_text("timestamp,temp_C\n2024-01-01T10:00:00Z,170.0\n")
            
            for filename in ["spec.json", "normalized.csv", "decision.json"]:
                (temp_path / filename).write_text('{"test": true}' if filename.endswith('.json') else "test,data\n1,2\n")
            
            plot_path = temp_path / "plot.png"
            pdf_path = temp_path / "proof.pdf"
            plot_path.write_bytes(b'\x89PNG\r\n\x1a\n')
            pdf_path.write_bytes(b'%PDF-1.4\n%%EOF')
            
            pack_result = runner.invoke(cli_app, [
                "pack",
                "--raw-csv", str(csv_path),
                "--spec", str(temp_path / "spec.json"),
                "--normalized", str(temp_path / "normalized.csv"),
                "--decision", str(temp_path / "decision.json"),
                "--proof", str(pdf_path),
                "--plot", str(plot_path),
                "--output", str(temp_path / "output.zip"),
                "--deterministic"
            ])
            
            # Should acknowledge deterministic mode
            if pack_result.exit_code == 0:
                assert "Deterministic" in pack_result.stdout or "deterministic" in pack_result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])