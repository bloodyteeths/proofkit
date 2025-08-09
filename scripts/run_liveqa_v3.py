#!/usr/bin/env python3
"""LIVE-QA v3 Comprehensive Audit - Testing all fixes."""

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
TAG = "LIVE-QA-V3"
RUN_DIR = Path("live_runs/20250809_v3")
RUN_DIR.mkdir(parents=True, exist_ok=True)
RATE_LIMIT_DELAY = 1.0

# Parse auth token
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

session = requests.Session()
session.cookies.set("auth_token", auth_token, domain="proofkit-prod.fly.dev")

def submit_test(industry: str, variant: str, csv_path: Path, spec: dict):
    """Submit test and download artifacts."""
    url = f"{BASE_URL}/api/compile/json"
    output_dir = RUN_DIR / industry / variant
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save inputs
    spec_path = output_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))
    
    import shutil
    shutil.copy(csv_path, output_dir / "input.csv")
    
    # Submit
    with open(csv_path, 'rb') as csv_file:
        files = {'csv_file': ('data.csv', csv_file, 'text/csv')}
        data = {
            'spec_json': json.dumps(spec),
            'industry': industry
        }
        
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
                
                # Download bundle
                if result.get("urls", {}).get("zip"):
                    zip_url = BASE_URL + result["urls"]["zip"]
                    zip_resp = session.get(zip_url, timeout=10)
                    if zip_resp.status_code == 200:
                        zip_path = output_dir / "evidence.zip"
                        zip_path.write_bytes(zip_resp.content)
                
                return {
                    "success": True,
                    "job_id": job_id,
                    "api_status": result.get("status"),
                    "pass": result.get("pass"),
                    "error_detail": None
                }
            else:
                error_body = {}
                try:
                    error_body = response.json()
                except:
                    error_body = {"raw": response.text[:200]}
                
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "error_detail": error_body
                }
        except Exception as e:
            return {"success": False, "error": str(e), "error_detail": None}

def generate_test_data(industry: str, variant: str):
    """Generate test data for each industry."""
    
    if industry == "powder":
        # Use fixed examples
        if variant == "pass":
            return Path("examples/powder_pass_fixed.csv"), {
                "industry": "powder",
                "parameters": {
                    "target_temp": 180,
                    "hold_duration_minutes": 10,
                    "sensor_uncertainty": 2,
                    "max_ramp_rate": 15
                }
            }
        else:
            return Path("examples/powder_coat_cure_insufficient_hold_time_fail.csv"), {
                "industry": "powder",
                "parameters": {
                    "target_temp": 180,
                    "hold_duration_minutes": 10,
                    "sensor_uncertainty": 2,
                    "max_ramp_rate": 50
                }
            }
    
    elif industry == "autoclave":
        times = list(range(0, 2400, 30))
        if variant == "pass":
            temps = [20] * 10 + [121.5] * 40 + [80] * 30
            pressures = [1] * 10 + [2.1] * 40 + [1] * 30
        else:
            temps = [20] * 10 + [121.5] * 20 + [80] * 50
            pressures = [1] * 10 + [2.1] * 20 + [1] * 50
        
        df = pd.DataFrame({"timestamp": times, "temperature": temps, "pressure": pressures})
        csv_path = RUN_DIR / f"autoclave_{variant}_test.csv"
        df.to_csv(csv_path, index=False)
        
        return csv_path, {
            "industry": "autoclave",
            "parameters": {
                "sterilization_temp": 121,
                "sterilization_time_minutes": 15,
                "min_pressure_bar": 2.0
            }
        }
    
    elif industry == "coldchain":
        np.random.seed(42 if variant == "pass" else 84)
        times = list(range(0, 86400, 300))
        
        if variant == "pass":
            temps = [np.random.uniform(3, 7) if np.random.random() < 0.96 else 8.5 for _ in range(len(times))]
        else:
            temps = [np.random.uniform(3, 7) if np.random.random() < 0.90 else np.random.uniform(9, 12) for _ in range(len(times))]
        
        df = pd.DataFrame({"timestamp": times, "temperature": temps})
        csv_path = RUN_DIR / f"coldchain_{variant}_test.csv"
        df.to_csv(csv_path, index=False)
        
        return csv_path, {
            "industry": "coldchain",
            "parameters": {
                "min_temp": 2,
                "max_temp": 8,
                "compliance_percentage": 95
            }
        }
    
    elif industry == "haccp":
        times = list(range(0, 25200, 30))
        
        if variant == "pass":
            temps = ([140] * 20 +
                    list(np.linspace(140, 68, 120)) +
                    list(np.linspace(68, 38, 200)) +
                    [38] * 320)
        else:
            temps = ([140] * 20 +
                    list(np.linspace(140, 68, 200)) +
                    list(np.linspace(68, 38, 320)) +
                    [38] * 200)
        
        df = pd.DataFrame({"timestamp": times[:len(temps)], "temperature": temps})
        csv_path = RUN_DIR / f"haccp_{variant}_test.csv"
        df.to_csv(csv_path, index=False)
        
        return csv_path, {
            "industry": "haccp",
            "parameters": {
                "temp_1": 135,
                "temp_2": 70,
                "temp_3": 41,
                "time_1_to_2_hours": 2,
                "time_2_to_3_hours": 4
            }
        }
    
    elif industry == "concrete":
        np.random.seed(42 if variant == "pass" else 84)
        times = list(range(0, 172800, 1800))
        temps = []
        humidities = []
        
        for i in range(len(times)):
            if i < 48:
                if variant == "pass":
                    if np.random.random() < 0.96:
                        temps.append(np.random.uniform(12, 28))
                        humidities.append(np.random.uniform(82, 95))
                    else:
                        temps.append(11)
                        humidities.append(81)
                else:
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
        csv_path = RUN_DIR / f"concrete_{variant}_test.csv"
        df.to_csv(csv_path, index=False)
        
        return csv_path, {
            "industry": "concrete",
            "parameters": {
                "min_temp": 10,
                "max_temp": 30,
                "min_humidity": 80,
                "time_window_hours": 24
            }
        }
    
    elif industry == "sterile":
        times = list(range(0, 86400, 1800))
        temps = []
        humidities = []
        
        for i in range(len(times)):
            if variant == "pass":
                if 5 <= i <= 33:
                    temps.append(np.random.uniform(56, 60))
                    humidities.append(np.random.uniform(52, 58))
                else:
                    temps.append(np.random.uniform(50, 54))
                    humidities.append(np.random.uniform(45, 49))
            else:
                if 5 <= i <= 25:
                    temps.append(np.random.uniform(56, 60))
                    humidities.append(np.random.uniform(52, 58))
                else:
                    temps.append(np.random.uniform(50, 54))
                    humidities.append(np.random.uniform(45, 49))
        
        df = pd.DataFrame({"timestamp": times, "temperature": temps, "humidity": humidities})
        csv_path = RUN_DIR / f"sterile_{variant}_test.csv"
        df.to_csv(csv_path, index=False)
        
        return csv_path, {
            "industry": "sterile",
            "parameters": {
                "min_temp": 55,
                "exposure_hours": 12,
                "min_humidity": 50
            }
        }

