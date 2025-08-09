#!/usr/bin/env python3
"""
Debug the pass case by creating synthetic data that should definitely pass.
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
from core.models import SpecV1
from core.normalize import normalize_temperature_data
from core.metrics_powder import validate_powder_coating_cure


def create_ideal_pass_data():
    """Create synthetic data that should pass all requirements."""
    
    # Create timestamps every 30 seconds for 20 minutes
    start_time = datetime(2024, 1, 1, 10, 0, 0)
    timestamps = []
    for i in range(41):  # 41 samples = 20 minutes at 30s intervals
        timestamps.append(start_time + timedelta(seconds=i*30))
    
    # Create temperature profile:
    # - Slow ramp from 25°C to 185°C over first 10 minutes (5°C/min)
    # - Hold at 185°C for 10 minutes
    temperatures = []
    for i in range(41):
        if i <= 20:  # First 20 samples (10 minutes) - ramp up
            temp = 25 + (i * 8)  # 8°C per 30-second step = 16°C/min... too fast
        else:  # Hold period
            temp = 185.0
        temperatures.append(temp)
    
    # Actually, let's be more careful about ramp rate
    temperatures = []
    for i in range(41):
        if i <= 32:  # First 32 samples (16 minutes) - slow ramp
            temp = 25 + (i * 5)  # 5°C per 30s = 10°C/min exactly
        else:  # Hold period for 4 minutes
            temp = 185.0
        temperatures.append(temp)
    
    # Create DataFrame
    df = pd.DataFrame({
        'timestamp': timestamps,
        'sensor_1': temperatures,
        'sensor_2': [t - 0.3 for t in temperatures],  # Slightly lower
        'sensor_3': [t + 0.2 for t in temperatures]   # Slightly higher  
    })
    
    return df


def test_ideal_data():
    """Test with ideal synthetic data."""
    
    # Load original spec
    spec_path = Path('audit/fixtures/powder/pass.json')
    with open(spec_path, 'r') as f:
        spec_data = json.load(f)
    
    # Create ideal test data
    df = create_ideal_pass_data()
    
    print("=== SYNTHETIC IDEAL DATA ===")
    print(f"Data shape: {df.shape}")
    print(f"Temperature range: {df.sensor_1.min():.1f}°C to {df.sensor_1.max():.1f}°C")
    print(f"Duration: {len(df)} samples = {(len(df)-1)*30}s")
    
    # Check against thresholds
    target = spec_data['spec']['target_temp_C']
    uncertainty = spec_data['spec']['sensor_uncertainty_C'] 
    conservative_threshold = target + uncertainty
    
    above_conservative = (df.sensor_1 >= conservative_threshold).sum()
    print(f"Samples above conservative threshold ({conservative_threshold}°C): {above_conservative} = {above_conservative*30}s")
    print(f"Required hold time: {spec_data['spec']['hold_time_s']}s")
    
    # Test normalization
    spec = SpecV1(**spec_data)
    
    try:
        # Convert to CSV-like format for normalization
        normalized_df = pd.DataFrame({
            'timestamp': df['timestamp'],
            'sensor_1': df['sensor_1'],
            'sensor_2': df['sensor_2'], 
            'sensor_3': df['sensor_3']
        })
        
        # Test the validation
        result = validate_powder_coating_cure(normalized_df, spec)
        
        print(f"\n=== VALIDATION RESULT ===")
        print(f"Status: {result.status}")
        print(f"Pass: {result.pass_}")
        print(f"Actual hold time: {result.actual_hold_time_s}s")
        print(f"Reasons: {result.reasons}")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")


if __name__ == '__main__':
    test_ideal_data()