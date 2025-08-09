#!/usr/bin/env python3
"""Live PDF audit runner for production QA testing with PASS/FAIL matrix."""

import argparse
import json
import time
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List
import requests
import pandas as pd
import numpy as np

INDUSTRIES = ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"]
RATE_LIMIT_DELAY = 1.0  # 1 second between requests
MAX_JOBS = 60  # Increased for matrix mode

def generate_synthetic_example(industry: str, outcome: str) -> Tuple[pd.DataFrame, Dict]:
    """Generate synthetic CSV and spec for testing."""
    np.random.seed(42 if outcome == "pass" else 84)
    
    if industry == "powder":
        spec = {
            "industry": "powder",
            "parameters": {
                "target_temp": 180,
                "hold_duration_minutes": 10,
                "sensor_uncertainty": 2,
                "hysteresis": 2
            }
        }
        times = list(range(0, 1800, 30))
        if outcome == "pass":
            temps = [20] * 10 + [180 + np.random.uniform(-1, 2) for _ in range(25)] + [100] * 25
        else:
            temps = [20] * 10 + [180 + np.random.uniform(-1, 2) for _ in range(15)] + [100] * 35
        df = pd.DataFrame({"timestamp": times, "temperature": temps})
        
    elif industry == "autoclave":
        spec = {
            "industry": "autoclave",
            "parameters": {
                "sterilization_temp": 121,
                "sterilization_time_minutes": 15,
                "min_pressure_bar": 2.0
            }
        }
        times = list(range(0, 2400, 30))
        if outcome == "pass":
            temps = [20] * 20 + [121 + np.random.uniform(-0.5, 1) for _ in range(35)] + [80] * 25
            pressures = [1] * 20 + [2.1 + np.random.uniform(-0.1, 0.2) for _ in range(35)] + [1] * 25
        else:
            temps = [20] * 20 + [121 + np.random.uniform(-0.5, 1) for _ in range(25)] + [80] * 35
            pressures = [1] * 20 + [2.1 + np.random.uniform(-0.1, 0.2) for _ in range(25)] + [1] * 35
        df = pd.DataFrame({"timestamp": times, "temperature": temps, "pressure": pressures})
        
    elif industry == "coldchain":
        spec = {
            "industry": "coldchain",
            "parameters": {
                "min_temp": 2,
                "max_temp": 8,
                "compliance_percentage": 95
            }
        }
        times = list(range(0, 86400, 300))
        if outcome == "pass":
            temps = [np.random.uniform(3, 7) if np.random.random() < 0.97 else 9 for _ in range(288)]
        else:
            temps = [np.random.uniform(3, 7) if np.random.random() < 0.90 else 10 for _ in range(288)]
        df = pd.DataFrame({"timestamp": times, "temperature": temps})
        
    elif industry == "haccp":
        spec = {
            "industry": "haccp",
            "parameters": {
                "temp_1": 135,
                "temp_2": 70,
                "temp_3": 41,
                "time_1_to_2_hours": 2,
                "time_2_to_3_hours": 4
            }
        }
        times = list(range(0, 25200, 30))
        if outcome == "pass":
            temps = [140] * 20 + list(np.linspace(140, 65, 120)) + list(np.linspace(65, 35, 200)) + [35] * 500
        else:
            temps = [140] * 20 + list(np.linspace(140, 65, 180)) + list(np.linspace(65, 35, 300)) + [35] * 340
        df = pd.DataFrame({"timestamp": times, "temperature": temps})
        
    elif industry == "concrete":
        spec = {
            "industry": "concrete",
            "parameters": {
                "min_temp": 10,
                "max_temp": 30,
                "min_humidity": 80,
                "time_window_hours": 24
            }
        }
        times = list(range(0, 172800, 300))
        if outcome == "pass":
            temps = [np.random.uniform(12, 28) for _ in range(576)]
            humidities = [np.random.uniform(82, 95) for _ in range(576)]
        else:
            temps = [np.random.uniform(8, 32) for _ in range(576)]
            humidities = [np.random.uniform(75, 95) for _ in range(576)]
        df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
        
    elif industry == "sterile":
        spec = {
            "industry": "sterile",
            "parameters": {
                "min_temp": 55,
                "exposure_hours": 12,
                "min_humidity": 50
            }
        }
        times = list(range(0, 86400, 300))
        if outcome == "pass":
            temps = [np.random.uniform(56, 60) for _ in range(288)]
            humidities = [np.random.uniform(52, 65) for _ in range(288)]
        else:
            temps = [np.random.uniform(53, 58) if i < 140 else np.random.uniform(56, 60) for i in range(288)]
            humidities = [np.random.uniform(48, 65) for _ in range(288)]
        df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
    
    else:
        raise ValueError(f"Unknown industry: {industry}")
    
    return df, spec