def main():
    print("=" * 60)
    print("LIVE-QA v3 COMPREHENSIVE AUDIT")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Run Directory: {RUN_DIR}\n")
    
    industries = ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"]
    variants = ["pass", "fail"]
    
    matrix_results = {}
    
    for industry in industries:
        print(f"\n=== {industry.upper()} ===")
        matrix_results[industry] = {}
        
        for variant in variants:
            print(f"  {variant.upper()}:")
            
            csv_path, spec = generate_test_data(industry, variant)
            result = submit_test(industry, variant, csv_path, spec)
            
            matrix_results[industry][variant] = result
            
            if result["success"]:
                status_icon = "✅" if result["pass"] == (variant == "pass") else "❌"
                print(f"    {status_icon} Status: {result['api_status']}")
                print(f"    Job ID: {result['job_id']}")
            else:
                print(f"    ❌ Error: {result['error']}")
                if result.get("error_detail"):
                    detail = result["error_detail"]
                    if isinstance(detail, dict) and "hints" in detail:
                        print(f"    Hints: {', '.join(detail['hints'][:2])}")
            
            time.sleep(RATE_LIMIT_DELAY)
    
    # Save results
    matrix_path = RUN_DIR / "matrix_v3.json"
    matrix_path.write_text(json.dumps(matrix_results, indent=2))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total = 0
    passed = 0
    
    for industry, variants in matrix_results.items():
        print(f"\n{industry.upper()}:")
        for variant, result in variants.items():
            total += 1
            expected_pass = (variant == "pass")
            
            if result.get("success"):
                actual_pass = result.get("pass", False)
                if actual_pass == expected_pass:
                    print(f"  {variant}: ✅ CORRECT")
                    passed += 1
                else:
                    print(f"  {variant}: ❌ MISMATCH")
            else:
                print(f"  {variant}: ❌ ERROR")
    
    print(f"\n\nOVERALL: {passed}/{total} tests passed ({passed*100//total if total else 0}%)")
    
    return matrix_results

if __name__ == "__main__":
    results = main()