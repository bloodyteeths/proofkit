#!/usr/bin/env python3
"""
Setup script to create required directory structure and test data for certificate generation.
Creates mock files if real ones don't exist (for testing only).
"""

import os
import json
from pathlib import Path

def setup_directories():
    """Create required directories."""
    dirs = ['fonts', 'assets', 'data']
    for d in dirs:
        Path(d).mkdir(exist_ok=True)
        print(f"✓ Created directory: {d}/")

def create_mock_svg():
    """Create a mock SVG logo if it doesn't exist."""
    svg_path = Path("assets/proofkit_logo_icon.svg")
    if not svg_path.exists():
        svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="45" fill="#23C48E"/>
  <path d="M 30 50 L 45 65 L 70 35" stroke="white" stroke-width="6" 
        stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>'''
        svg_path.write_text(svg_content)
        print(f"✓ Created mock SVG: {svg_path}")
    else:
        print(f"✓ SVG exists: {svg_path}")

def create_test_data():
    """Create test JSON data files."""
    # Specification data
    spec_data = {
        "job_id": "TEST-2024-001",
        "target_temp_C": 170.0,
        "hold_time_s": 480,
        "sensor_uncertainty_C": 2.0,
        "conservative_threshold_C": 172.0,
        "max_sample_period_s": 10,
        "allowed_gaps_s": 30,
        "hold_logic": "Continuous"
    }
    
    spec_path = Path("data/test_spec.json")
    spec_path.write_text(json.dumps(spec_data, indent=2))
    print(f"✓ Created test spec: {spec_path}")
    
    # Decision data - PASS
    decision_pass = {
        "pass": True,
        "actual_hold_time_s": 540,
        "required_hold_time_s": 480,
        "max_temp_C": 175.3,
        "min_temp_C": 171.2,
        "conservative_threshold_C": 172.0,
        "reasons": [
            "Temperature maintained above conservative threshold for required duration",
            "Actual hold time exceeded requirement by 12.5%",
            "All sensor readings within acceptable range"
        ],
        "verification_hash": "a7f3d2e8b9c1f4a6e5d8c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2"
    }
    
    pass_path = Path("data/test_decision_pass.json")
    pass_path.write_text(json.dumps(decision_pass, indent=2))
    print(f"✓ Created test decision (PASS): {pass_path}")
    
    # Decision data - FAIL
    decision_fail = {
        "pass": False,
        "actual_hold_time_s": 240,
        "required_hold_time_s": 480,
        "max_temp_C": 171.8,
        "min_temp_C": 165.3,
        "conservative_threshold_C": 172.0,
        "reasons": [
            "Insufficient hold time above conservative threshold",
            "Temperature dropped below threshold at 12:35",
            "Only 50% of required hold time achieved"
        ],
        "verification_hash": "b8e4c3f9a0e1d2c7b6f5a4e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0"
    }
    
    fail_path = Path("data/test_decision_fail.json")
    fail_path.write_text(json.dumps(decision_fail, indent=2))
    print(f"✓ Created test decision (FAIL): {fail_path}")

def check_fonts():
    """Check for required font files."""
    required_fonts = [
        "fonts/CormorantGaramondSC-ExtraBold.otf",
        "fonts/Inter-Regular.otf",
        "fonts/Inter-Medium.otf",
        "fonts/GreatVibes-Regular.otf"
    ]
    
    missing = []
    for font in required_fonts:
        if Path(font).exists():
            print(f"✓ Font found: {font}")
        else:
            missing.append(font)
            print(f"✗ Font missing: {font}")
    
    if missing:
        print("\n⚠️  Missing fonts - Certificate generation will fail!")
        print("Please add the following font files:")
        for f in missing:
            print(f"  - {f}")
        print("\nNote: These exact font files are required. No substitutions allowed.")
    
    return len(missing) == 0

def main():
    print("Setting up certificate generation environment...\n")
    
    setup_directories()
    create_mock_svg()
    create_test_data()
    fonts_ok = check_fonts()
    
    print("\n" + "="*60)
    if fonts_ok:
        print("✅ Setup complete! You can now run:")
        print("\n  python generate_certificate.py \\")
        print("    --spec-json data/test_spec.json \\")
        print("    --decision-json data/test_decision_pass.json \\")
        print("    --certificate-no TEST-2024-001")
    else:
        print("⚠️  Setup incomplete - missing required fonts")
        print("Add the font files and run this script again.")

if __name__ == "__main__":
    main()