def get_example_files(industry: str, variant: str) -> Tuple[str, str]:
    """Get CSV and spec paths for an industry variant."""
    examples_dir = Path("examples") / industry
    
    # Try specific variant files first
    csv_paths = [
        examples_dir / f"{variant}.csv",
        examples_dir / f"{industry}_{variant}.csv",
        examples_dir / f"{variant}_example.csv",
    ]
    
    spec_paths = [
        examples_dir / f"{variant}.json",
        examples_dir / f"{variant}_spec.json",
        examples_dir / f"{industry}_{variant}_spec.json",
    ]
    
    for csv_path in csv_paths:
        if csv_path.exists():
            for spec_path in spec_paths:
                if spec_path.exists():
                    return str(csv_path), str(spec_path)
    
    # Generate synthetic if not found
    print(f"  Generating synthetic {variant} example for {industry}")
    df, spec = generate_synthetic_example(industry, variant)
    
    # Save generated files
    examples_dir.mkdir(parents=True, exist_ok=True)
    csv_path = examples_dir / f"{variant}_auto.csv"
    spec_path = examples_dir / f"{variant}_auto_spec.json"
    
    df.to_csv(csv_path, index=False)
    with open(spec_path, 'w') as f:
        json.dump(spec, f, indent=2)
    
    # Record in README
    readme_path = Path("examples") / "README.md"
    with open(readme_path, 'a') as f:
        f.write(f"\n- {industry}/{variant}_auto: Synthetic example generated {datetime.now()}")
    
    return str(csv_path), str(spec_path)

def compile_job(base_url: str, csv_path: str, spec_path: str, 
                email: str, tag: str, variant: str, token: Optional[str] = None) -> Dict:
    """Submit compilation job to production."""
    url = f"{base_url}/api/compile"
    
    with open(csv_path, 'rb') as csv_file, open(spec_path, 'r') as spec_file:
        files = {'csv_file': csv_file}
        data = {
            'spec_json': spec_file.read(),
            'job_tag': tag,
            'variant': variant
        }
        
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
        
        if response.status_code == 429:
            print(f"Rate limited, waiting 5s...")
            time.sleep(5)
            return compile_job(base_url, csv_path, spec_path, email, tag, variant, token)
        
        response.raise_for_status()
        return response.json()

