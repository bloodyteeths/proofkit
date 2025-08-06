#!/usr/bin/env python3
"""Test Pro Tier Certificate Generator using actual core renderer"""

import json
import sys
sys.path.append('.')

# Use actual core certificate renderer
from core.render_certificate_pro import generate_certificate_pdf

def generate_pro_tier_certificate():
    """Generate Pro tier certificate using core renderer with QR codes."""
    # Load test data and convert to proper models
    with open('data/test_spec.json', 'r') as f:
        spec_data = json.load(f)
    
    with open('data/test_decision_fail.json', 'r') as f:
        decision_data = json.load(f)
    
    # Convert to proper model objects (simplified for testing)
    from types import SimpleNamespace
    
    # Create spec object
    job = SimpleNamespace(job_id="PRO_TIER_TEST")
    spec_detail = SimpleNamespace(
        target_temp_C=spec_data.get('target_temp_C', 170),
        hold_time_s=spec_data.get('hold_time_s', 480),
        sensor_uncertainty_C=spec_data.get('sensor_uncertainty_C', 2)
    )
    data_req = SimpleNamespace(
        max_sample_period_s=spec_data.get('max_sample_period_s', 10),
        allowed_gaps_s=spec_data.get('allowed_gaps_s', 30)
    )
    logic = SimpleNamespace(continuous=True)
    
    spec = SimpleNamespace(job=job, spec=spec_detail, data_requirements=data_req, logic=logic)
    
    # Create decision object  
    decision = SimpleNamespace(
        pass_=decision_data.get('pass', False),
        actual_hold_time_s=decision_data.get('actual_hold_time_s', 0),
        required_hold_time_s=decision_data.get('required_hold_time_s', 480),
        max_temp_C=decision_data.get('max_temp_C', 0),
        min_temp_C=decision_data.get('min_temp_C', 0),
        conservative_threshold_C=decision_data.get('conservative_threshold_C', 172),
        reasons=decision_data.get('reasons', [])
    )
    
    # Generate PDF with QR code
    output_path = "certificate_PRO_TIER_FAIL.pdf"
    pdf_bytes = generate_certificate_pdf(
        spec, 
        decision, 
        plot_path="data/temperature_plot.png",
        certificate_no="PRO_TIER_TEST_FAIL",
        verification_hash="pro_tier_test_hash_fail_" + str(hash(str(decision_data))),
        output_path=output_path
    )
    
    return output_path

if __name__ == "__main__":
    try:
        output_path = generate_pro_tier_certificate()
        print(f"✅ Pro Tier certificate generated: {output_path}")
        print("   Features: CMYK colors, fixed micro-text borders, professional layout")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()