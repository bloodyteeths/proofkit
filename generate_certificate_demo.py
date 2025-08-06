#!/usr/bin/env python3
"""
Generate demo certificate using the new ISO-style design.
Uses existing test fixtures and data.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.models import SpecV1, DecisionResult
from core.render_certificate_premium import generate_premium_certificate as generate_certificate_pdf
from tests.helpers import load_spec_fixture_validated, load_csv_fixture

# Create sample plot
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def create_sample_plot():
    """Create a professional temperature plot."""
    plot_path = Path("temp_plot_demo.png")
    
    # Create temperature data
    import numpy as np
    time = np.linspace(0, 30, 180)  # 30 minutes, 180 samples
    temp_base = 170 + 5 * np.sin(time / 5) + np.random.normal(0, 0.5, len(time))
    temp = np.where(time < 5, 20 + (temp_base - 20) * time / 5, temp_base)  # Ramp up
    
    # Create professional plot
    fig, ax = plt.subplots(figsize=(14, 7), dpi=100)
    
    # Plot temperature line
    ax.plot(time, temp, 'b-', linewidth=2, label='PMT-01 Temperature', alpha=0.8)
    
    # Add threshold lines
    ax.axhline(y=172, color='#D73502', linestyle='--', linewidth=1.5, 
               label='Conservative Threshold (172°C)', alpha=0.7)
    ax.axhline(y=170, color='#219653', linestyle=':', linewidth=1.5,
               label='Target Temperature (170°C)', alpha=0.7)
    
    # Shade hold region
    hold_start = 5
    hold_end = 25
    ax.axvspan(hold_start, hold_end, alpha=0.1, color='green', label='Hold Period')
    
    # Styling
    ax.set_xlabel('Time (minutes)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Temperature (°C)', fontsize=11, fontweight='bold')
    ax.set_title('Powder-Coat Cure Temperature Profile', fontsize=13, fontweight='bold', pad=15)
    ax.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    ax.legend(loc='lower right', fontsize=9, framealpha=0.95)
    
    # Set limits
    ax.set_xlim(0, 30)
    ax.set_ylim(15, 180)
    
    # Add annotations
    ax.annotate('Ramp Up', xy=(2.5, 100), xytext=(2.5, 50),
                arrowprops=dict(arrowstyle='->', color='gray', alpha=0.5),
                fontsize=9, color='gray')
    ax.annotate('Stable Hold', xy=(15, 173), xytext=(15, 178),
                arrowprops=dict(arrowstyle='->', color='gray', alpha=0.5),
                fontsize=9, color='gray')
    
    # Style the plot area
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(0.5)
    ax.spines['bottom'].set_linewidth(0.5)
    
    plt.tight_layout()
    plt.savefig(plot_path, dpi=100, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return plot_path

def main():
    """Generate demo certificate."""
    
    # Load test fixtures
    spec = load_spec_fixture_validated("min_powder_spec.json")
    
    # Create a PASS decision
    decision = DecisionResult(
        pass_=True,
        job_id="CERT-2024-0115-A",
        target_temp_C=170.0,
        conservative_threshold_C=172.0,
        actual_hold_time_s=1200.0,  # 20 minutes
        required_hold_time_s=480,    # 8 minutes required
        max_temp_C=175.3,
        min_temp_C=171.2,
        reasons=[
            "Temperature maintained above conservative threshold (172.0°C) for required duration",
            "Actual hold time (1200s) exceeded minimum requirement (480s) by 150%",
            "Maximum ramp rate (3.2°C/min) within acceptable limits"
        ],
        warnings=[]
    )
    
    # Override job ID for demo
    spec.job.job_id = "CERT-2024-0115-A"
    
    # Create plot
    print("Creating temperature plot...")
    plot_path = create_sample_plot()
    
    # Generate certificate
    print("Generating professional ISO-style certificate...")
    pdf_bytes = generate_certificate_pdf(
        spec=spec,
        decision=decision,
        plot_path=plot_path,
        certificate_no="PC-2024-0115-A",
        verification_hash="a7f3d2e8b9c1f4a6e5d8c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2",
        output_path="proofkit_certificate_PC-2024-0115-A.pdf",
        timestamp=datetime.now(timezone.utc)
    )
    
    print(f"✓ Certificate generated: proofkit_certificate_PC-2024-0115-A.pdf")
    print(f"  Size: {len(pdf_bytes):,} bytes")
    
    # Also test FAIL case
    decision_fail = DecisionResult(
        pass_=False,
        job_id="CERT-2024-0115-B",
        target_temp_C=170.0,
        conservative_threshold_C=172.0,
        actual_hold_time_s=240.0,  # Only 4 minutes
        required_hold_time_s=480,   # 8 minutes required
        max_temp_C=171.8,
        min_temp_C=165.3,
        reasons=[
            "Insufficient hold time above conservative threshold",
            "Actual hold time (240s) only reached 50% of requirement (480s)",
            "Temperature dropped below threshold at 12:35 mark"
        ],
        warnings=["Multiple temperature excursions detected", "Sensor PMT-02 showed anomalies"]
    )
    
    spec.job.job_id = "CERT-2024-0115-B"
    
    print("\nGenerating FAIL certificate...")
    pdf_bytes_fail = generate_certificate_pdf(
        spec=spec,
        decision=decision_fail,
        plot_path=plot_path,
        certificate_no="PC-2024-0115-B",
        verification_hash="b8e4c3f9a0e1d2c7b6f5a4e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0",
        output_path="proofkit_certificate_PC-2024-0115-B.pdf",
        timestamp=datetime.now(timezone.utc)
    )
    
    print(f"✓ FAIL certificate generated: proofkit_certificate_PC-2024-0115-B.pdf")
    print(f"  Size: {len(pdf_bytes_fail):,} bytes")
    
    # Clean up temp plot
    plot_path.unlink()
    
    print("\n✅ Demo certificates generated successfully!")
    print("   - proofkit_certificate_PC-2024-0115-A.pdf (PASS)")
    print("   - proofkit_certificate_PC-2024-0115-B.pdf (FAIL)")

if __name__ == "__main__":
    main()