def fetch_artifacts(base_url: str, job_id: str, output_dir: Path) -> None:
    """Download PDF and evidence bundle."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download proof PDF
    pdf_url = f"{base_url}/output/{job_id}/proof.pdf"
    pdf_resp = requests.get(pdf_url, timeout=30)
    if pdf_resp.status_code == 200:
        (output_dir / "proof.pdf").write_bytes(pdf_resp.content)
    
    # Download evidence bundle
    zip_url = f"{base_url}/output/{job_id}/evidence.zip"
    zip_resp = requests.get(zip_url, timeout=30)
    if zip_resp.status_code == 200:
        (output_dir / "evidence.zip").write_bytes(zip_resp.content)
    
    # Fetch verify page HTML
    verify_url = f"{base_url}/verify/{job_id}"
    verify_resp = requests.get(verify_url, timeout=30)
    if verify_resp.status_code == 200:
        (output_dir / "verify.html").write_text(verify_resp.text)

def run_matrix_audit(base_url: str, email: str, tag: str, matrix: List[str], token: Optional[str] = None) -> Dict:
    """Run full audit across all industries with PASS/FAIL matrix."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(f"live_runs/{timestamp}")
    run_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    job_count = 0
    
    for industry in INDUSTRIES:
        if job_count >= MAX_JOBS:
            print(f"Reached max jobs limit ({MAX_JOBS})")
            break
        
        print(f"\n[{industry}] Starting matrix audit...")
        results[industry] = {}
        
        for variant in matrix:
            print(f"  Running {variant} variant...")
            variant_dir = run_dir / industry / variant
            
            try:
                # Get example files
                csv_path, spec_path = get_example_files(industry, variant)
                print(f"    Using: {csv_path}, {spec_path}")
                
                # Submit compilation
                time.sleep(RATE_LIMIT_DELAY)
                result = compile_job(base_url, csv_path, spec_path, email, tag, variant, token)
                job_count += 1
                
                job_id = result.get('job_id')
                if not job_id:
                    results[industry][variant] = {"error": "No job_id in response"}
                    continue
                
                print(f"    Job ID: {job_id}")
                print(f"    Decision: {result.get('decision', {}).get('outcome')}")
                
                # Save API response
                variant_dir.mkdir(parents=True, exist_ok=True)
                (variant_dir / "api.json").write_text(json.dumps(result, indent=2))
                
                # Fetch artifacts
                time.sleep(RATE_LIMIT_DELAY)
                fetch_artifacts(base_url, job_id, variant_dir)
                
                results[industry][variant] = {
                    "job_id": job_id,
                    "api_status": result.get('decision', {}).get('outcome'),
                    "artifacts": {
                        "pdf": (variant_dir / "proof.pdf").exists(),
                        "bundle": (variant_dir / "evidence.zip").exists(),
                        "verify": (variant_dir / "verify.html").exists()
                    }
                }
                
            except Exception as e:
                print(f"    ERROR: {e}")
                results[industry][variant] = {"error": str(e)}
    
    # Save matrix results
    matrix_path = run_dir / "matrix.json"
    matrix_path.write_text(json.dumps(results, indent=2))
    
    # Save summary
    summary = {
        "timestamp": timestamp,
        "base_url": base_url,
        "tag": tag,
        "matrix": matrix,
        "industries": list(results.keys()),
        "total_jobs": job_count,
        "results": results
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    
    print(f"\nAudit complete. Results saved to: {run_dir}")
    return results

def main():
    parser = argparse.ArgumentParser(description="Live PDF audit runner with PASS/FAIL matrix")
    parser.add_argument("--base", default=os.getenv("BASE_URL", "https://proofkit.net"))
    parser.add_argument("--email", default=os.getenv("LIVE_QA_EMAIL"))
    parser.add_argument("--token", default=os.getenv("LIVE_QA_TOKEN"))
    parser.add_argument("--tag", default=os.getenv("LIVE_QA_TAG", "LIVE-QA"))
    parser.add_argument("--matrix", action="store_true", help="Run PASS/FAIL matrix tests")
    parser.add_argument("--variants", default="pass,fail", help="Comma-separated variants to test")
    
    args = parser.parse_args()
    
    if not args.email:
        print("ERROR: Email required (--email or LIVE_QA_EMAIL env)")
        sys.exit(1)
    
    if args.matrix:
        # Run full PASS/FAIL matrix
        variants = args.variants.split(",")
        print(f"Running live PASS/FAIL matrix audit against: {args.base}")
        print(f"Email: {args.email}")
        print(f"Tag: {args.tag}")
        print(f"Variants: {variants}")
        results = run_matrix_audit(args.base, args.email, args.tag, variants, args.token)
    else:
        # Run single variant (legacy mode)
        print(f"Running single variant audit against: {args.base}")
        print(f"Email: {args.email}")
        print(f"Tag: {args.tag}")
        # Run just the pass variant for each industry
        results = run_matrix_audit(args.base, args.email, args.tag, ["pass"], args.token)
    
    # Print summary
    print("\n=== MATRIX SUMMARY ===")
    for industry, variants in results.items():
        print(f"\n{industry}:")
        for variant, result in variants.items():
            if "error" in result:
                print(f"  {variant}: ❌ {result['error']}")
            else:
                status = result.get('api_status', 'UNKNOWN')
                artifacts = sum(1 for v in result.get('artifacts', {}).values() if v)
                print(f"  {variant}: {status} ({artifacts}/3 artifacts)")

if __name__ == "__main__":
    main()