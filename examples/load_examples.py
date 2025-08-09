#!/usr/bin/env python3
"""
Load examples for all supported industries.

Provides programmatic access to example CSV and JSON files for testing,
demonstrations, and API integration across all 5 supported industries.
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def get_powder_pass_example() -> Tuple[Path, Path]:
    """Get powder pass example based on feature flag."""
    examples_v2 = os.getenv("EXAMPLES_V2_ENABLED", "true").lower() == "true"
    
    if examples_v2:
        # Use fixed example with proper ramp rate
        csv_path = Path("examples/powder_pass_fixed.csv")
        spec_path = Path("examples/powder_pass_spec_fixed.json")
    else:
        # Use legacy example
        csv_path = Path("examples/_legacy/powder_coat_cure_successful_180c_10min_pass.csv")
        spec_path = Path("examples/powder_coat_cure_spec_standard_180c_10min.json")
    
    return csv_path, spec_path


def get_industry_examples(industry: str) -> Dict[str, List[Tuple[Path, Path]]]:
    """
    Get all examples for a specific industry.
    
    Args:
        industry: One of 'powder', 'autoclave', 'concrete', 'coldchain', 'haccp', 'sterile'
        
    Returns:
        Dict with 'pass', 'fail', and optionally 'indeterminate' example lists
        
    Raises:
        ValueError: If industry is not supported
    """
    examples_base = Path("examples")
    
    industry_map = {
        "powder": {
            "pass": [
                (examples_base / "powder_coat_cure_successful_180c_10min_pass.csv",
                 examples_base / "powder_coat_cure_spec_standard_180c_10min.json"),
                (examples_base / "powder_coat_cure_cumulative_hold_pass_170c_20min.csv", 
                 examples_base / "powder_coat_cure_spec_cumulative_hold_170c_20min.json"),
                (examples_base / "powder_coat_cure_fahrenheit_input_356f_10min_pass.csv",
                 examples_base / "powder_coat_cure_spec_fahrenheit_input_356f_10min.json"),
                (examples_base / "powder_pass_fixed.csv",
                 examples_base / "powder_pass_spec_fixed.json")
            ],
            "fail": [
                (examples_base / "powder_coat_cure_insufficient_hold_time_fail.csv",
                 examples_base / "powder_coat_cure_spec_standard_180c_10min.json"),
                (examples_base / "powder_coat_cure_data_gaps_sensor_disconnect_fail.csv",
                 examples_base / "powder_coat_cure_spec_standard_180c_10min.json"),
                (examples_base / "powder_coat_cure_slow_ramp_rate_fail.csv",
                 examples_base / "powder_coat_cure_spec_standard_180c_10min.json"),
                (examples_base / "powder_coat_cure_sensor_failure_mid_run_fail.csv",
                 examples_base / "powder_coat_cure_spec_standard_180c_10min.json")
            ]
        },
        "autoclave": {
            "pass": [
                (examples_base / "autoclave_sterilization_pass.csv",
                 examples_base / "autoclave-medical-device-validation.json")
            ],
            "fail": [
                (examples_base / "autoclave_sterilization_fail.csv",
                 examples_base / "autoclave-medical-device-validation.json")
            ],
            "indeterminate": [
                (examples_base / "autoclave_missing_pressure_indeterminate.csv",
                 examples_base / "autoclave-medical-device-validation.json")
            ]
        },
        "concrete": {
            "pass": [
                (examples_base / "concrete_curing_pass.csv",
                 examples_base / "concrete-curing-astm-c31.json")
            ],
            "fail": [
                (examples_base / "concrete_curing_fail.csv",
                 examples_base / "concrete-curing-astm-c31.json")
            ]
        },
        "coldchain": {
            "pass": [
                (examples_base / "coldchain_storage_pass.csv",
                 examples_base / "coldchain-storage-validation.json")
            ],
            "fail": [
                (examples_base / "coldchain_storage_fail.csv",
                 examples_base / "coldchain-storage-validation.json")
            ]
        },
        "haccp": {
            "pass": [
                (examples_base / "haccp_cooling_pass.csv",
                 examples_base / "haccp-cooling-validation.json")
            ],
            "fail": [
                (examples_base / "haccp_cooling_fail.csv",
                 examples_base / "haccp-cooling-validation.json")
            ]
        },
        "sterile": {
            "pass": [
                (examples_base / "sterile_processing_pass.csv",
                 examples_base / "sterile-processing-validation.json")
            ],
            "fail": [
                (examples_base / "sterile_processing_fail.csv",
                 examples_base / "sterile-processing-validation.json")
            ]
        }
    }
    
    if industry not in industry_map:
        supported = ", ".join(industry_map.keys())
        raise ValueError(f"Unsupported industry '{industry}'. Supported: {supported}")
    
    return industry_map[industry]


def get_all_examples() -> Dict[str, Dict[str, List[Tuple[Path, Path]]]]:
    """
    Get all examples across all industries.
    
    Returns:
        Dict mapping industry -> category -> list of (csv_path, spec_path) tuples
        
    Example:
        {
            "powder": {
                "pass": [(Path(...), Path(...))],
                "fail": [(Path(...), Path(...))]
            },
            "autoclave": {
                "pass": [(Path(...), Path(...))],
                "fail": [(Path(...), Path(...))],
                "indeterminate": [(Path(...), Path(...))]
            },
            ...
        }
    """
    supported_industries = ["powder", "autoclave", "concrete", "coldchain", "haccp", "sterile"]
    
    all_examples = {}
    for industry in supported_industries:
        all_examples[industry] = get_industry_examples(industry)
    
    return all_examples


def get_example_by_filename(csv_filename: str) -> Optional[Tuple[Path, Path]]:
    """
    Find example spec file for a given CSV filename.
    
    Args:
        csv_filename: Name of CSV file (with or without .csv extension)
        
    Returns:
        (csv_path, spec_path) tuple if found, None otherwise
    """
    if not csv_filename.endswith('.csv'):
        csv_filename += '.csv'
    
    all_examples = get_all_examples()
    
    for industry_examples in all_examples.values():
        for category_examples in industry_examples.values():
            for csv_path, spec_path in category_examples:
                if csv_path.name == csv_filename:
                    return (csv_path, spec_path)
    
    return None


def list_available_examples() -> Dict[str, int]:
    """
    Get count of examples by category across all industries.
    
    Returns:
        Dict with counts: {"pass": n, "fail": n, "indeterminate": n}
    """
    all_examples = get_all_examples()
    
    counts = {"pass": 0, "fail": 0, "indeterminate": 0}
    
    for industry_examples in all_examples.values():
        for category, examples in industry_examples.items():
            if category in counts:
                counts[category] += len(examples)
    
    return counts


def get_representative_examples() -> Dict[str, Tuple[Path, Path]]:
    """
    Get one representative example per industry (PASS cases).
    
    Returns:
        Dict mapping industry -> (csv_path, spec_path)
    """
    representatives = {}
    all_examples = get_all_examples()
    
    for industry, categories in all_examples.items():
        if "pass" in categories and categories["pass"]:
            # Use first PASS example as representative
            representatives[industry] = categories["pass"][0]
    
    return representatives


if __name__ == "__main__":
    """Demo script showing example loading capabilities."""
    print("ProofKit Examples Loader")
    print("=" * 40)
    
    # Show summary
    counts = list_available_examples()
    print(f"Available examples: {counts}")
    
    # Show all industries
    all_examples = get_all_examples()
    for industry, categories in all_examples.items():
        total = sum(len(examples) for examples in categories.values())
        print(f"{industry}: {total} examples")
        for category, examples in categories.items():
            print(f"  {category}: {len(examples)}")
    
    # Show representatives
    print("\nRepresentative examples:")
    reps = get_representative_examples()
    for industry, (csv_path, spec_path) in reps.items():
        print(f"  {industry}: {csv_path.name} + {spec_path.name}")
    
    # Test filename lookup
    test_csv = "powder_coat_cure_successful_180c_10min_pass.csv"
    result = get_example_by_filename(test_csv)
    if result:
        csv_path, spec_path = result
        print(f"\nFilename lookup '{test_csv}': {spec_path.name}")
    else:
        print(f"\nFilename lookup '{test_csv}': Not found")