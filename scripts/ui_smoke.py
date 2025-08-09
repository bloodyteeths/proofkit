#!/usr/bin/env python3
"""UI smoke tests for production pages."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List
import requests

def check_homepage(base_url: str) -> Dict:
    """Check homepage for expected content."""
    result = {
        "url": f"{base_url}/",
        "status_code": None,
        "hero_found": False,
        "copy_found": False,
        "passed": False
    }
    
    try:
        resp = requests.get(result["url"], timeout=10)
        result["status_code"] = resp.status_code
        
        if resp.status_code == 200:
            text = resp.text
            
            # Check for hero H1
            if "<h1" in text and ("Generate" in text or "Temperature" in text or "Validation" in text):
                result["hero_found"] = True
            
            # Check for key copy
            if "inspector-ready proof" in text or "compliance" in text.lower() or "validation" in text.lower():
                result["copy_found"] = True
            
            result["passed"] = result["hero_found"] and result["copy_found"]
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def check_industry_page(base_url: str, industry: str) -> Dict:
    """Check industry page for expected content."""
    result = {
        "url": f"{base_url}/industries/{industry}",
        "status_code": None,
        "badge_found": False,
        "industry_name_found": False,
        "passed": False
    }
    
    # Map industry to expected terms
    industry_terms = {
        "powder-coating": ["powder", "coating", "cure"],
        "autoclave": ["autoclave", "sterilization", "F0"],
        "cold-chain": ["cold", "chain", "temperature"],
        "coldchain": ["cold", "chain", "temperature"],
        "haccp": ["haccp", "cooling", "food"],
        "concrete": ["concrete", "curing", "humidity"],
        "eto": ["eto", "ethylene", "oxide"],
        "sterile": ["sterile", "sterilization"]
    }
    
    try:
        resp = requests.get(result["url"], timeout=10)
        result["status_code"] = resp.status_code
        
        if resp.status_code == 200:
            text = resp.text.lower()
            
            # Check for data-liveqa marker
            if 'data-liveqa="industry"' in resp.text:
                result["badge_found"] = True
            # Fallback to SVG badges or aria-labels
            elif "svg" in text or "badge" in text or "icon" in text:
                result["badge_found"] = True
            
            # Check for industry-specific terms
            terms = industry_terms.get(industry, [industry])
            for term in terms:
                if term in text:
                    result["industry_name_found"] = True
                    break
            
            result["passed"] = result["badge_found"] or result["industry_name_found"]
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def check_examples_page(base_url: str) -> Dict:
    """Check examples page for industry cards."""
    result = {
        "url": f"{base_url}/examples",
        "status_code": None,
        "industries_found": [],
        "card_count": 0,
        "passed": False
    }
    
    industries = ["powder", "autoclave", "cold", "haccp", "concrete", "sterile", "eto"]
    
    try:
        resp = requests.get(result["url"], timeout=10)
        result["status_code"] = resp.status_code
        
        if resp.status_code == 200:
            text = resp.text.lower()
            
            # Count cards
            result["card_count"] = text.count("card") or text.count("example-item")
            
            # Check for each industry
            for industry in industries:
                if industry in text:
                    result["industries_found"].append(industry)
            
            # Pass if we have at least 4 industries
            result["passed"] = len(result["industries_found"]) >= 4
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def check_verify_page(base_url: str, job_id: str) -> Dict:
    """Check verify page for expected content."""
    result = {
        "url": f"{base_url}/verify/{job_id}",
        "status_code": None,
        "job_id_found": False,
        "status_chip_found": False,
        "industry_found": False,
        "passed": False
    }
    
    try:
        resp = requests.get(result["url"], timeout=10)
        result["status_code"] = resp.status_code
        
        if resp.status_code == 200:
            text = resp.text
            
            # Check for job ID
            if job_id in text:
                result["job_id_found"] = True
            
            # Check for PASS/FAIL chip
            if "PASS" in text or "FAIL" in text or "INDETERMINATE" in text:
                result["status_chip_found"] = True
            
            # Check for industry name
            industries = ["powder", "autoclave", "cold", "haccp", "concrete", "sterile"]
            for industry in industries:
                if industry.lower() in text.lower():
                    result["industry_found"] = True
                    break
            
            result["passed"] = result["status_chip_found"]
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def run_ui_smoke(base_url: str) -> Dict:
    """Run all UI smoke tests."""
    timestamp = Path("live_runs").glob("*")
    latest_run = max(timestamp, default=None) if timestamp else None
    
    results = {
        "base_url": base_url,
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "homepage": check_homepage(base_url),
        "industries": {},
        "examples": check_examples_page(base_url),
        "verify_pages": {}
    }
    
    # Check industry pages
    industries = ["powder-coating", "autoclave", "cold-chain", "haccp", "concrete", "eto"]
    for industry in industries:
        results["industries"][industry] = check_industry_page(base_url, industry)
        time.sleep(0.5)  # Be nice to the server
    
    # Check verify pages from latest run if available
    if latest_run:
        matrix_file = latest_run / "matrix.json"
        if matrix_file.exists():
            with open(matrix_file) as f:
                matrix = json.load(f)
            
            for industry, variants in matrix.items():
                for variant, result in variants.items():
                    if "job_id" in result:
                        job_id = result["job_id"]
                        verify_result = check_verify_page(base_url, job_id)
                        results["verify_pages"][f"{industry}/{variant}"] = verify_result
                        time.sleep(0.5)
    
    # Calculate summary
    total_checks = 1 + len(results["industries"]) + 1  # homepage + industries + examples
    passed_checks = (
        (1 if results["homepage"].get("passed") else 0) +
        sum(1 for r in results["industries"].values() if r.get("passed")) +
        (1 if results["examples"].get("passed") else 0)
    )
    
    if results["verify_pages"]:
        total_checks += len(results["verify_pages"])
        passed_checks += sum(1 for r in results["verify_pages"].values() if r.get("passed"))
    
    results["summary"] = {
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "pass_rate": round(passed_checks / total_checks * 100, 1) if total_checks > 0 else 0
    }
    
    return results

def main():
    parser = argparse.ArgumentParser(description="UI smoke tests")
    parser.add_argument("--base", default=os.getenv("BASE_URL", "https://proofkit.net"))
    
    args = parser.parse_args()
    
    print(f"Running UI smoke tests against: {args.base}")
    
    results = run_ui_smoke(args.base)
    
    # Save results
    output_dir = Path("live_runs")
    if output_dir.exists():
        latest_run = max(output_dir.glob("*"), default=None)
        if latest_run:
            ui_smoke_file = latest_run / "ui_smoke.json"
            ui_smoke_file.write_text(json.dumps(results, indent=2))
            print(f"Results saved to: {ui_smoke_file}")
    
    # Print summary
    print("\n=== UI SMOKE TEST SUMMARY ===")
    print(f"Homepage: {'✅' if results['homepage'].get('passed') else '❌'}")
    print(f"Examples: {'✅' if results['examples'].get('passed') else '❌'}")
    
    print("\nIndustry Pages:")
    for industry, result in results["industries"].items():
        status = '✅' if result.get('passed') else '❌'
        print(f"  {industry}: {status}")
    
    if results["verify_pages"]:
        print("\nVerify Pages:")
        for page, result in results["verify_pages"].items():
            status = '✅' if result.get('passed') else '❌'
            print(f"  {page}: {status}")
    
    summary = results["summary"]
    print(f"\nOverall: {summary['passed_checks']}/{summary['total_checks']} passed ({summary['pass_rate']}%)")
    
    # Exit with error if pass rate < 80%
    if summary['pass_rate'] < 80:
        print(f"\n❌ UI smoke tests failed: {summary['pass_rate']}% < 80% threshold")
        sys.exit(1)
    
    return 0  # Success

if __name__ == "__main__":
    main()