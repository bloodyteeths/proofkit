#!/usr/bin/env python3
"""Run comprehensive LIVE-QA v2 audit with authenticated session."""

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
TAG = "LIVE-QA-AUDIT"
RUN_DIR = Path("live_runs/20250809_010745")
RATE_LIMIT_DELAY = 1.5  # seconds between requests

# Load cookies from authentication
session = requests.Session()
with open("cookies.txt") as f:
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.strip().split("\t")
        if len(parts) >= 7:
            session.cookies.set(parts[5], parts[6], domain=parts[0])

def test_powder_pass():
    """Test powder coating PASS case with real data."""
    csv_path = Path("examples/powder_coat_cure_successful_180c_10min_pass.csv")
    spec_path = Path("examples/powder_coat_cure_spec_standard_180c_10min.json")
    
    with open(spec_path) as f:
        spec = json.load(f)
    
    return submit_job("powder", "pass", csv_path, spec)

def test_powder_fail():
    """Test powder coating FAIL case with real data."""
    csv_path = Path("examples/powder_coat_cure_insufficient_hold_time_fail.csv")
    spec_path = Path("examples/powder_coat_cure_spec_standard_180c_10min.json")
    
    with open(spec_path) as f:
        spec = json.load(f)
    
    return submit_job("powder", "fail", csv_path, spec)

def test_autoclave_pass():
    """Test autoclave PASS case with synthetic data."""
    # Generate passing autoclave data
    times = list(range(0, 2400, 30))  # 40 minutes, 30-sec intervals
    temps = ([20] * 10 +  # Ramp up
             [121.5] * 40 +  # Hold at 121°C for 20 minutes
             [80] * 30)  # Cool down
    pressures = ([1] * 10 +  # Low pressure
                 [2.1] * 40 +  # Operating pressure
                 [1] * 30)  # Back to atmospheric
    
    df = pd.DataFrame({
        "timestamp": times,
        "temperature": temps,
        "pressure": pressures
    })
    
    csv_path = RUN_DIR / "autoclave" / "pass" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "autoclave",
        "parameters": {
            "sterilization_temp": 121,
            "sterilization_time_minutes": 15,
            "min_pressure_bar": 2.0
        }
    }
    
    return submit_job("autoclave", "pass", csv_path, spec)

def test_autoclave_fail():
    """Test autoclave FAIL case - insufficient hold time."""
    times = list(range(0, 2400, 30))
    temps = ([20] * 10 +  # Ramp up
             [121.5] * 20 +  # Hold for only 10 minutes (FAIL)
             [80] * 50)  # Cool down
    pressures = ([1] * 10 +
                 [2.1] * 20 +
                 [1] * 50)
    
    df = pd.DataFrame({
        "timestamp": times,
        "temperature": temps,
        "pressure": pressures
    })
    
    csv_path = RUN_DIR / "autoclave" / "fail" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "autoclave",
        "parameters": {
            "sterilization_temp": 121,
            "sterilization_time_minutes": 15,
            "min_pressure_bar": 2.0
        }
    }
    
    return submit_job("autoclave", "fail", csv_path, spec)

def test_coldchain_pass():
    """Test cold chain PASS case - 96% compliance."""
    np.random.seed(42)
    times = list(range(0, 86400, 300))  # 24 hours, 5-min intervals
    temps = []
    
    for _ in range(len(times)):
        if np.random.random() < 0.96:  # 96% compliance (PASS)
            temps.append(np.random.uniform(3, 7))
        else:
            temps.append(9)  # Slightly out of range
    
    df = pd.DataFrame({"timestamp": times, "temperature": temps})
    
    csv_path = RUN_DIR / "coldchain" / "pass" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "coldchain",
        "parameters": {
            "min_temp": 2,
            "max_temp": 8,
            "compliance_percentage": 95
        }
    }
    
    return submit_job("coldchain", "pass", csv_path, spec)

def test_coldchain_fail():
    """Test cold chain FAIL case - 90% compliance."""
    np.random.seed(84)
    times = list(range(0, 86400, 300))
    temps = []
    
    for _ in range(len(times)):
        if np.random.random() < 0.90:  # 90% compliance (FAIL)
            temps.append(np.random.uniform(3, 7))
        else:
            temps.append(np.random.uniform(9, 12))  # Out of range
    
    df = pd.DataFrame({"timestamp": times, "temperature": temps})
    
    csv_path = RUN_DIR / "coldchain" / "fail" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "coldchain",
        "parameters": {
            "min_temp": 2,
            "max_temp": 8,
            "compliance_percentage": 95
        }
    }
    
    return submit_job("coldchain", "fail", csv_path, spec)

