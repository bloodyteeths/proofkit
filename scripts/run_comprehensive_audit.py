#!/usr/bin/env python3
"""Run comprehensive LIVE-QA v2 audit with real-world datasets."""

import json
import time
import sys
import shutil
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd

BASE_URL = "https://proofkit.net"
EMAIL = "liveqa@proofkit.net"
TAG = "LIVE-QA-COMPREHENSIVE"
RUN_DIR = Path("live_runs/20250809_010745")
RATE_LIMIT_DELAY = 1.5  # seconds between requests

# Map industries to their test datasets
TEST_DATASETS = {
    "powder": {
        "pass": {
            "csv": "examples/powder_coat_cure_successful_180c_10min_pass.csv",
            "spec": "examples/powder_coat_cure_spec_standard_180c_10min.json"
        },
        "fail": {
            "csv": "examples/powder_coat_cure_insufficient_hold_time_fail.csv",
            "spec": "examples/powder_coat_cure_spec_standard_180c_10min.json"
        }
    },
    "autoclave": {
        "pass": {
            "csv": "realworld/autoclave/raw/medical_device_sterilization.csv",
            "spec": "realworld/autoclave/spec.json"
        },
        "fail": {
            "csv": "examples/autoclave_missing_pressure_indeterminate.csv",
            "spec": None  # Will create a spec
        }
    },
    "coldchain": {
        "pass": {
            "csv": "realworld/coldchain/raw/cold_storage_monitoring.csv",
            "spec": "realworld/coldchain/spec.json"
        },
        "fail": {
            "csv": None,  # Will generate synthetic
            "spec": None
        }
    },
    "haccp": {
        "pass": {
            "csv": None,  # Will generate synthetic
            "spec": None
        },
        "fail": {
            "csv": None,  # Will generate synthetic
            "spec": None
        }
    },
    "concrete": {
        "pass": {
            "csv": "realworld/concrete/raw/astm_c31_sample_curing.csv",
            "spec": "realworld/concrete/spec.json"
        },
        "fail": {
            "csv": None,  # Will generate synthetic
            "spec": None
        }
    },
    "sterile": {
        "pass": {
            "csv": "realworld/sterile/raw/iso_17665_steam_sterilization.csv",
            "spec": "realworld/sterile/spec.json"
        },
        "fail": {
            "csv": None,  # Will generate synthetic
            "spec": None
        }
    }
}

def generate_synthetic_data(industry: str, outcome: str):
    """Generate synthetic test data for missing datasets."""
    import numpy as np
    
    if industry == "coldchain" and outcome == "fail":
        # Generate failing cold chain data
        times = list(range(0, 86400, 300))  # 24 hours, 5-min intervals
        temps = []
        for _ in range(len(times)):
            if np.random.random() < 0.85:  # 85% compliance (fail)
                temps.append(np.random.uniform(3, 7))
            else:
                temps.append(np.random.uniform(9, 12))  # Out of range
        
        df = pd.DataFrame({"timestamp": times, "temperature": temps})
        spec = {
            "industry": "coldchain",
            "parameters": {
                "min_temp": 2,
                "max_temp": 8,
                "compliance_percentage": 95
            }
        }
        return df, spec
    
    elif industry == "haccp":
        times = list(range(0, 25200, 30))  # 7 hours, 30-sec intervals
        
        if outcome == "pass":
            # Proper cooling curve
            temps = ([140] * 20 +  # Start hot
                    list(np.linspace(140, 65, 120)) +  # Cool to 70F in 2 hours
                    list(np.linspace(65, 35, 200)) +  # Cool to 41F in 4 more hours
                    [35] * 500)  # Stay cold
        else:
            # Too slow cooling (fail)
            temps = ([140] * 20 +  # Start hot
                    list(np.linspace(140, 65, 200)) +  # Too slow to 70F
                    list(np.linspace(65, 35, 320)) +  # Too slow to 41F
                    [35] * 300)  # Stay cold
        
        df = pd.DataFrame({"timestamp": times[:len(temps)], "temperature": temps})
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
        return df, spec
    
    elif industry == "concrete" and outcome == "fail":
        # Generate failing concrete data
        times = list(range(0, 172800, 1800))  # 48 hours, 30-min intervals
        temps = []
        humidities = []
        
        for i in range(len(times)):
            if i < 48:  # First 24 hours
                if np.random.random() < 0.9:  # 90% compliance (fail)
                    temps.append(np.random.uniform(12, 28))
                    humidities.append(np.random.uniform(82, 95))
                else:
                    temps.append(np.random.uniform(5, 10))  # Too cold
                    humidities.append(np.random.uniform(70, 78))  # Too dry
            else:
                temps.append(np.random.uniform(15, 25))
                humidities.append(np.random.uniform(85, 95))
        
        df = pd.DataFrame({
            "timestamp": times,
            "temperature": temps,
            "humidity": humidities
        })
        spec = {
            "industry": "concrete",
            "parameters": {
                "min_temp": 10,
                "max_temp": 30,
                "min_humidity": 80,
                "time_window_hours": 24
            }
        }
        return df, spec
    
    elif industry == "sterile" and outcome == "fail":
        # Generate failing sterile data
        times = list(range(0, 86400, 1800))  # 24 hours, 30-min intervals
        temps = []
        humidities = []
        
        for i in range(len(times)):
            if i < 20:  # First 10 hours - not enough exposure
                temps.append(np.random.uniform(52, 58))
                humidities.append(np.random.uniform(45, 55))
            else:
                temps.append(np.random.uniform(58, 62))
                humidities.append(np.random.uniform(55, 65))
        
        df = pd.DataFrame({
            "timestamp": times,
            "temperature": temps,
            "humidity": humidities
        })
        spec = {
            "industry": "sterile",
            "parameters": {
                "min_temp": 55,
                "exposure_hours": 12,
                "min_humidity": 50
            }
        }
        return df, spec
    
    elif industry == "autoclave" and outcome == "fail":
        # Create spec for the existing CSV
        spec = {
            "industry": "autoclave",
            "parameters": {
                "sterilization_temp": 121,
                "sterilization_time_minutes": 15,
                "min_pressure_bar": 2.0
            }
        }
        return None, spec
    
    return None, None

