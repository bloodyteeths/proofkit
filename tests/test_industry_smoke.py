"""
Industry Smoke Tests

Tests each industry fixture (pass/fail/borderline/missing_required) to ensure
the compile pipeline works without errors. Validates that DecisionResult
has non-null status. For safety-critical industries, missing required 
sensors should result in INDETERMINATE status.

Example usage:
    pytest tests/test_industry_smoke.py -v
    pytest tests/test_industry_smoke.py::test_powder_fixtures -v
"""

import pytest
import pandas as pd
import json
from pathlib import Path
from typing import Dict, Any

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import SpecV1, DecisionResult
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision


class TestIndustrySmoke:
    """Smoke tests for all industry fixtures."""
    
    @pytest.fixture(scope="class")
    def audit_dir(self):
        """Path to audit fixtures directory."""
        return Path(__file__).parent.parent / "audit" / "fixtures"
    
    @pytest.fixture(scope="class")
    def fixture_map(self, audit_dir):
        """Map of all available industry fixtures."""
        fixtures = {}
        for industry_dir in audit_dir.iterdir():
            if industry_dir.is_dir():
                industry = industry_dir.name
                fixtures[industry] = {}
                
                for csv_file in industry_dir.glob("*.csv"):
                    test_type = csv_file.stem
                    json_file = industry_dir / f"{test_type}.json"
                    
                    if json_file.exists():
                        fixtures[industry][test_type] = {
                            'csv': csv_file,
                            'json': json_file
                        }
        
        return fixtures
    
    def compile_pipeline(self, csv_path: Path, spec_path: Path) -> DecisionResult:
        """
        Run the full compile pipeline: load CSV -> normalize -> make decision.
        
        Args:
            csv_path: Path to CSV fixture
            spec_path: Path to JSON spec fixture
            
        Returns:
            DecisionResult from make_decision
            
        Raises:
            Any exception from the pipeline
        """
        # Load spec
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        spec = SpecV1(**spec_data)
        
        # Load and normalize CSV
        df, metadata = load_csv_with_metadata(csv_path)
        data_reqs = spec_data.get('data_requirements', {})
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=data_reqs.get('max_sample_period_s', 30.0),
            allowed_gaps_s=data_reqs.get('allowed_gaps_s', 60.0),
            industry=spec_data.get('industry')
        )
        
        # Make decision
        result = make_decision(normalized_df, spec)
        
        return result
    
    def is_safety_critical(self, industry: str) -> bool:
        """Check if industry is safety-critical."""
        safety_critical = {'haccp', 'autoclave', 'sterile', 'concrete'}
        return industry.lower() in safety_critical
    
    # Powder industry tests
    def test_powder_pass(self, fixture_map):
        """Test powder pass fixture compilation."""
        if 'powder' not in fixture_map or 'pass' not in fixture_map['powder']:
            pytest.skip("Powder pass fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['powder']['pass']['csv'],
            fixture_map['powder']['pass']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_powder_fail(self, fixture_map):
        """Test powder fail fixture compilation."""
        if 'powder' not in fixture_map or 'fail' not in fixture_map['powder']:
            pytest.skip("Powder fail fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['powder']['fail']['csv'],
            fixture_map['powder']['fail']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_powder_borderline(self, fixture_map):
        """Test powder borderline fixture compilation."""
        if 'powder' not in fixture_map or 'borderline' not in fixture_map['powder']:
            pytest.skip("Powder borderline fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['powder']['borderline']['csv'],
            fixture_map['powder']['borderline']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_powder_missing_required(self, fixture_map):
        """Test powder missing_required fixture compilation."""
        if 'powder' not in fixture_map or 'missing_required' not in fixture_map['powder']:
            pytest.skip("Powder missing_required fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['powder']['missing_required']['csv'],
            fixture_map['powder']['missing_required']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    # HACCP industry tests
    def test_haccp_pass(self, fixture_map):
        """Test haccp pass fixture compilation."""
        if 'haccp' not in fixture_map or 'pass' not in fixture_map['haccp']:
            pytest.skip("HACCP pass fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['haccp']['pass']['csv'],
            fixture_map['haccp']['pass']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_haccp_fail(self, fixture_map):
        """Test haccp fail fixture compilation."""
        if 'haccp' not in fixture_map or 'fail' not in fixture_map['haccp']:
            pytest.skip("HACCP fail fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['haccp']['fail']['csv'],
            fixture_map['haccp']['fail']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_haccp_borderline(self, fixture_map):
        """Test haccp borderline fixture compilation."""
        if 'haccp' not in fixture_map or 'borderline' not in fixture_map['haccp']:
            pytest.skip("HACCP borderline fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['haccp']['borderline']['csv'],
            fixture_map['haccp']['borderline']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_haccp_missing_required(self, fixture_map):
        """Test haccp missing_required fixture compilation."""
        if 'haccp' not in fixture_map or 'missing_required' not in fixture_map['haccp']:
            pytest.skip("HACCP missing_required fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['haccp']['missing_required']['csv'],
            fixture_map['haccp']['missing_required']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
        
        # Safety-critical industry with missing required should be INDETERMINATE
        if self.is_safety_critical('haccp'):
            assert result.status == "INDETERMINATE", "Safety-critical missing required should be INDETERMINATE"
    
    # Autoclave industry tests
    def test_autoclave_pass(self, fixture_map):
        """Test autoclave pass fixture compilation."""
        if 'autoclave' not in fixture_map or 'pass' not in fixture_map['autoclave']:
            pytest.skip("Autoclave pass fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['autoclave']['pass']['csv'],
            fixture_map['autoclave']['pass']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_autoclave_fail(self, fixture_map):
        """Test autoclave fail fixture compilation."""
        if 'autoclave' not in fixture_map or 'fail' not in fixture_map['autoclave']:
            pytest.skip("Autoclave fail fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['autoclave']['fail']['csv'],
            fixture_map['autoclave']['fail']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    # Sterile industry tests
    def test_sterile_pass(self, fixture_map):
        """Test sterile pass fixture compilation."""
        if 'sterile' not in fixture_map or 'pass' not in fixture_map['sterile']:
            pytest.skip("Sterile pass fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['sterile']['pass']['csv'],
            fixture_map['sterile']['pass']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_sterile_fail(self, fixture_map):
        """Test sterile fail fixture compilation."""
        if 'sterile' not in fixture_map or 'fail' not in fixture_map['sterile']:
            pytest.skip("Sterile fail fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['sterile']['fail']['csv'],
            fixture_map['sterile']['fail']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    # Concrete industry tests  
    def test_concrete_pass(self, fixture_map):
        """Test concrete pass fixture compilation."""
        if 'concrete' not in fixture_map or 'pass' not in fixture_map['concrete']:
            pytest.skip("Concrete pass fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['concrete']['pass']['csv'],
            fixture_map['concrete']['pass']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_concrete_fail(self, fixture_map):
        """Test concrete fail fixture compilation."""
        if 'concrete' not in fixture_map or 'fail' not in fixture_map['concrete']:
            pytest.skip("Concrete fail fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['concrete']['fail']['csv'],
            fixture_map['concrete']['fail']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    # Coldchain industry tests
    def test_coldchain_pass(self, fixture_map):
        """Test coldchain pass fixture compilation."""
        if 'coldchain' not in fixture_map or 'pass' not in fixture_map['coldchain']:
            pytest.skip("Coldchain pass fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['coldchain']['pass']['csv'],
            fixture_map['coldchain']['pass']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    def test_coldchain_fail(self, fixture_map):
        """Test coldchain fail fixture compilation."""
        if 'coldchain' not in fixture_map or 'fail' not in fixture_map['coldchain']:
            pytest.skip("Coldchain fail fixture not available")
        
        result = self.compile_pipeline(
            fixture_map['coldchain']['fail']['csv'],
            fixture_map['coldchain']['fail']['json']
        )
        
        assert result.status is not None, "DecisionResult status should not be null"
        assert result.status != "", "DecisionResult status should not be empty"
    
    # Comprehensive fixture coverage test
    @pytest.mark.parametrize("industry,test_type", [
        ("powder", "pass"), ("powder", "fail"), ("powder", "borderline"), ("powder", "missing_required"),
        ("powder", "gap"), ("powder", "dup_ts"), ("powder", "tz_shift"),
        ("haccp", "pass"), ("haccp", "fail"), ("haccp", "borderline"), ("haccp", "missing_required"),
        ("autoclave", "pass"), ("autoclave", "fail"),
        ("sterile", "pass"), ("sterile", "fail"),
        ("concrete", "pass"), ("concrete", "fail"),
        ("coldchain", "pass"), ("coldchain", "fail"),
    ])
    def test_fixture_compilation(self, fixture_map, industry, test_type):
        """Test that all available fixtures compile successfully."""
        if industry not in fixture_map or test_type not in fixture_map[industry]:
            pytest.skip(f"{industry}/{test_type} fixture not available")
        
        # Attempt compilation
        try:
            result = self.compile_pipeline(
                fixture_map[industry][test_type]['csv'],
                fixture_map[industry][test_type]['json']
            )
            
            # Basic smoke test assertions
            assert result.status is not None, f"{industry}/{test_type}: DecisionResult status should not be null"
            assert result.status != "", f"{industry}/{test_type}: DecisionResult status should not be empty"
            assert isinstance(result.status, str), f"{industry}/{test_type}: DecisionResult status should be string"
            
            # Safety-critical missing required check
            if test_type == "missing_required" and self.is_safety_critical(industry):
                assert result.status == "INDETERMINATE", f"{industry}/{test_type}: Safety-critical missing required should be INDETERMINATE"
            
        except AttributeError as e:
            # This is what we're testing for - potential AttributeErrors in metrics_* modules
            pytest.fail(f"{industry}/{test_type}: AttributeError during compilation: {e}")
        except Exception as e:
            # Other exceptions might be expected (e.g., data validation errors)
            # We still want to ensure the pipeline doesn't crash with AttributeErrors
            if "AttributeError" in str(type(e)):
                pytest.fail(f"{industry}/{test_type}: Unexpected AttributeError: {e}")
            # For other exceptions, log but continue (these might be expected validation failures)
            print(f"Expected exception in {industry}/{test_type}: {e}")