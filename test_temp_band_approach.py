#!/usr/bin/env python3
"""
Test if using temp_band_C.min instead of conservative threshold would fix the pass case.
"""

import sys
import json
import pandas as pd
from pathlib import Path
from core.models import SpecV1
from core.normalize import load_csv_with_metadata, normalize_temperature_data


def test_temp_band_approach():
    """Test pass case with temp_band_C.min as threshold."""
    
    csv_path = Path('audit/fixtures/powder/pass.csv')
    spec_path = Path('audit/fixtures/powder/pass.json')
    
    with open(spec_path, 'r') as f:
        spec_data = json.load(f)
    
    df, metadata = load_csv_with_metadata(csv_path)
    
    # Get thresholds
    target = spec_data['spec']['target_temp_C']
    uncertainty = spec_data['spec']['sensor_uncertainty_C'] 
    conservative_threshold = target + uncertainty
    temp_band_min = spec_data['spec']['temp_band_C']['min']
    
    print(f"Target: {target}°C")
    print(f"Sensor uncertainty: {uncertainty}°C") 
    print(f"Conservative threshold (target + uncertainty): {conservative_threshold}°C")
    print(f"Temp band min: {temp_band_min}°C")
    print(f"Required hold time: {spec_data['spec']['hold_time_s']}s")
    print()
    
    # Test different thresholds
    thresholds_to_test = [
        ("Conservative", conservative_threshold),
        ("Temp band min", temp_band_min),
        ("Target only", target)
    ]
    
    for name, threshold in thresholds_to_test:
        # Check hold time with this threshold
        above_threshold = df['sensor_1'] >= threshold
        
        # Calculate continuous hold time 
        continuous_periods = []
        in_period = False
        start_idx = None
        
        for i, is_above in enumerate(above_threshold):
            if is_above and not in_period:
                start_idx = i
                in_period = True
            elif not is_above and in_period:
                continuous_periods.append((start_idx, i-1))
                in_period = False
        
        if in_period and start_idx is not None:
            continuous_periods.append((start_idx, len(above_threshold)-1))
        
        if continuous_periods:
            max_period = max(continuous_periods, key=lambda p: p[1] - p[0])
            max_continuous_time = (max_period[1] - max_period[0] + 1) * 10  # 10s per sample
        else:
            max_continuous_time = 0
            
        total_time_above = above_threshold.sum() * 10
        
        print(f"{name} threshold ({threshold}°C):")
        print(f"  Total time above: {total_time_above}s")
        print(f"  Max continuous time: {max_continuous_time}s")
        print(f"  Would pass hold time requirement: {'YES' if max_continuous_time >= spec_data['spec']['hold_time_s'] else 'NO'}")
        print()


if __name__ == '__main__':
    test_temp_band_approach()