def test_haccp_pass():
    """Test HACCP PASS case - proper cooling curve."""
    times = list(range(0, 25200, 30))  # 7 hours, 30-sec intervals
    temps = ([140] * 20 +  # Start hot (135°F)
             list(np.linspace(140, 68, 120)) +  # Cool to 70°F in 1 hour
             list(np.linspace(68, 38, 200)) +  # Cool to 41°F in 3 hours
             [38] * 320)  # Stay cold
    
    df = pd.DataFrame({
        "timestamp": times[:len(temps)],
        "temperature": temps
    })
    
    csv_path = RUN_DIR / "haccp" / "pass" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
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
    
    return submit_job("haccp", "pass", csv_path, spec)

def test_haccp_fail():
    """Test HACCP FAIL case - too slow cooling."""
    times = list(range(0, 25200, 30))
    temps = ([140] * 20 +  # Start hot
             list(np.linspace(140, 68, 200)) +  # Too slow to 70°F (3+ hours)
             list(np.linspace(68, 38, 320)) +  # Too slow to 41°F (5+ hours)
             [38] * 200)  # Stay cold
    
    df = pd.DataFrame({
        "timestamp": times[:len(temps)],
        "temperature": temps
    })
    
    csv_path = RUN_DIR / "haccp" / "fail" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
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
    
    return submit_job("haccp", "fail", csv_path, spec)

def test_concrete_pass():
    """Test concrete PASS case - 96% compliance in first 24h."""
    np.random.seed(42)
    times = list(range(0, 172800, 1800))  # 48 hours, 30-min intervals
    temps = []
    humidities = []
    
    for i in range(len(times)):
        if i < 48:  # First 24 hours
            if np.random.random() < 0.96:  # 96% compliance
                temps.append(np.random.uniform(12, 28))
                humidities.append(np.random.uniform(82, 95))
            else:
                temps.append(11)  # Slightly out
                humidities.append(81)
        else:
            temps.append(np.random.uniform(15, 25))
            humidities.append(np.random.uniform(85, 95))
    
    df = pd.DataFrame({
        "timestamp": times,
        "temperature": temps,
        "humidity": humidities
    })
    
    csv_path = RUN_DIR / "concrete" / "pass" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "concrete",
        "parameters": {
            "min_temp": 10,
            "max_temp": 30,
            "min_humidity": 80,
            "time_window_hours": 24
        }
    }
    
    return submit_job("concrete", "pass", csv_path, spec)

def test_concrete_fail():
    """Test concrete FAIL case - 88% compliance in first 24h."""
    np.random.seed(84)
    times = list(range(0, 172800, 1800))
    temps = []
    humidities = []
    
    for i in range(len(times)):
        if i < 48:  # First 24 hours
            if np.random.random() < 0.88:  # 88% compliance (FAIL)
                temps.append(np.random.uniform(12, 28))
                humidities.append(np.random.uniform(82, 95))
            else:
                temps.append(np.random.uniform(5, 9))  # Too cold
                humidities.append(np.random.uniform(70, 78))  # Too dry
        else:
            temps.append(np.random.uniform(15, 25))
            humidities.append(np.random.uniform(85, 95))
    
    df = pd.DataFrame({
        "timestamp": times,
        "temperature": temps,
        "humidity": humidities
    })
    
    csv_path = RUN_DIR / "concrete" / "fail" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "concrete",
        "parameters": {
            "min_temp": 10,
            "max_temp": 30,
            "min_humidity": 80,
            "time_window_hours": 24
        }
    }
    
    return submit_job("concrete", "fail", csv_path, spec)

def test_sterile_pass():
    """Test sterile PASS case - 14 hours continuous exposure."""
    times = list(range(0, 86400, 1800))  # 24 hours, 30-min intervals
    temps = []
    humidities = []
    
    for i in range(len(times)):
        if 5 <= i <= 33:  # 14 hours of continuous exposure
            temps.append(np.random.uniform(56, 60))
            humidities.append(np.random.uniform(52, 58))
        else:
            temps.append(np.random.uniform(50, 54))
            humidities.append(np.random.uniform(45, 49))
    
    df = pd.DataFrame({
        "timestamp": times,
        "temperature": temps,
        "humidity": humidities
    })
    
    csv_path = RUN_DIR / "sterile" / "pass" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "sterile",
        "parameters": {
            "min_temp": 55,
            "exposure_hours": 12,
            "min_humidity": 50
        }
    }
    
    return submit_job("sterile", "pass", csv_path, spec)

def test_sterile_fail():
    """Test sterile FAIL case - only 10 hours exposure."""
    times = list(range(0, 86400, 1800))
    temps = []
    humidities = []
    
    for i in range(len(times)):
        if 5 <= i <= 25:  # Only 10 hours (FAIL)
            temps.append(np.random.uniform(56, 60))
            humidities.append(np.random.uniform(52, 58))
        else:
            temps.append(np.random.uniform(50, 54))
            humidities.append(np.random.uniform(45, 49))
    
    df = pd.DataFrame({
        "timestamp": times,
        "temperature": temps,
        "humidity": humidities
    })
    
    csv_path = RUN_DIR / "sterile" / "fail" / "input.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    
    spec = {
        "industry": "sterile",
        "parameters": {
            "min_temp": 55,
            "exposure_hours": 12,
            "min_humidity": 50
        }
    }
    
    return submit_job("sterile", "fail", csv_path, spec)