def submit_job(industry: str, variant: str, csv_path: Path, spec: dict):
    """Submit a job to the ProofKit API."""
    url = f"{BASE_URL}/compile"
    
    # Prepare the files
    files = {
        'csv_file': ('data.csv', open(csv_path, 'rb'), 'text/csv')
    }
    
    data = {
        'spec': json.dumps(spec),
        'email': EMAIL,
        'tag': f"{TAG}-{industry}-{variant}"
    }
    
    try:
        response = requests.post(url, files=files, data=data, timeout=30)
        files['csv_file'][1].close()
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "job_id": result.get("job_id"),
                "status": result.get("status"),
                "api_status": result.get("decision", {}).get("outcome")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def download_artifacts(job_id: str, output_dir: Path):
    """Download PDF and bundle for a job."""
    artifacts = {}
    
    # Download PDF
    pdf_url = f"{BASE_URL}/output/{job_id}/proof.pdf"
    try:
        resp = requests.get(pdf_url, timeout=10)
        if resp.status_code == 200:
            pdf_path = output_dir / "proof.pdf"
            pdf_path.write_bytes(resp.content)
            artifacts["pdf"] = str(pdf_path)
    except:
        pass
    
    # Download bundle
    bundle_url = f"{BASE_URL}/output/{job_id}/evidence.zip"
    try:
        resp = requests.get(bundle_url, timeout=10)
        if resp.status_code == 200:
            bundle_path = output_dir / "evidence.zip"
            bundle_path.write_bytes(resp.content)
            artifacts["bundle"] = str(bundle_path)
    except:
        pass
    
    return artifacts

def main():
    print(f"Starting comprehensive audit at {datetime.now()}")
    print(f"Run directory: {RUN_DIR}")
    
    matrix_results = {}
    
    for industry, variants in TEST_DATASETS.items():
        print(f"\n=== Testing {industry.upper()} ===")
        matrix_results[industry] = {}
        
        for variant in ["pass", "fail"]:
            print(f"  Variant: {variant}")
            
            # Get or generate test data
            dataset = variants[variant]
            csv_path = Path(dataset["csv"]) if dataset["csv"] else None
            spec = None
            
            if dataset["spec"]:
                with open(dataset["spec"]) as f:
                    spec = json.load(f)
            
            # Generate synthetic data if needed
            if not csv_path or not csv_path.exists():
                print(f"    Generating synthetic data...")
                df, spec = generate_synthetic_data(industry, variant)
                if df is not None:
                    csv_path = RUN_DIR / industry / variant / "input.csv"
                    csv_path.parent.mkdir(parents=True, exist_ok=True)
                    df.to_csv(csv_path, index=False)
                elif industry == "autoclave" and variant == "fail":
                    # Use the existing CSV
                    csv_path = Path("examples/autoclave_missing_pressure_indeterminate.csv")
            
            if not csv_path or not spec:
                print(f"    ERROR: No data available")
                matrix_results[industry][variant] = {"error": "No data available"}
                continue
            
            # Save spec for reference
            spec_path = RUN_DIR / industry / variant / "spec.json"
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(json.dumps(spec, indent=2))
            
            # Submit job
            print(f"    Submitting job...")
            result = submit_job(industry, variant, csv_path, spec)
            
            if result["success"]:
                job_id = result["job_id"]
                print(f"    Job ID: {job_id}")
                print(f"    Status: {result['api_status']}")
                
                # Download artifacts
                output_dir = RUN_DIR / industry / variant
                artifacts = download_artifacts(job_id, output_dir)
                
                result["artifacts"] = artifacts
                print(f"    Downloaded: {len(artifacts)} artifacts")
            else:
                print(f"    ERROR: {result['error']}")
            
            matrix_results[industry][variant] = result
            
            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)
    
    # Save matrix results
    matrix_path = RUN_DIR / "matrix.json"
    matrix_path.write_text(json.dumps(matrix_results, indent=2))
    print(f"\n\nMatrix results saved to: {matrix_path}")
    
    # Print summary
    print("\n=== SUMMARY ===")
    for industry, variants in matrix_results.items():
        print(f"\n{industry}:")
        for variant, result in variants.items():
            if "error" in result:
                print(f"  {variant}: ERROR - {result['error']}")
            else:
                status = result.get('api_status', 'UNKNOWN')
                artifacts = len(result.get('artifacts', {}))
                print(f"  {variant}: {status} ({artifacts} artifacts)")

if __name__ == "__main__":
    main()