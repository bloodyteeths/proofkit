#!/usr/bin/env python3
"""
ProofKit Plot Generation Example

This example demonstrates the complete ProofKit workflow:
1. Generate synthetic cure data
2. Normalize the CSV data  
3. Make a cure decision
4. Generate a proof plot with PMT data, thresholds, and hold intervals

This shows M3 plot requirements integration with M1 (normalize) and M2 (decide).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.normalize import load_csv_with_metadata, normalize_temperature_data
from core.decide import make_decision
from core.plot import generate_proof_plot, validate_plot_inputs
from core.models import SpecV1
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import tempfile
import json


def create_cure_example_csv(scenario="pass"):
    """
    Create an example CSV file with cure process data.
    
    Args:
        scenario: "pass", "fail_short_hold", or "fail_no_threshold"
    """
    start_time = datetime(2025, 1, 15, 14, 30, 0)  # Start at 2:30 PM
    duration_minutes = 30  # Longer duration for passing scenario
    interval_seconds = 30  # Regular 30-second sampling
    
    timestamps = []
    pmt_sensor_1 = []  # Primary PMT sensor
    pmt_sensor_2 = []  # Secondary PMT sensor
    oven_air_temp = []  # Oven air temperature
    
    target_temp = 180.0
    conservative_threshold = target_temp + 2.0  # 182°C threshold
    
    for i in range(int(duration_minutes * 60 / interval_seconds)):
        # Create timestamp
        ts = start_time + timedelta(seconds=i * interval_seconds)
        timestamps.append(ts)
        
        time_mins = i * interval_seconds / 60
        
        if scenario == "pass":
            # Successful cure: ramp up quickly, hold well above threshold for 15+ minutes
            if time_mins < 4:  # Quick ramp phase
                temp_base = 20 + (conservative_threshold + 3) * (time_mins / 4)  # Ramp to 185°C
            else:  # Long hold phase - stay well above conservative threshold
                temp_base = conservative_threshold + 3 + np.random.normal(0, 1.0)  # Hold at 185°C ± 1°C
                
        elif scenario == "fail_short_hold":
            # Failed cure: reaches temperature but doesn't hold long enough
            if time_mins < 4:  # Slower ramp
                temp_base = 20 + (target_temp - 20) * (time_mins / 4)
            elif time_mins < 15:  # Short hold
                temp_base = target_temp + np.random.normal(1, 1.5)
            else:  # Temperature drops
                temp_base = target_temp - 5 + np.random.normal(0, 2)
                
        else:  # fail_no_threshold
            # Failed cure: never reaches target temperature
            if time_mins < 8:  # Slow ramp
                temp_base = 20 + (target_temp - 15) * (time_mins / 8)  # Only reaches 165°C
            else:  # Hold below threshold
                temp_base = target_temp - 15 + np.random.normal(0, 2)
        
        # Add sensor-specific variations
        pmt1 = temp_base + np.random.normal(0, 1.2)  # Sensor 1 noise
        pmt2 = temp_base + np.random.normal(-1, 1.0)  # Sensor 2 slightly lower reading
        oven = temp_base + np.random.normal(5, 2.0)   # Oven air typically higher
        
        pmt_sensor_1.append(pmt1)
        pmt_sensor_2.append(pmt2)
        oven_air_temp.append(oven)
    
    # Create CSV content with metadata
    csv_content = f"""# job_id: cure_test_{scenario}
# method: PMT
# operator: Test Engineer
# part_number: example_part_001
# powder_type: polyester_white
# cure_spec: 180C_10min_PMT
# timestamp_start: {start_time.isoformat()}
# scenario: {scenario}

