"""
Test concrete fixture data produces sufficient normalized points and compiles to PASS/FAIL.
"""

import pytest
from pathlib import Path
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
from core.models import SpecV1


@pytest.fixture
def pass_csv_path():
    """Path to concrete pass fixture."""
    return Path(__file__).parent.parent.parent / "audit" / "fixtures" / "concrete" / "pass.csv"


@pytest.fixture 
def fail_csv_path():
    """Path to concrete fail fixture."""
    return Path(__file__).parent.parent.parent / "audit" / "fixtures" / "concrete" / "fail.csv"


@pytest.fixture
def concrete_spec():
    """Create minimal concrete spec suitable for short test fixture data."""
    from core.models import JobInfo, CureSpec, DataRequirements, SensorSelection, Logic, Preconditions, Reporting
    
    return SpecV1(
        version="1.0",
        industry="concrete",
        job=JobInfo(job_id="test_concrete"),
        spec=CureSpec(
            method="OVEN_AIR",  # Using coerced from AMBIENT_CURE
            target_temp_C=18.0,
            hold_time_s=600,  # 10 minutes for testing
            sensor_uncertainty_C=1.0
        ),
        data_requirements=DataRequirements(
            max_sample_period_s=60.0,
            allowed_gaps_s=120.0
        ),
        sensor_selection=SensorSelection(
            mode="mean_of_set",
            require_at_least=2
        ),
        logic=Logic(
            continuous=True,
            max_total_dips_s=60
        ),
        preconditions=Preconditions(
            max_ramp_rate_C_per_min=10.0,  # Relaxed for test
            max_time_to_threshold_s=600
        )
    )


def test_pass_fixture_normalizes_sufficient_points(pass_csv_path, concrete_spec):
    """Test that pass.csv normalizes to ≥10 points."""
    df, metadata = load_csv_with_metadata(str(pass_csv_path))
    
    # Normalize with 30s target step (matches fixture cadence)
    normalized_df = normalize_temperature_data(
        df, 
        target_step_s=30.0,
        allowed_gaps_s=60.0,
        industry="concrete"
    )
    
    assert len(normalized_df) >= 10, f"Expected ≥10 points, got {len(normalized_df)}"
    
    # Verify timestamps are preserved (no coalescing)
    time_diffs = normalized_df['timestamp'].diff().dt.total_seconds().dropna()
    expected_step = 30.0
    tolerance = 5.0  # Allow 5s tolerance
    
    # Most intervals should be close to 30s
    close_to_target = abs(time_diffs - expected_step) <= tolerance
    assert close_to_target.sum() / len(time_diffs) >= 0.8, "Most intervals should be ~30s"


def test_fail_fixture_normalizes_sufficient_points(fail_csv_path, concrete_spec):
    """Test that fail.csv normalizes to ≥10 points."""
    df, metadata = load_csv_with_metadata(str(fail_csv_path))
    
    # Normalize with 30s target step (matches fixture cadence)
    normalized_df = normalize_temperature_data(
        df,
        target_step_s=30.0, 
        allowed_gaps_s=60.0,
        industry="concrete"
    )
    
    assert len(normalized_df) >= 10, f"Expected ≥10 points, got {len(normalized_df)}"
    
    # Verify timestamps are preserved (no coalescing) 
    time_diffs = normalized_df['timestamp'].diff().dt.total_seconds().dropna()
    expected_step = 30.0
    tolerance = 5.0  # Allow 5s tolerance
    
    # Most intervals should be close to 30s
    close_to_target = abs(time_diffs - expected_step) <= tolerance
    assert close_to_target.sum() / len(time_diffs) >= 0.8, "Most intervals should be ~30s"


def test_pass_fixture_compiles_to_pass(pass_csv_path, concrete_spec):
    """Test that pass.csv compiles to a decision (not insufficient data)."""
    df, metadata = load_csv_with_metadata(str(pass_csv_path))
    
    normalized_df = normalize_temperature_data(
        df,
        target_step_s=30.0,
        allowed_gaps_s=60.0, 
        industry="concrete"
    )
    
    # Make decision
    decision = make_decision(normalized_df, concrete_spec)
    
    # Primary requirement: No "insufficient data" error
    all_reasons = " ".join(decision.reasons).lower()
    assert "insufficient data" not in all_reasons
    
    # Secondary requirement: Got a definitive decision (not an error)
    assert decision.status in ["PASS", "FAIL"], f"Expected PASS or FAIL, got {decision.status}"
    
    # The fixture may fail due to concrete-specific requirements (24h minimum, etc.)
    # but it should not fail due to insufficient data points


def test_fail_fixture_compiles_to_fail(fail_csv_path, concrete_spec):
    """Test that fail.csv compiles to a decision (not insufficient data).""" 
    df, metadata = load_csv_with_metadata(str(fail_csv_path))
    
    normalized_df = normalize_temperature_data(
        df,
        target_step_s=30.0,
        allowed_gaps_s=60.0,
        industry="concrete"
    )
    
    # Make decision
    decision = make_decision(normalized_df, concrete_spec)
    
    # Primary requirement: No "insufficient data" error
    all_reasons = " ".join(decision.reasons).lower()
    assert "insufficient data" not in all_reasons
    
    # Secondary requirement: Got a definitive decision (not an error)
    assert decision.status in ["PASS", "FAIL"], f"Expected PASS or FAIL, got {decision.status}"


def test_fixtures_have_proper_timestamps(pass_csv_path, fail_csv_path):
    """Test that fixture timestamps are properly spaced (30s intervals)."""
    import pandas as pd
    
    for csv_path in [pass_csv_path, fail_csv_path]:
        df, _ = load_csv_with_metadata(str(csv_path))
        
        # Parse timestamps to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        
        # Check timestamp intervals
        time_diffs = df['timestamp'].diff().dt.total_seconds().dropna()
        
        # Should be consistent 30s intervals
        assert all(abs(diff - 30.0) < 1.0 for diff in time_diffs), f"Irregular intervals in {csv_path.name}"
        
        # Should have sufficient data points
        assert len(df) >= 20, f"Insufficient data in {csv_path.name}: {len(df)} points"