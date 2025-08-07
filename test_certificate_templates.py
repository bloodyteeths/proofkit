#!/usr/bin/env python3
"""
Test script to verify certificate templates work for different user plans.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from core.models import SpecV1, DecisionResult
from core.render_pdf import generate_proof_pdf

def create_test_data():
    """Create test specification and decision data."""
    
    # Create test spec
    spec_data = {
        "job": {
            "job_id": "test123456",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_email": "test@example.com"
        },
        "spec": {
            "method": "powder-coat",
            "target_temp_C": 180.0,
            "hold_time_s": 1200,
            "sensor_uncertainty_C": 2.0
        },
        "data_requirements": {
            "max_sample_period_s": 60,
            "allowed_gaps_s": 120
        }
    }
    spec = SpecV1(**spec_data)
    
    # Create test decision
    decision_data = {
        "pass_": True,
        "actual_hold_time_s": 1245,
        "required_hold_time_s": 1200,
        "max_temp_C": 185.3,
        "min_temp_C": 178.2,
        "conservative_threshold_C": 182.0,
        "reasons": ["Temperature maintained above threshold for required duration"],
        "metrics": {
            "target_temp_C": 180.0,
            "actual_hold_time_s": 1245,
            "required_hold_time_s": 1200,
            "max_temp_C": 185.3,
            "min_temp_C": 178.2
        }
    }
    decision = DecisionResult(**decision_data)
    
    return spec, decision

def test_certificate_generation():
    """Test certificate generation for different user plans."""
    
    # Create test data
    spec, decision = create_test_data()
    
    # Use an existing plot image for testing (or create a dummy one)
    plot_path = Path("examples/golden/autoclave_plot.png")
    if not plot_path.exists():
        # Create a dummy plot if the example doesn't exist
        from PIL import Image
        img = Image.new('RGB', (800, 600), color='white')
        plot_path = Path("test_plot.png")
        img.save(plot_path)
    
    # Test plans
    test_plans = [
        ('free', 'Free tier with basic template'),
        ('starter', 'Starter tier with basic template'),
        ('pro', 'Pro tier with professional template'),
        ('business', 'Business tier with premium template'),
        ('enterprise', 'Enterprise tier with premium template')
    ]
    
    output_dir = Path("test_certificates")
    output_dir.mkdir(exist_ok=True)
    
    for plan, description in test_plans:
        print(f"\nTesting {plan} plan: {description}")
        try:
            # Generate certificate
            pdf_bytes = generate_proof_pdf(
                spec=spec,
                decision=decision,
                plot_path=str(plot_path),
                user_plan=plan
            )
            
            # Save to file
            output_file = output_dir / f"certificate_{plan}.pdf"
            with open(output_file, 'wb') as f:
                f.write(pdf_bytes)
            
            print(f"✓ Generated: {output_file}")
            print(f"  Size: {len(pdf_bytes):,} bytes")
            
        except Exception as e:
            print(f"✗ Failed for {plan}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n✅ Test certificates saved to: {output_dir}")
    print("Please review the PDFs to verify the correct templates are being used.")

if __name__ == "__main__":
    test_certificate_generation()