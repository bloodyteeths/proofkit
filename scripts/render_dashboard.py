#!/usr/bin/env python3
"""Render live audit dashboard with matrix support."""

import json
import sys
from pathlib import Path
from datetime import datetime
from jinja2 import Template

def prepare_matrix_data(matrix_file: Path) -> dict:
    """Transform matrix.json into dashboard-ready format."""
    with open(matrix_file) as f:
        matrix = json.load(f)
    
    # Transform to {industry: {pass: result, fail: result}}
    dashboard_matrix = {}
    
    for industry, variants in matrix.items():
        dashboard_matrix[industry] = {"pass": None, "fail": None}
        
        for variant, result in variants.items():
            if "pass" in variant.lower():
                dashboard_matrix[industry]["pass"] = result
            elif "fail" in variant.lower():
                dashboard_matrix[industry]["fail"] = result
    
    return dashboard_matrix

def calculate_summary(matrix_data: dict) -> dict:
    """Calculate summary statistics from matrix data."""
    total_tested = len(matrix_data)
    total_pass = 0
    total_fail = 0
    total_errors = 0
    correct_outcomes = 0
    total_variants = 0
    
    for industry, variants in matrix_data.items():
        if variants["pass"]:
            total_variants += 1
            if "error" in variants["pass"]:
                total_errors += 1
            elif variants["pass"].get("api_status") == "PASS":
                total_pass += 1
                correct_outcomes += 1
            else:
                total_fail += 1
        
        if variants["fail"]:
            total_variants += 1
            if "error" in variants["fail"]:
                total_errors += 1
            elif variants["fail"].get("api_status") == "FAIL":
                total_fail += 1
                correct_outcomes += 1
            else:
                total_pass += 1
    
    match_rate = round(correct_outcomes / total_variants * 100, 1) if total_variants > 0 else 0
    
    return {
        "total_tested": total_tested,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "total_errors": total_errors,
        "match_rate": match_rate
    }

def render_dashboard(run_dir: Path, output_path: Path = None):
    """Render the live audit dashboard HTML."""
    matrix_file = run_dir / "matrix.json"
    ui_smoke_file = run_dir / "ui_smoke.json"
    
    if not matrix_file.exists():
        print(f"No matrix.json found in {run_dir}")
        return None
    
    # Load template
    template_path = Path(__file__).parent.parent / "web" / "templates" / "live_audit.html"
    with open(template_path) as f:
        template = Template(f.read())
    
    # Prepare data
    matrix_data = prepare_matrix_data(matrix_file)
    summary = calculate_summary(matrix_data)
    
    # Load UI smoke results if available
    ui_smoke_results = None
    if ui_smoke_file.exists():
        with open(ui_smoke_file) as f:
            ui_smoke_results = json.load(f)
    
    # Get run metadata
    run_timestamp = run_dir.name  # e.g., "20241209_143022"
    try:
        formatted_timestamp = datetime.strptime(run_timestamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        # For test directories or non-standard names
        formatted_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Render template
    html = template.render(
        matrix_results=matrix_data,
        ui_smoke_results=ui_smoke_results,
        run_timestamp=formatted_timestamp,
        base_url="https://proofkit.net",
        job_tag="LIVE-QA",
        **summary
    )
    
    # Save output
    if output_path is None:
        output_path = run_dir / "dashboard.html"
    
    output_path.write_text(html)
    print(f"Dashboard rendered to: {output_path}")
    
    return output_path

def main():
    if len(sys.argv) > 1:
        run_dir = Path(sys.argv[1])
    else:
        # Find latest run
        live_runs = Path("live_runs")
        if live_runs.exists():
            runs = sorted([d for d in live_runs.iterdir() if d.is_dir()])
            run_dir = runs[-1] if runs else None
        else:
            print("No live runs found")
            sys.exit(1)
    
    if not run_dir or not run_dir.exists():
        print(f"Run directory not found: {run_dir}")
        sys.exit(1)
    
    render_dashboard(run_dir)

if __name__ == "__main__":
    main()