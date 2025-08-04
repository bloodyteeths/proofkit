#!/usr/bin/env python3
"""
ProofKit CSV Normalization Example

This example demonstrates how to use the normalize.py module
to process CSV temperature data according to ProofKit specifications.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.normalize import load_csv_with_metadata, normalize_temperature_data
from core.models import SpecV1
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import tempfile

def create_example_csv():
    """Create an example CSV file with metadata and temperature data."""
    # Generate synthetic cure data
    start_time = datetime(2025, 1, 15, 10, 0, 0)  # Start at 10:00 AM
    duration_minutes = 30
    interval_seconds = 25  # Slightly irregular sampling
    
    timestamps = []
    temps_f = []  # Fahrenheit temperatures
    temps_c = []  # Celsius temperatures
    
    for i in range(int(duration_minutes * 60 / interval_seconds)):
        # Create timestamp with slight jitter
        ts = start_time + timedelta(seconds=i * interval_seconds + np.random.uniform(-2, 2))
        timestamps.append(ts)
        
        # Simulate heating curve: ramp up, then hold at target
        time_mins = i * interval_seconds / 60
        if time_mins < 5:  # Ramp phase
            temp_c = 20 + (160 * time_mins / 5)  # Ramp to 180°C over 5 minutes
        else:  # Hold phase
            temp_c = 180 + np.random.normal(0, 1.5)  # Hold at 180°C ± noise
        
        # Convert to Fahrenheit for one sensor
        temp_f = temp_c * 9/5 + 32
        
        temps_f.append(temp_f + np.random.normal(0, 1))  # Add sensor noise
        temps_c.append(temp_c + np.random.normal(0, 0.8))  # Different noise for C sensor
    
    # Create CSV content with metadata
    csv_content = f"""# job_id: powder_coat_batch_001
# method: PMT
# operator: John Smith
# part_number: steel_bracket_v2
# cure_spec: 180C_10min_hold
# timestamp_start: {start_time.isoformat()}

timestamp,pmt_temp_degF,oven_temp_C,thermocouple_1_f
"""
    
    for ts, tf, tc, tc2 in zip(timestamps, temps_f, temps_c, temps_f):
        csv_content += f"{ts.isoformat()},{tf:.2f},{tc:.2f},{tc2+5:.2f}\n"
    
    # Write to temporary file  
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    temp_file.write(csv_content)
    temp_file.close()
    
    return temp_file.name

def main():
    """Run the normalization example."""
    print("ProofKit CSV Normalization Example")
    print("=" * 40)
    
    # Create example CSV
    csv_path = create_example_csv()
    print(f"Created example CSV: {csv_path}")
    
    try:
        # Step 1: Load CSV with metadata
        print("\n1. Loading CSV with metadata...")
        df, metadata = load_csv_with_metadata(csv_path)
        print(f"   - Loaded {len(df)} samples")
        print(f"   - Metadata extracted: {len(metadata)} fields")
        for key, value in metadata.items():
            print(f"     • {key}: {value}")
        
        print(f"   - Columns: {list(df.columns)}")
        print(f"   - Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        # Step 2: Create a specification for the normalization
        print("\n2. Creating specification...")
        spec_data = {
            "version": "1.0",
            "job": {"job_id": metadata.get("job_id", "unknown")},
            "spec": {
                "method": "PMT",
                "target_temp_C": 180.0,
                "hold_time_s": 600  # 10 minutes
            },
            "data_requirements": {
                "max_sample_period_s": 60.0,  # Allow up to 60s between samples
                "allowed_gaps_s": 120.0       # Allow gaps up to 2 minutes
            }
        }
        
        spec = SpecV1(**spec_data)
        print(f"   - Target: {spec.spec.target_temp_C}°C for {spec.spec.hold_time_s}s")
        print(f"   - Max sample period: {spec.data_requirements.max_sample_period_s}s")
        print(f"   - Allowed gaps: {spec.data_requirements.allowed_gaps_s}s")
        
        # Step 3: Normalize the data
        print("\n3. Normalizing temperature data...")
        normalized_df = normalize_temperature_data(
            df,
            target_step_s=30.0,  # Resample to 30-second intervals
            allowed_gaps_s=spec.data_requirements.allowed_gaps_s,
            max_sample_period_s=spec.data_requirements.max_sample_period_s,
            source_timezone=None  # Assume UTC
        )
        
        print(f"   - Normalized to {len(normalized_df)} samples at 30s intervals")
        print(f"   - Columns after normalization: {list(normalized_df.columns)}")
        
        # Show temperature column conversions
        temp_cols_before = [col for col in df.columns if 'temp' in col.lower()]
        temp_cols_after = [col for col in normalized_df.columns if 'temp' in col.lower()]
        
        print(f"   - Temperature columns before: {temp_cols_before}")
        print(f"   - Temperature columns after: {temp_cols_after}")
        
        # Step 4: Show sample of normalized data
        print("\n4. Sample of normalized data:")
        sample_df = normalized_df.head(10)
        for col in sample_df.columns:
            if 'temp' in col.lower():
                temps = sample_df[col].dropna()
                if len(temps) > 0:
                    print(f"   - {col}: {temps.mean():.1f}°C (avg), range {temps.min():.1f}°C to {temps.max():.1f}°C")
        
        print(f"\n✅ Normalization completed successfully!")
        print(f"   - Original samples: {len(df)}")
        print(f"   - Normalized samples: {len(normalized_df)}")
        print(f"   - Time span: {(normalized_df['timestamp'].max() - normalized_df['timestamp'].min()).total_seconds():.0f} seconds")
        
    except Exception as e:
        print(f"\n❌ Normalization failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        os.unlink(csv_path)

if __name__ == "__main__":
    main()