def submit_job(industry: str, variant: str, csv_path: Path, spec: dict):
    """Submit a job to the ProofKit API."""
    url = f"{BASE_URL}/api/compile/json"
    
    # Save spec for reference
    spec_path = RUN_DIR / industry / variant / "spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2))
    
    # Prepare the files
    files = {
        'csv_file': ('data.csv', open(csv_path, 'rb'), 'text/csv')
    }
    
    data = {
        'spec_json': json.dumps(spec),
        'email': EMAIL,
        'tag': f"{TAG}-{industry}-{variant}"
    }
    
    try:
        response = session.post(url, files=files, data=data, timeout=30)
        files['csv_file'][1].close()
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get("job_id")
            
            # Download artifacts
            output_dir = RUN_DIR / industry / variant
            artifacts = download_artifacts(job_id, output_dir)
            
            return {
                "success": True,
                "job_id": job_id,
                "api_status": result.get("decision", {}).get("outcome"),
                "artifacts": artifacts
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
        resp = session.get(pdf_url, timeout=10)
        if resp.status_code == 200:
            pdf_path = output_dir / "proof.pdf"
            pdf_path.write_bytes(resp.content)
            artifacts["pdf"] = str(pdf_path)
            print(f"      Downloaded PDF: {pdf_path}")
    except Exception as e:
        print(f"      Failed to download PDF: {e}")
    
    # Download bundle
    bundle_url = f"{BASE_URL}/output/{job_id}/evidence.zip"
    try:
        resp = session.get(bundle_url, timeout=10)
        if resp.status_code == 200:
            bundle_path = output_dir / "evidence.zip"
            bundle_path.write_bytes(resp.content)
            artifacts["bundle"] = str(bundle_path)
            print(f"      Downloaded bundle: {bundle_path}")
    except Exception as e:
        print(f"      Failed to download bundle: {e}")
    
    return artifacts

def main():
    print(f"=== LIVE-QA v2 COMPREHENSIVE AUDIT ===")
    print(f"Timestamp: {datetime.now()}")
    print(f"Base URL: {BASE_URL}")
    print(f"Email: {EMAIL}")
    print(f"Run Directory: {RUN_DIR}")
    print("")
    
    # Test matrix
    tests = [
        ("powder", "pass", test_powder_pass),
        ("powder", "fail", test_powder_fail),
        ("autoclave", "pass", test_autoclave_pass),
        ("autoclave", "fail", test_autoclave_fail),
        ("coldchain", "pass", test_coldchain_pass),
        ("coldchain", "fail", test_coldchain_fail),
        ("haccp", "pass", test_haccp_pass),
        ("haccp", "fail", test_haccp_fail),
        ("concrete", "pass", test_concrete_pass),
        ("concrete", "fail", test_concrete_fail),
        ("sterile", "pass", test_sterile_pass),
        ("sterile", "fail", test_sterile_fail),
    ]
    
    matrix_results = {}
    
    for industry, variant, test_func in tests:
        print(f"\n{industry.upper()} - {variant.upper()}:")
        print(f"  Running test...")
        
        result = test_func()
        
        if industry not in matrix_results:
            matrix_results[industry] = {}
        matrix_results[industry][variant] = result
        
        if result["success"]:
            print(f"  ✅ Job ID: {result['job_id']}")
            print(f"  Status: {result['api_status']}")
            print(f"  Artifacts: {len(result.get('artifacts', {}))} downloaded")
        else:
            print(f"  ❌ Error: {result['error']}")
        
        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)
    
    # Save matrix results
    matrix_path = RUN_DIR / "matrix.json"
    matrix_path.write_text(json.dumps(matrix_results, indent=2))
    print(f"\n\nMatrix results saved to: {matrix_path}")
    
    # Print summary
    print("\n=== SUMMARY ===")
    total_tests = 0
    passed_tests = 0
    
    for industry, variants in matrix_results.items():
        print(f"\n{industry}:")
        for variant, result in variants.items():
            total_tests += 1
            if "error" in result:
                print(f"  {variant}: ❌ ERROR - {result['error']}")
            else:
                status = result.get('api_status', 'UNKNOWN')
                expected = "PASS" if variant == "pass" else "FAIL"
                
                if status == expected:
                    print(f"  {variant}: ✅ {status} (correct)")
                    passed_tests += 1
                else:
                    print(f"  {variant}: ❌ {status} (expected {expected})")
    
    print(f"\n\nOverall: {passed_tests}/{total_tests} tests passed ({passed_tests*100//total_tests}%)")

if __name__ == "__main__":
    main()