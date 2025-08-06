#!/usr/bin/env python3
"""Create a sample temperature plot for testing."""

import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def create_temperature_plot():
    """Create a professional temperature plot."""
    # Create temperature data
    time_minutes = np.linspace(0, 30, 180)  # 30 minutes, 180 data points
    
    # Simulate powder coating cure cycle
    temp_profile = []
    for t in time_minutes:
        if t < 5:  # Ramp up phase (0-5 minutes)
            temp = 20 + (170 - 20) * (t / 5) + np.random.normal(0, 1)
        elif t < 25:  # Hold phase (5-25 minutes)
            temp = 170 + 3 * np.sin(t / 3) + np.random.normal(0, 0.8)
        else:  # Cool down phase (25-30 minutes)
            temp = 170 - (170 - 100) * ((t - 25) / 5) + np.random.normal(0, 2)
        
        temp_profile.append(max(temp, 15))  # Minimum temperature
    
    temp_profile = np.array(temp_profile)
    
    # Create professional plot
    plt.style.use('default')
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    
    # Plot temperature line
    ax.plot(time_minutes, temp_profile, 'b-', linewidth=2.5, 
            label='PMT-01 Temperature', alpha=0.9)
    
    # Add threshold lines
    ax.axhline(y=172, color='#D73502', linestyle='--', linewidth=2, 
               label='Conservative Threshold (172°C)', alpha=0.8)
    ax.axhline(y=170, color='#219653', linestyle=':', linewidth=2,
               label='Target Temperature (170°C)', alpha=0.8)
    
    # Shade hold region where temp > threshold
    hold_mask = temp_profile >= 172
    hold_regions = []
    start_idx = None
    
    for i, above_threshold in enumerate(hold_mask):
        if above_threshold and start_idx is None:
            start_idx = i
        elif not above_threshold and start_idx is not None:
            hold_regions.append((start_idx, i))
            start_idx = None
    
    if start_idx is not None:
        hold_regions.append((start_idx, len(temp_profile) - 1))
    
    for start_idx, end_idx in hold_regions:
        if end_idx - start_idx > 10:  # Only shade significant hold periods
            ax.axvspan(time_minutes[start_idx], time_minutes[end_idx], 
                      alpha=0.15, color='green', label='Hold Period' if len(hold_regions) == 1 else '')
    
    # Styling
    ax.set_xlabel('Time (minutes)', fontsize=12, fontweight='bold', color='#334E68')
    ax.set_ylabel('Temperature (°C)', fontsize=12, fontweight='bold', color='#334E68')
    ax.set_title('Powder-Coat Cure Temperature Profile', fontsize=14, fontweight='bold', 
                color='#102A43', pad=20)
    
    # Grid
    ax.grid(True, alpha=0.3, linestyle=':', linewidth=0.8, color='#334E68')
    ax.set_axisbelow(True)
    
    # Legend - positioned well outside plot area to avoid covering any data
    legend = ax.legend(bbox_to_anchor=(1.15, 0.85), loc='upper left', fontsize=7, 
                      framealpha=0.95, fancybox=True, shadow=False)
    legend.get_frame().set_facecolor('#F7F9FC')
    legend.get_frame().set_edgecolor('#9FB3C8')
    legend.get_frame().set_linewidth(0.5)
    
    # Set limits with padding
    ax.set_xlim(0, 30)
    ax.set_ylim(min(temp_profile) - 10, max(temp_profile) + 20)
    
    # Add annotations
    max_temp_idx = np.argmax(temp_profile)
    ax.annotate(f'Peak: {temp_profile[max_temp_idx]:.1f}°C', 
                xy=(time_minutes[max_temp_idx], temp_profile[max_temp_idx]),
                xytext=(time_minutes[max_temp_idx] + 3, temp_profile[max_temp_idx] + 5),
                arrowprops=dict(arrowstyle='->', color='#102A43', alpha=0.7),
                fontsize=9, color='#102A43', weight='bold')
    
    # Professional styling
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#9FB3C8')
    ax.spines['bottom'].set_color('#9FB3C8')
    ax.spines['left'].set_linewidth(1)
    ax.spines['bottom'].set_linewidth(1)
    
    # Tick styling
    ax.tick_params(axis='both', which='major', labelsize=10, colors='#334E68')
    ax.tick_params(axis='x', which='major', length=6, width=1)
    ax.tick_params(axis='y', which='major', length=6, width=1)
    
    plt.tight_layout(pad=1.5)
    
    # Save plot
    plot_path = Path("data/temperature_plot.png")
    plot_path.parent.mkdir(exist_ok=True)
    
    plt.savefig(plot_path, dpi=150, bbox_inches='tight', facecolor='white', 
                edgecolor='none', pad_inches=0.1)
    plt.close()
    
    print(f"✓ Temperature plot created: {plot_path}")
    return plot_path

if __name__ == "__main__":
    create_temperature_plot()