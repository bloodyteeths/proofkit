#!/usr/bin/env python3
"""Final comprehensive LIVE-QA v2 audit with correct API format."""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd
import numpy as np

BASE_URL = "https://proofkit-prod.fly.dev"
EMAIL = "atanrikulu@e-listele.com"
TAG = "LIVE-QA-FINAL"
RUN_DIR = Path("live_runs/20250809_010745")
RATE_LIMIT_DELAY = 1.0  # seconds between requests

# Parse auth token from cookies
auth_token = None
with open("cookies.txt") as f:
    for line in f:
        if "auth_token" in line:
            parts = line.strip().split("\t")
            if len(parts) > 6:
                auth_token = parts[6]
                break

if not auth_token:
    print("No auth token found!")
    sys.exit(1)

# Create session with cookie
session = requests.Session()
session.cookies.set("auth_token", auth_token, domain="proofkit-prod.fly.dev")

def submit_and_download(industry: str, variant: str, csv_path: Path, spec: dict):
    """Submit job and download artifacts."""
    url = f"{BASE_URL}/api/compile/json"
    
    # Save inputs for reference
    output_dir = RUN_DIR / industry / variant
    output_dir.mkdir(parents=True, exist_ok=True)
    
    spec_path = output_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))
    
    # Copy CSV to output dir
    import shutil
    shutil.copy(csv_path, output_dir / "input.csv")
    
    # Submit job
    with open(csv_path, 'rb') as csv_file:
        files = {'csv_file': ('data.csv', csv_file, 'text/csv')}
        data = {'spec_json': json.dumps(spec)}
        
        try:
            response = session.post(url, files=files, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                job_id = result.get("id")
                
                # Save response
                response_path = output_dir / "response.json"
                response_path.write_text(json.dumps(result, indent=2))
                
                # Download PDF
                if result.get("urls", {}).get("pdf"):
                    pdf_url = BASE_URL + result["urls"]["pdf"]
                    pdf_resp = session.get(pdf_url, timeout=10)
                    if pdf_resp.status_code == 200:
                        pdf_path = output_dir / "proof.pdf"
                        pdf_path.write_bytes(pdf_resp.content)
                        print(f"    ✓ PDF downloaded ({len(pdf_resp.content)} bytes)")
                
                # Download bundle
                if result.get("urls", {}).get("zip"):
                    zip_url = BASE_URL + result["urls"]["zip"]
                    zip_resp = session.get(zip_url, timeout=10)
                    if zip_resp.status_code == 200:
                        zip_path = output_dir / "evidence.zip"
                        zip_path.write_bytes(zip_resp.content)
                        print(f"    ✓ Bundle downloaded ({len(zip_resp.content)} bytes)")
                
                return {
                    "success": True,
                    "job_id": job_id,
                    "api_status": result.get("status"),
                    "pass": result.get("pass"),
                    "metrics": result.get("metrics"),
                    "reasons": result.get("reasons"),
                    "artifacts": {
                        "pdf": str(output_dir / "proof.pdf") if (output_dir / "proof.pdf").exists() else None,
                        "bundle": str(output_dir / "evidence.zip") if (output_dir / "evidence.zip").exists() else None
                    }
                }
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

def run_all_tests():
    """Run comprehensive test matrix."""
    
    # Test definitions
    tests = []
    
    # POWDER tests with real data
    tests.append({
        "industry": "powder",
        "variant": "pass",
        "csv": "examples/powder_coat_cure_successful_180c_10min_pass.csv",
        "spec": "examples/powder_coat_cure_spec_standard_180c_10min.json"
    })
    tests.append({
        "industry": "powder",
        "variant": "fail",
        "csv": "examples/powder_coat_cure_insufficient_hold_time_fail.csv",
        "spec": "examples/powder_coat_cure_spec_standard_180c_10min.json"
    })
    
    # Generate synthetic data for other industries
    
    # AUTOCLAVE PASS
    times = list(range(0, 2400, 30))
    temps = [20] * 10 + [121.5] * 40 + [80] * 30
    pressures = [1] * 10 + [2.1] * 40 + [1] * 30
    df = pd.DataFrame({"timestamp": times, "temperature": temps, "pressure": pressures})
    csv_path = RUN_DIR / "autoclave_pass_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "autoclave",
        "variant": "pass",
        "csv": str(csv_path),
        "spec": {
            "industry": "autoclave",
            "parameters": {
                "sterilization_temp": 121,
                "sterilization_time_minutes": 15,
                "min_pressure_bar": 2.0
            }
        }
    })
    
    # AUTOCLAVE FAIL
    temps = [20] * 10 + [121.5] * 20 + [80] * 50  # Only 10 minutes hold
    pressures = [1] * 10 + [2.1] * 20 + [1] * 50
    df = pd.DataFrame({"timestamp": times, "temperature": temps, "pressure": pressures})
    csv_path = RUN_DIR / "autoclave_fail_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "autoclave",
        "variant": "fail",
        "csv": str(csv_path),
        "spec": {
            "industry": "autoclave",
            "parameters": {
                "sterilization_temp": 121,
                "sterilization_time_minutes": 15,
                "min_pressure_bar": 2.0
            }
        }
    })
    
    # COLDCHAIN PASS (96% compliance)
    np.random.seed(42)
    times = list(range(0, 86400, 300))
    temps = [np.random.uniform(3, 7) if np.random.random() < 0.96 else 9 for _ in range(len(times))]
    df = pd.DataFrame({"timestamp": times, "temperature": temps})
    csv_path = RUN_DIR / "coldchain_pass_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "coldchain",
        "variant": "pass",
        "csv": str(csv_path),
        "spec": {
            "industry": "coldchain",
            "parameters": {
                "min_temp": 2,
                "max_temp": 8,
                "compliance_percentage": 95
            }
        }
    })
    
    # COLDCHAIN FAIL (90% compliance)
    np.random.seed(84)
    temps = [np.random.uniform(3, 7) if np.random.random() < 0.90 else np.random.uniform(9, 12) for _ in range(len(times))]
    df = pd.DataFrame({"timestamp": times, "temperature": temps})
    csv_path = RUN_DIR / "coldchain_fail_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "coldchain",
        "variant": "fail",
        "csv": str(csv_path),
        "spec": {
            "industry": "coldchain",
            "parameters": {
                "min_temp": 2,
                "max_temp": 8,
                "compliance_percentage": 95
            }
        }
    })
    
    # HACCP PASS
    times = list(range(0, 25200, 30))
    temps = ([140] * 20 +
             list(np.linspace(140, 68, 120)) +
             list(np.linspace(68, 38, 200)) +
             [38] * 320)
    df = pd.DataFrame({"timestamp": times[:len(temps)], "temperature": temps})
    csv_path = RUN_DIR / "haccp_pass_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "haccp",
        "variant": "pass",
        "csv": str(csv_path),
        "spec": {
            "industry": "haccp",
            "parameters": {
                "temp_1": 135,
                "temp_2": 70,
                "temp_3": 41,
                "time_1_to_2_hours": 2,
                "time_2_to_3_hours": 4
            }
        }
    })
    
    # HACCP FAIL
    temps = ([140] * 20 +
             list(np.linspace(140, 68, 200)) +  # Too slow
             list(np.linspace(68, 38, 320)) +
             [38] * 200)
    df = pd.DataFrame({"timestamp": times[:len(temps)], "temperature": temps})
    csv_path = RUN_DIR / "haccp_fail_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "haccp",
        "variant": "fail",
        "csv": str(csv_path),
        "spec": {
            "industry": "haccp",
            "parameters": {
                "temp_1": 135,
                "temp_2": 70,
                "temp_3": 41,
                "time_1_to_2_hours": 2,
                "time_2_to_3_hours": 4
            }
        }
    })
    
    # CONCRETE PASS (96% compliance)
    np.random.seed(42)
    times = list(range(0, 172800, 1800))
    temps = []
    humidities = []
    for i in range(len(times)):
        if i < 48:  # First 24 hours
            if np.random.random() < 0.96:
                temps.append(np.random.uniform(12, 28))
                humidities.append(np.random.uniform(82, 95))
            else:
                temps.append(11)
                humidities.append(81)
        else:
            temps.append(np.random.uniform(15, 25))
            humidities.append(np.random.uniform(85, 95))
    df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
    csv_path = RUN_DIR / "concrete_pass_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "concrete",
        "variant": "pass",
        "csv": str(csv_path),
        "spec": {
            "industry": "concrete",
            "parameters": {
                "min_temp": 10,
                "max_temp": 30,
                "min_humidity": 80,
                "time_window_hours": 24
            }
        }
    })
    
    # CONCRETE FAIL (88% compliance)
    np.random.seed(84)
    temps = []
    humidities = []
    for i in range(len(times)):
        if i < 48:
            if np.random.random() < 0.88:
                temps.append(np.random.uniform(12, 28))
                humidities.append(np.random.uniform(82, 95))
            else:
                temps.append(np.random.uniform(5, 9))
                humidities.append(np.random.uniform(70, 78))
        else:
            temps.append(np.random.uniform(15, 25))
            humidities.append(np.random.uniform(85, 95))
    df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
    csv_path = RUN_DIR / "concrete_fail_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "concrete",
        "variant": "fail",
        "csv": str(csv_path),
        "spec": {
            "industry": "concrete",
            "parameters": {
                "min_temp": 10,
                "max_temp": 30,
                "min_humidity": 80,
                "time_window_hours": 24
            }
        }
    })
    
    # STERILE PASS (14 hours exposure)
    times = list(range(0, 86400, 1800))
    temps = []
    humidities = []
    for i in range(len(times)):
        if 5 <= i <= 33:  # 14 hours
            temps.append(np.random.uniform(56, 60))
            humidities.append(np.random.uniform(52, 58))
        else:
            temps.append(np.random.uniform(50, 54))
            humidities.append(np.random.uniform(45, 49))
    df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
    csv_path = RUN_DIR / "sterile_pass_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "sterile",
        "variant": "pass",
        "csv": str(csv_path),
        "spec": {
            "industry": "sterile",
            "parameters": {
                "min_temp": 55,
                "exposure_hours": 12,
                "min_humidity": 50
            }
        }
    })
    
    # STERILE FAIL (10 hours exposure)
    temps = []
    humidities = []
    for i in range(len(times)):
        if 5 <= i <= 25:  # Only 10 hours
            temps.append(np.random.uniform(56, 60))
            humidities.append(np.random.uniform(52, 58))
        else:
            temps.append(np.random.uniform(50, 54))
            humidities.append(np.random.uniform(45, 49))
    df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
    csv_path = RUN_DIR / "sterile_fail_synthetic.csv"
    df.to_csv(csv_path, index=False)
    tests.append({
        "industry": "sterile",
        "variant": "fail",
        "csv": str(csv_path),
        "spec": {
            "industry": "sterile",
            "parameters": {
                "min_temp": 55,
                "exposure_hours": 12,
                "min_humidity": 50
            }
        }
    })
    
    # Run all tests
    matrix_results = {}
    
    for test in tests:
        industry = test["industry"]
        variant = test["variant"]
        
        print(f"\n{industry.upper()} - {variant.upper()}:")
        
        # Load spec
        if isinstance(test["spec"], str):
            with open(test["spec"]) as f:
                spec = json.load(f)
        else:
            spec = test["spec"]
        
        csv_path = Path(test["csv"])
        
        result = submit_and_download(industry, variant, csv_path, spec)
        
        if industry not in matrix_results:
            matrix_results[industry] = {}
        matrix_results[industry][variant] = result
        
        if result["success"]:
            print(f"  ✓ Job ID: {result['job_id']}")
            print(f"  Status: {result['api_status']} (Pass: {result['pass']})")
            if result.get("reasons"):
                print(f"  Reasons: {', '.join(result['reasons'])}")
        else:
            print(f"  ✗ Error: {result['error']}")
        
        time.sleep(RATE_LIMIT_DELAY)
    
    return matrix_results