timestamp,pmt_sensor_1,pmt_sensor_2,oven_air_temp_C
"""
    
    for ts, pmt1, pmt2, oven in zip(timestamps, pmt_sensor_1, pmt_sensor_2, oven_air_temp):
        csv_content += f"{ts.isoformat()},{pmt1:.2f},{pmt2:.2f},{oven:.2f}\n"
    
    # Write to temporary file  
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    temp_file.write(csv_content)
    temp_file.close()
    
    return temp_file.name


def create_cure_specification(scenario="pass"):
    """Create a cure specification for the test scenario."""
    spec_data = {
        "version": "1.0",
        "job": {
            "job_id": f"cure_test_{scenario}"
        },
        "spec": {
            "method": "PMT",
            "target_temp_C": 180.0,
            "hold_time_s": 600,  # 10 minutes required hold
            "sensor_uncertainty_C": 2.0
        },
        "data_requirements": {
            "max_sample_period_s": 60.0,
            "allowed_gaps_s": 90.0
        },
        "sensor_selection": {
            "mode": "min_of_set",  # Conservative - use minimum reading
            "sensors": ["pmt_sensor_1", "pmt_sensor_2"],
            "require_at_least": 1
        },
        "logic": {
            "continuous": True,  # Require continuous hold time
            "max_total_dips_s": 0
        },
        "reporting": {
            "units": "C",
            "language": "en", 
            "timezone": "UTC"
        }
    }
    
    return SpecV1(**spec_data)


def run_complete_workflow(scenario="pass"):
    """Run the complete ProofKit workflow for a given scenario."""
    print(f"\nRunning ProofKit workflow for scenario: {scenario.upper()}")
    print("=" * 60)
    
    # Step 1: Create synthetic cure data
    print("1. Creating synthetic cure data...")
    csv_path = create_cure_example_csv(scenario)
    print(f"   ✓ Generated CSV: {csv_path}")
    
    try:
        # Step 2: Load CSV with metadata
        print("\n2. Loading and parsing CSV...")
        df, metadata = load_csv_with_metadata(csv_path)
        print(f"   ✓ Loaded {len(df)} samples")
        print(f"   ✓ Metadata: {metadata.get('job_id', 'unknown')} - {metadata.get('scenario', 'unknown')}")
        
        # Step 3: Create specification
        print("\n3. Creating cure specification...")
        spec = create_cure_specification(scenario)
        print(f"   ✓ Target: {spec.spec.target_temp_C}°C for {spec.spec.hold_time_s}s")
        print(f"   ✓ Threshold: {spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C}°C (conservative)")
        print(f"   ✓ Sensors: {spec.sensor_selection.sensors} ({spec.sensor_selection.mode})")
        
        # Step 4: Normalize the data
        print("\n4. Normalizing temperature data...")
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,
            allowed_gaps_s=spec.data_requirements.allowed_gaps_s,
            max_sample_period_s=spec.data_requirements.max_sample_period_s
        )
        print(f"   ✓ Normalized to {len(normalized_df)} samples at 30s intervals")
        
        # Step 5: Make cure decision
        print("\n5. Making cure decision...")
        decision = make_decision(normalized_df, spec)
        decision_status = "PASS" if decision.pass_ else "FAIL"
        print(f"   ✓ Decision: {decision_status}")
        print(f"   ✓ Hold time: {decision.actual_hold_time_s:.0f}s / {decision.required_hold_time_s}s")
        print(f"   ✓ Temperature range: {decision.min_temp_C:.1f}°C to {decision.max_temp_C:.1f}°C")
        
        if decision.reasons:
            print("   ✓ Reasons:")
            for reason in decision.reasons:
                print(f"     • {reason}")
        
        if decision.warnings:
            print("   ⚠ Warnings:")
            for warning in decision.warnings:
                print(f"     • {warning}")
        
        # Step 6: Validate inputs for plotting
        print("\n6. Validating plot inputs...")
        validation_errors = validate_plot_inputs(normalized_df, spec, decision)
        if validation_errors:
            print("   ❌ Validation errors:")
            for error in validation_errors:
                print(f"     • {error}")
            return False
        else:
            print("   ✓ All inputs valid for plotting")
        
        # Step 7: Generate proof plot
        print("\n7. Generating proof plot...")
        output_dir = os.path.join(os.path.dirname(__file__), "outputs")
        os.makedirs(output_dir, exist_ok=True)
        plot_path = os.path.join(output_dir, f"proof_plot_{scenario}.png")
        
        generated_plot_path = generate_proof_plot(normalized_df, spec, decision, plot_path)
        print(f"   ✓ Plot generated: {generated_plot_path}")
        
        # Step 8: Summary
        print(f"\n🎯 WORKFLOW COMPLETE - {decision_status}")
        print(f"   • Job ID: {spec.job.job_id}")
        print(f"   • Decision: {decision_status}")
        print(f"   • Hold Time: {decision.actual_hold_time_s:.0f}s / {decision.required_hold_time_s}s")
        print(f"   • Plot: {generated_plot_path}")
        
        # Save decision as JSON for reference
        decision_path = os.path.join(output_dir, f"decision_{scenario}.json")
        decision_dict = decision.model_dump()
        with open(decision_path, 'w') as f:
            json.dump(decision_dict, f, indent=2, default=str)
        print(f"   • Decision JSON: {decision_path}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up temporary CSV
        if os.path.exists(csv_path):
            os.unlink(csv_path)


def main():
    """Run plot generation examples for different scenarios."""
    print("ProofKit Plot Generation Example")
    print("=" * 60)
    print("This example demonstrates the complete M1-M2-M3 workflow:")
    print("• M1: CSV normalization (core/normalize.py)")
    print("• M2: Cure decision algorithm (core/decide.py)")  
    print("• M3: Proof plot generation (core/plot.py)")
    
    scenarios = [
        ("pass", "Successful cure with proper hold time"),
        ("fail_short_hold", "Failed cure - insufficient hold time"),
        ("fail_no_threshold", "Failed cure - never reaches threshold")
    ]
    
    results = {}
    
    for scenario, description in scenarios:
        print(f"\n{'='*20} SCENARIO: {scenario.upper()} {'='*20}")
        print(f"Description: {description}")
        
        success = run_complete_workflow(scenario)
        results[scenario] = success
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    
    for scenario, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{scenario:20} {status}")
    
    output_dir = os.path.join(os.path.dirname(__file__), "outputs")
    if os.path.exists(output_dir):
        files = os.listdir(output_dir)
        plot_files = [f for f in files if f.endswith('.png')]
        json_files = [f for f in files if f.endswith('.json')]
        
        print(f"\nGenerated files in {output_dir}:")
        print(f"• Plots: {len(plot_files)} files")
        for plot_file in sorted(plot_files):
            print(f"  - {plot_file}")
        print(f"• Decision JSON: {len(json_files)} files")
        for json_file in sorted(json_files):
            print(f"  - {json_file}")
    
    print(f"\n🎯 Plot generation example complete!")
    print(f"   View the generated plots to see M3 requirements:")
    print(f"   • PMT temperature data (blue line)")
    print(f"   • Target temperature (green dashed line)")
    print(f"   • Conservative threshold (red dashed line)")
    print(f"   • Hold intervals (green shaded areas)")
    print(f"   • Pass/fail status and metrics")


if __name__ == "__main__":
    main()