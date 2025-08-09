#!/usr/bin/env python3
"""Post-deployment smoke tests for production validation."""

import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Tuple

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://proofkit.net"

SMOKE_TESTS = {
    "powder": {
        "csv": "tests/fixtures/min_powder.csv",
        "spec": "tests/fixtures/min_powder_spec.json",
        "expected": "PASS"
    },
    "autoclave": {
        "csv": "tests/data/autoclave_sterilization_pass.csv", 
        "spec": "examples/autoclave_sterilization_spec.json",
        "expected": "PASS"
    },
    "coldchain": {
        "csv": "tests/data/coldchain_storage_fail.csv",
        "spec": "examples/coldchain_storage_spec.json",
        "expected": "FAIL"
    },
    "haccp": {
        "csv": "tests/data/haccp_cooling_fail.csv",
        "spec": "examples/haccp_cooling_spec.json",
        "expected": "FAIL"
    },
    "concrete": {
        "csv": "tests/data/concrete_curing_pass.csv",
        "spec": "examples/concrete_curing_spec.json",
        "expected": "PASS"
    }
}

def check_health() -> bool:
    """Check /health endpoint."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            print("✅ Health check passed")
            return True
        else:
            print(f"❌ Health check failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_compile(industry: str, test_data: Dict) -> Tuple[bool, str]:
    """Test compilation for an industry."""
    csv_path = Path(test_data["csv"])
    spec_path = Path(test_data["spec"])
    
    if not csv_path.exists() or not spec_path.exists():
        return False, f"Missing test files for {industry}"
    
    with open(csv_path, 'rb') as csv_file, open(spec_path, 'r') as spec_file:
        files = {'csv_file': csv_file}
        data = {'spec_json': spec_file.read()}
        
        try:
            resp = requests.post(
                f"{BASE_URL}/compile",
                files=files,
                data=data,
                timeout=10
            )
            
            if resp.status_code != 200:
                return False, f"Compile failed with {resp.status_code}"
            
            result = resp.json()
            decision = result.get('decision', {}).get('outcome')
            
            if decision != test_data["expected"]:
                return False, f"Expected {test_data['expected']}, got {decision}"
            
            # Check verify page loads
            job_id = result.get('job_id')
            if job_id:
                verify_resp = requests.get(f"{BASE_URL}/verify/{job_id}", timeout=5)
                if verify_resp.status_code != 200:
                    return False, f"Verify page failed: {verify_resp.status_code}"
            
            return True, f"✅ {industry}: {decision}"
            
        except Exception as e:
            return False, f"Error testing {industry}: {e}"

def main():
    """Run all smoke tests."""
    print(f"🚀 Running post-deploy smoke tests against {BASE_URL}")
    print("-" * 50)
    
    # Health check
    if not check_health():
        print("FATAL: Health check failed")
        sys.exit(1)
    
    # Test each industry
    failures = []
    for industry, test_data in SMOKE_TESTS.items():
        print(f"\nTesting {industry}...")
        success, message = test_compile(industry, test_data)
        print(message)
        if not success:
            failures.append(message)
        time.sleep(1)  # Be nice to the server
    
    print("\n" + "=" * 50)
    if failures:
        print(f"❌ FAILED: {len(failures)} tests failed")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)
    else:
        print("✅ All smoke tests passed!")
        
    # Check campaign page
    try:
        campaign_resp = requests.get(f"{BASE_URL}/campaign", timeout=5)
        if campaign_resp.status_code == 200 and "Golden Pack" in campaign_resp.text:
            print("✅ Campaign page loads with Golden Pack")
        else:
            print("⚠️ Campaign page issue")
    except Exception as e:
        print(f"⚠️ Campaign page error: {e}")
    
    print("\n🎉 Post-deploy validation complete")

if __name__ == "__main__":
    main()