def main():
    print("=" * 60)
    print("LIVE-QA v2 COMPREHENSIVE AUDIT - FINAL RUN")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Run Directory: {RUN_DIR}\n")
    
    matrix_results = run_all_tests()
    
    # Save results
    matrix_path = RUN_DIR / "matrix_final.json"
    matrix_path.write_text(json.dumps(matrix_results, indent=2))
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_tests = 0
    passed_tests = 0
    
    for industry, variants in matrix_results.items():
        print(f"\n{industry.upper()}:")
        for variant, result in variants.items():
            total_tests += 1
            expected_pass = (variant == "pass")
            
            if result.get("success"):
                actual_pass = result.get("pass", False)
                if actual_pass == expected_pass:
                    print(f"  {variant}: ✅ CORRECT ({result['api_status']})")
                    passed_tests += 1
                else:
                    print(f"  {variant}: ❌ MISMATCH (expected {'PASS' if expected_pass else 'FAIL'}, got {result['api_status']})")
            else:
                print(f"  {variant}: ❌ ERROR - {result.get('error')}")
    
    print(f"\n\nOVERALL: {passed_tests}/{total_tests} tests passed ({passed_tests*100//total_tests}%)")
    print(f"\nResults saved to: {matrix_path}")

if __name__ == "__main__":
    main()