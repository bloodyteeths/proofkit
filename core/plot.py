"""
ProofKit Plot Generation

Generates matplotlib plots for powder-coat cure validation following M3 requirements.
Creates deterministic plots with PMT temperature data, target/threshold lines,
and shaded hold intervals for inspector-ready proof documentation.

Example usage:
    from core.plot import generate_proof_plot
    from core.models import SpecV1, DecisionResult
    
    # Load data and decision result
    spec = SpecV1(**spec_data)
    normalized_df = pd.read_csv("normalized.csv")
    decision = DecisionResult(**decision_data)
    
    # Generate plot
    plot_path = generate_proof_plot(
        normalized_df, spec, decision, "plot.png"
    )
    print(f"Plot saved to: {plot_path}")
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
import logging
import os

from core.models import SpecV1, DecisionResult, SensorMode, Industry
from core.decide import (
    combine_sensor_readings, 
    detect_temperature_columns,
    calculate_continuous_hold_time,
    calculate_cumulative_hold_time
)

logger = logging.getLogger(__name__)


class PlotError(Exception):
    """Raised when plot generation encounters errors."""
    pass


# Industry-specific color palettes (deterministic)
INDUSTRY_COLORS = {
    Industry.POWDER: {
        'primary': '#2E5BBA',  # Deep blue
        'secondary': '#8ECAE6',  # Light blue
        'accent': '#FFB300',  # Amber
        'target': '#219653',  # Green
        'threshold': '#D73502'  # Red-orange
    },
    Industry.HACCP: {
        'primary': '#7B2CBF',  # Purple
        'secondary': '#C77DFF',  # Light purple
        'accent': '#F72585',  # Pink
        'target': '#10451D',  # Dark green
        'threshold': '#E71D36'  # Red
    },
    Industry.AUTOCLAVE: {
        'primary': '#0077B6',  # Ocean blue
        'secondary': '#90E0EF',  # Sky blue
        'accent': '#00B4D8',  # Cyan
        'target': '#2D6A4F',  # Forest green
        'threshold': '#D00000'  # Pure red
    },
    Industry.STERILE: {
        'primary': '#06FFA5',  # Mint green
        'secondary': '#B7E4C7',  # Light green
        'accent': '#52B788',  # Medium green
        'target': '#2D6A4F',  # Dark green
        'threshold': '#BA1A1A'  # Dark red
    },
    Industry.CONCRETE: {
        'primary': '#6C757D',  # Gray
        'secondary': '#ADB5BD',  # Light gray
        'accent': '#FFC107',  # Yellow
        'target': '#198754',  # Success green
        'threshold': '#DC3545'  # Danger red
    },
    Industry.COLDCHAIN: {
        'primary': '#0D47A1',  # Deep blue
        'secondary': '#BBDEFB',  # Very light blue
        'accent': '#03DAC6',  # Teal
        'target': '#1B5E20',  # Dark green
        'threshold': '#B71C1C'  # Dark red
    }
}

# Default color palette
DEFAULT_COLORS = INDUSTRY_COLORS[Industry.POWDER]


def get_industry_colors(industry: Optional[Industry] = None) -> Dict[str, str]:
    """
    Get color palette for specified industry.
    
    Args:
        industry: Industry type for color selection
        
    Returns:
        Dictionary containing industry-specific colors
    """
    if industry and industry in INDUSTRY_COLORS:
        return INDUSTRY_COLORS[industry]
    return DEFAULT_COLORS


def configure_matplotlib_for_deterministic_rendering():
    """
    Configure matplotlib for consistent, deterministic rendering.
    
    Sets font family, sizes, DPI, and other parameters to ensure
    identical output across different environments.
    """
    # Ensure Agg backend for testing environment
    if os.getenv('PROOFKIT_TEST') == '1':
        import matplotlib
        matplotlib.use('Agg')
    
    plt.rcParams.update({
        # Font settings for consistency
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        
        # DPI and figure settings
        'figure.dpi': 100,
        'savefig.dpi': 100,
        'figure.figsize': (12, 8),
        
        # Deterministic backend settings
        'backend': 'Agg',  # Non-interactive backend
        'timezone': 'UTC',  # Consistent timezone handling
        
        # Grid and line settings
        'axes.grid': True,
        'grid.alpha': 0.3,
        'lines.linewidth': 1.5,
        'axes.linewidth': 0.8,
        
        # Margin settings
        'figure.autolayout': True,
        'axes.xmargin': 0.02,
        'axes.ymargin': 0.05,
        
        # Additional deterministic settings for testing
        'svg.fonttype': 'none' if os.getenv('PROOFKIT_TEST') == '1' else 'path',
        'text.antialiased': False if os.getenv('PROOFKIT_TEST') == '1' else True,
        'lines.antialiased': False if os.getenv('PROOFKIT_TEST') == '1' else True,
        'patch.antialiased': False if os.getenv('PROOFKIT_TEST') == '1' else True
    })


def extract_combined_pmt_data(df: pd.DataFrame, spec: SpecV1) -> Tuple[pd.Series, pd.Series, List[str]]:
    """
    Extract and combine PMT temperature data according to spec configuration.
    
    Args:
        df: Normalized DataFrame with temperature data
        spec: Cure process specification
        
    Returns:
        Tuple of (timestamp_series, combined_pmt_series, sensor_names_used)
        
    Raises:
        PlotError: If PMT data cannot be extracted
    """
    # Detect timestamp column
    timestamp_col = None
    for col in df.columns:
        if 'time' in col.lower() or pd.api.types.is_datetime64_any_dtype(df[col]):
            timestamp_col = col
            break
    
    if timestamp_col is None:
        raise PlotError("No timestamp column found in normalized data")
    
    # Ensure timestamps are datetime
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    
    # Detect temperature columns
    temp_columns = detect_temperature_columns(df)
    if not temp_columns:
        raise PlotError("No temperature columns found in normalized data")
    
    # Apply sensor selection from spec
    sensor_selection = spec.sensor_selection
    if sensor_selection and sensor_selection.sensors:
        # Use specified sensors
        available_sensors = [col for col in sensor_selection.sensors if col in temp_columns]
        if not available_sensors:
            raise PlotError(f"None of specified sensors found in data: {sensor_selection.sensors}")
        temp_columns = available_sensors
    
    # Calculate conservative threshold for majority_over_threshold mode
    conservative_threshold_C = spec.spec.target_temp_C + spec.spec.sensor_uncertainty_C
    
    # Combine sensor readings
    sensor_mode = sensor_selection.mode if sensor_selection else SensorMode.MIN_OF_SET
    require_at_least = sensor_selection.require_at_least if sensor_selection else None
    
    try:
        combined_pmt = combine_sensor_readings(
            df, temp_columns, sensor_mode, require_at_least, conservative_threshold_C
        )
    except Exception as e:
        raise PlotError(f"Failed to combine sensor readings: {str(e)}")
    
    return df[timestamp_col], combined_pmt, temp_columns


def find_hold_intervals(timestamps: pd.Series, temperatures: pd.Series, 
                       threshold_C: float, spec: SpecV1) -> List[Tuple[datetime, datetime]]:
    """
    Find hold intervals where temperature criteria are met.
    
    Args:
        timestamps: Timestamp series
        temperatures: Temperature series
        threshold_C: Conservative threshold temperature
        spec: Cure process specification
        
    Returns:
        List of (start_time, end_time) tuples for hold intervals
    """
    intervals = []
    
    # Get logic configuration
    if spec.logic:
        logic_continuous = spec.logic.continuous
        logic_max_dips = spec.logic.max_total_dips_s
    else:
        logic_continuous = True
        logic_max_dips = 0
    
    if logic_continuous:
        # Find continuous hold intervals
        hold_time_s, start_idx, end_idx = calculate_continuous_hold_time(
            temperatures, timestamps, threshold_C
        )
        
        if start_idx >= 0 and end_idx >= 0:
            start_time = timestamps.iloc[start_idx]
            end_time = timestamps.iloc[end_idx]
            intervals.append((start_time, end_time))
    else:
        # Find cumulative hold intervals
        hold_time_s, interval_indices = calculate_cumulative_hold_time(
            temperatures, timestamps, threshold_C, logic_max_dips
        )
        
        for start_idx, end_idx in interval_indices:
            start_time = timestamps.iloc[start_idx]
            end_time = timestamps.iloc[end_idx]
            intervals.append((start_time, end_time))
    
    return intervals


def create_temperature_plot(timestamps: pd.Series, temperatures: pd.Series,
                          spec: SpecV1, decision: DecisionResult,
                          sensor_names: List[str], industry: Optional[Industry] = None) -> plt.Figure:
    """
    Create the main temperature vs time plot.
    
    Args:
        timestamps: Timestamp series
        temperatures: Combined PMT temperature series
        spec: Cure process specification
        decision: Decision result
        sensor_names: List of sensor names used
        industry: Industry type for color palette selection
        
    Returns:
        Matplotlib figure object
    """
    # Get industry-specific colors
    colors_palette = get_industry_colors(industry)
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Convert timestamps to matplotlib dates for proper x-axis handling
    time_dates = mdates.date2num([ts.to_pydatetime() for ts in timestamps])
    
    # Plot main PMT line using industry primary color
    ax.plot(time_dates, temperatures, color=colors_palette['primary'], linewidth=2, 
            label='PMT Temperature', alpha=0.8)
    
    # Add target temperature line using industry target color
    target_temp = spec.spec.target_temp_C
    ax.axhline(y=target_temp, color=colors_palette['target'], linestyle='--', linewidth=2, 
               label=f'Target Temperature ({target_temp:.1f}°C)')
    
    # Add conservative threshold line using industry threshold color
    threshold_temp = decision.conservative_threshold_C
    ax.axhline(y=threshold_temp, color=colors_palette['threshold'], linestyle='--', linewidth=2,
               label=f'Conservative Threshold ({threshold_temp:.1f}°C)')
    
    # Find and shade hold intervals
    hold_intervals = find_hold_intervals(timestamps, temperatures, threshold_temp, spec)
    
    for i, (start_time, end_time) in enumerate(hold_intervals):
        start_date = mdates.date2num(start_time.to_pydatetime())
        end_date = mdates.date2num(end_time.to_pydatetime())
        width = end_date - start_date
        
        # Calculate y-range for shading
        y_min = ax.get_ylim()[0]
        y_max = max(temperatures.max(), threshold_temp) + 10
        height = y_max - y_min
        
        # Add shaded rectangle for hold interval using industry secondary color
        rect = Rectangle((start_date, y_min), width, height, 
                        facecolor=colors_palette['secondary'], alpha=0.3, 
                        label='Hold Interval' if i == 0 else "")
        ax.add_patch(rect)
    
    # Format x-axis for time display
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Set labels and title
    ax.set_xlabel('Time (HH:MM:SS)')
    ax.set_ylabel('Temperature (°C)')
    
    # Create title with key information
    logic_type = "Continuous" if (spec.logic and spec.logic.continuous) or not spec.logic else "Cumulative"
    pass_status = "PASS" if decision.pass_ else "FAIL"
    title = (f'ProofKit Cure Validation - Job {spec.job.job_id}\n'
             f'{pass_status} | {logic_type} Hold | '
             f'Target: {target_temp:.1f}°C | Hold Time: {decision.actual_hold_time_s:.0f}s / {decision.required_hold_time_s}s')
    ax.set_title(title, fontsize=12, fontweight='bold')
    
    # Add grid
    ax.grid(True, alpha=0.3)
    
    # Add legend
    ax.legend(loc='upper left', framealpha=0.9)
    
    # Set y-axis limits to show data clearly
    temp_min = min(temperatures.min(), target_temp - 10)
    temp_max = max(temperatures.max(), threshold_temp + 10)
    ax.set_ylim(temp_min - 5, temp_max + 5)
    
    # Add text box with key metrics
    metrics_text = (
        f'Max Temp: {decision.max_temp_C:.1f}°C\n'
        f'Min Temp: {decision.min_temp_C:.1f}°C\n'
        f'Hold Time: {decision.actual_hold_time_s:.0f}s\n'
        f'Sensors: {", ".join(sensor_names[:3])}{"..." if len(sensor_names) > 3 else ""}'
    )
    
    # Position text box in upper right
    ax.text(0.98, 0.98, metrics_text, transform=ax.transAxes,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8),
            fontsize=9)
    
    # Tight layout to prevent label cutoff
    fig.tight_layout()
    
    return fig


def generate_proof_plot(normalized_df: pd.DataFrame, spec: SpecV1, 
                       decision: DecisionResult, output_path: str,
                       industry: Optional[Industry] = None) -> str:
    """
    Generate proof plot for ProofKit cure validation.
    
    Creates a comprehensive temperature vs time plot showing:
    - Combined PMT temperature data
    - Target temperature line
    - Conservative threshold line  
    - Shaded hold intervals where criteria are met
    - Key metrics and pass/fail status
    - Industry-specific color palette
    
    Args:
        normalized_df: Normalized temperature data from core.normalize
        spec: Cure process specification
        decision: Decision result from core.decide
        output_path: Output file path for the plot
        industry: Industry type for color palette selection
        
    Returns:
        Absolute path to the generated plot file
        
    Raises:
        PlotError: If plot generation fails
    """
    try:
        # Configure matplotlib for deterministic rendering
        configure_matplotlib_for_deterministic_rendering()
        
        # Extract combined PMT data
        timestamps, temperatures, sensor_names = extract_combined_pmt_data(normalized_df, spec)
        
        # Validate data
        if len(timestamps) != len(temperatures):
            raise PlotError("Timestamp and temperature data length mismatch")
        
        if len(timestamps) < 2:
            raise PlotError("Insufficient data points for plotting")
        
        # Create the plot
        fig = create_temperature_plot(timestamps, temperatures, spec, decision, sensor_names, industry)
        
        # Save the plot
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        fig.savefig(
            output_path,
            dpi=100,
            bbox_inches='tight',
            facecolor='white',
            edgecolor='none',
            format='png'
        )
        
        # Close figure to free memory
        plt.close(fig)
        
        logger.info(f"Proof plot generated successfully: {output_path}")
        return str(output_path)
        
    except Exception as e:
        logger.error(f"Plot generation failed: {e}")
        raise PlotError(f"Failed to generate proof plot: {str(e)}")


def validate_plot_inputs(normalized_df: pd.DataFrame, spec: SpecV1, 
                        decision: DecisionResult) -> List[str]:
    """
    Validate inputs for plot generation.
    
    Args:
        normalized_df: Normalized temperature data
        spec: Cure process specification
        decision: Decision result
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Validate DataFrame
    if normalized_df.empty:
        errors.append("Normalized DataFrame is empty")
        return errors
    
    if len(normalized_df) < 2:
        errors.append("Insufficient data points (need at least 2)")
    
    # Check for timestamp column
    timestamp_cols = [col for col in normalized_df.columns 
                     if 'time' in col.lower() or pd.api.types.is_datetime64_any_dtype(normalized_df[col])]
    if not timestamp_cols:
        errors.append("No timestamp column found")
    
    # Check for temperature columns
    temp_columns = detect_temperature_columns(normalized_df)
    if not temp_columns:
        errors.append("No temperature columns found")
    
    # Validate spec
    if spec.spec.target_temp_C <= 0:
        errors.append("Invalid target temperature")
    
    if spec.spec.hold_time_s < 0:
        errors.append("Invalid hold time")
    
    # Validate decision result
    if decision.job_id != spec.job.job_id:
        errors.append("Job ID mismatch between spec and decision")
    
    if decision.target_temp_C != spec.spec.target_temp_C:
        errors.append("Target temperature mismatch between spec and decision")
    
    return errors


# Usage example in comments:
"""
Example usage for ProofKit plot generation:

from core.plot import generate_proof_plot
from core.models import SpecV1, DecisionResult
from core.normalize import normalize_temperature_data, load_csv_with_metadata
from core.decide import make_decision
import pandas as pd
import json

# Load and process data
df, metadata = load_csv_with_metadata("examples/cure_data.csv")
normalized_df = normalize_temperature_data(df, target_step_s=30.0)

# Load specification
with open("examples/spec_example.json") as f:
    spec_data = json.load(f)
spec = SpecV1(**spec_data)

# Make decision
decision = make_decision(normalized_df, spec)

# Generate plot
plot_path = generate_proof_plot(
    normalized_df, spec, decision, "outputs/plot.png"
)

print(f"Plot generated: {plot_path}")
print(f"Decision: {'PASS' if decision.pass_ else 'FAIL'}")
"""