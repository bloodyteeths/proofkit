#!/usr/bin/env python3
"""Simple test to submit one job using cookie authentication."""

import json
import requests
from pathlib import Path

BASE_URL = "https://proofkit-prod.fly.dev"

# Parse the cookie
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
    exit(1)

print(f"Found auth token: {auth_token[:20]}...")

# Create session with cookie
session = requests.Session()
session.cookies.set("auth_token", auth_token, domain="proofkit-prod.fly.dev")

# Test with powder PASS example
csv_path = Path("examples/powder_coat_cure_successful_180c_10min_pass.csv")
spec_path = Path("examples/powder_coat_cure_spec_standard_180c_10min.json")

with open(spec_path) as f:
    spec = json.load(f)

# Submit job
url = f"{BASE_URL}/api/compile/json"

with open(csv_path, 'rb') as csv_file:
    files = {'csv_file': ('data.csv', csv_file, 'text/csv')}
    data = {'spec_json': json.dumps(spec)}
    
    response = session.post(url, files=files, data=data, timeout=30)
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Response keys: {result.keys()}")
        print(f"Success! Job ID: {result.get('job_id')}")
        print(f"Decision: {result.get('decision', {}).get('outcome')}")
        print(f"Full response: {json.dumps(result, indent=2)[:500]}")
        
        # Try to download PDF
        if result.get('job_id'):
            pdf_url = f"{BASE_URL}/output/{result['job_id']}/proof.pdf"
            pdf_resp = session.get(pdf_url)
            if pdf_resp.status_code == 200:
                with open("test_output.pdf", "wb") as f:
                    f.write(pdf_resp.content)
                print("PDF saved to test_output.pdf")
    else:
        print(f"Error: {response.text[:500]}")