#!/usr/bin/env python3
"""
Generate Examples Manifest

This script generates a live manifest.json file for the examples page by calling the 
ProofKit API v2 with all 12 example datasets, capturing the results, and storing 
metadata about the live verification results.

The manifest includes:
- PASS/FAIL status for each example
- Timestamp of verification (UTC)
- Links to generated PDF and ZIP artifacts
- Example metadata (industry, description, etc.)

Usage:
    python scripts/generate_examples_manifest.py [--base-url http://localhost:8000]
"""

import json
import requests
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# Add the project root to the Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Example definitions with their CSV and JSON spec files
EXAMPLES = [
    # PASS Examples
    {
        "id": "powder_standard_pass",
        "name": "Standard 180°C Powder Cure",
        "industry": "powder",
        "category": "pass",
        "icon": "🎨",
        "description": "Premium automotive wheel coating with clean temperature ramp and adequate hold time. Demonstrates ideal cure profile with dual PMT sensors.",
        "csv_file": "powder_coat_cure_successful_180c_10min_pass.csv",
        "spec_file": "powder_coat_cure_spec_standard_180c_10min.json",
        "details": {
            "Target": "180°C for 10 minutes",
            "Sensors": "Dual PMT (min_of_set)",
            "Logic": "Continuous hold required"
        }
    },
    {
        "id": "autoclave_sterilization_pass",
        "name": "Steam Sterilization Cycle",
        "industry": "autoclave",
        "category": "pass", 
        "icon": "🏥",
        "description": "Medical device sterilization at 121°C with proper come-up time and steam penetration. F0 value calculation demonstrates sterility assurance.",
        "csv_file": "autoclave_sterilization_pass.csv",
        "spec_file": "autoclave-medical-device-validation.json",
        "details": {
            "Target": "121°C for 15 minutes",
            "F0 Value": "18.2 minutes",
            "Application": "Medical devices"
        }
    },
    {
        "id": "concrete_curing_pass",
        "name": "Concrete Curing Monitoring",
        "industry": "concrete",
        "category": "pass",
        "icon": "🏗️", 
        "description": "Structural concrete curing with proper temperature management per ASTM C31. Demonstrates controlled heat of hydration for strength development.",
        "csv_file": "concrete_curing_pass.csv",
        "spec_file": "concrete-curing-astm-c31.json",
        "details": {
            "Standard": "ASTM C31",
            "Duration": "72 hours",
            "Max Temp": "65°C"
        }
    },
    {
        "id": "coldchain_storage_pass",
        "name": "Cold Chain Storage",
        "industry": "coldchain",
        "category": "pass",
        "icon": "❄️",
        "description": "Pharmaceutical cold storage maintaining proper temperature range throughout storage period. Demonstrates continuous monitoring and compliance.",
        "csv_file": "coldchain_storage_pass.csv", 
        "spec_file": "coldchain-storage-validation.json",
        "details": {
            "Range": "2°C to 8°C",
            "Duration": "72 hours", 
            "Standard": "USP 797"
        }
    },
    {
        "id": "haccp_cooling_pass",
        "name": "HACCP Cooling Process",
        "industry": "haccp",
        "category": "pass",
        "icon": "🍽️",
        "description": "Restaurant cooling process following FDA Food Code requirements. Demonstrates proper cooling from 135°F to 41°F within time limits.",
        "csv_file": "haccp_cooling_pass.csv",
        "spec_file": "haccp-cooling-validation.json", 
        "details": {
            "Pattern": "135°F → 70°F → 41°F",
            "Time Limit": "2hr + 4hr",
            "Standard": "FDA Food Code"
        }
    },
    {
        "id": "sterile_processing_pass",
        "name": "Steam Sterile Processing",
        "industry": "sterile",
        "category": "pass",
        "icon": "🧪",
        "description": "Clean steam sterilization cycle with proper time/temperature parameters. Demonstrates sterility assurance per ISO 17665 requirements.",
        "csv_file": "sterile_processing_pass.csv",
        "spec_file": "sterile-processing-validation.json",
        "details": {
            "Temperature": "121°C",
            "Hold Time": "15 minutes",
            "Standard": "ISO 17665"
        }
    },
    
    # INDETERMINATE Examples
    {
        "id": "autoclave_missing_pressure",
        "name": "Missing Pressure Sensor",
        "industry": "autoclave", 
        "category": "indeterminate",
        "icon": "🏥",
        "description": "Autoclave sterilization cycle with temperature data only. Cannot validate sterility without required pressure measurements for steam qualification.",
        "csv_file": "autoclave_missing_pressure_indeterminate.csv",
        "spec_file": "autoclave-medical-device-validation.json",
        "details": {
            "Issue": "Pressure data required but missing",
            "Available": "Temperature sensors only",
            "Required": "Temperature + pressure + F0"
        }
    },
    
    # FAIL Examples
    {
        "id": "powder_insufficient_hold",
        "name": "Insufficient Hold Time",
        "industry": "powder",
        "category": "fail",
        "icon": "🎨",
        "description": "Industrial bracket coating where temperature reaches target but cools down too quickly. Demonstrates failure due to inadequate time at cure temperature.",
        "csv_file": "powder_coat_cure_insufficient_hold_time_fail.csv",
        "spec_file": "powder_coat_cure_spec_standard_180c_10min.json",
        "details": {
            "Issue": "Only ~4 minutes at temperature",
            "Cause": "Rapid cooling after reaching target",
            "Required": "10 minutes minimum"
        }
    },
    {
        "id": "autoclave_sterilization_fail",
        "name": "Incomplete Steam Penetration",
        "industry": "autoclave",
        "category": "fail",
        "icon": "🏥",
        "description": "Sterilization cycle fails due to inadequate steam penetration. Temperature sensors show uneven heating, compromising sterility assurance.",
        "csv_file": "autoclave_sterilization_fail.csv",
        "spec_file": "autoclave-medical-device-validation.json",
        "details": {
            "Issue": "Uneven temperature distribution",
            "F0 Value": "6.2 minutes (insufficient)",
            "Minimum": "8.0 minutes required"
        }
    },
    {
        "id": "concrete_curing_fail", 
        "name": "Temperature Runaway",
        "industry": "concrete",
        "category": "fail",
        "icon": "🏗️",
        "description": "Concrete pour with excessive heat of hydration due to high cement content. Temperature exceeds safe limits, risking thermal cracking.",
        "csv_file": "concrete_curing_fail.csv",
        "spec_file": "concrete-curing-astm-c31.json",
        "details": {
            "Peak Temp": "78°C (exceeded limit)",
            "Limit": "65°C maximum",
            "Risk": "Thermal cracking"
        }
    },
    {
        "id": "coldchain_storage_fail",
        "name": "Temperature Excursion", 
        "industry": "coldchain",
        "category": "fail",
        "icon": "❄️",
        "description": "Cold storage failure due to equipment malfunction. Temperature rises above safe limits, compromising product integrity.",
        "csv_file": "coldchain_storage_fail.csv",
        "spec_file": "coldchain-storage-validation.json",
        "details": {
            "Peak Temp": "15°C (exceeded limit)",
            "Safe Range": "2°C to 8°C",
            "Duration": "45 minutes above limit"
        }
    },
    {
        "id": "haccp_cooling_fail",
        "name": "Slow Cooling Violation",
        "industry": "haccp", 
        "category": "fail",
        "icon": "🍽️",
        "description": "Food cooling process fails to meet FDA timing requirements. Temperature stays in danger zone too long, risking bacterial growth.",
        "csv_file": "haccp_cooling_fail.csv",
        "spec_file": "haccp-cooling-validation.json",
        "details": {
            "Issue": "Slow cooling to 70°F",
            "Time Exceeded": "3.5 hours (limit: 2hr)",
            "Risk": "Pathogen growth"
        }
    },
    {
        "id": "sterile_processing_fail",
        "name": "Inadequate Sterilization",
        "industry": "sterile",
        "category": "fail", 
        "icon": "🧪",
        "description": "Sterile processing cycle with insufficient temperature exposure. Fails to achieve required sterility assurance level.",
        "csv_file": "sterile_processing_fail.csv",
        "spec_file": "sterile-processing-validation.json",
        "details": {
            "Issue": "Temperature dips below target", 
            "Achieved": "118°C average",
            "Required": "121°C minimum"
        }
    }
]


class ExampleGenerator:
    """Generate live examples manifest by calling ProofKit API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.examples_dir = PROJECT_ROOT / "examples"
        self.static_dir = PROJECT_ROOT / "web" / "static"
        self.session = requests.Session()
        
        # Create examples static directory if it doesn't exist
        self.examples_static_dir = self.static_dir / "examples"
        self.examples_static_dir.mkdir(parents=True, exist_ok=True)
        
    def load_csv_file(self, filename: str) -> str:
        """Load CSV file content as string."""
        csv_path = self.examples_dir / filename
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def load_spec_file(self, filename: str) -> Dict[str, Any]:
        """Load JSON spec file."""
        spec_path = self.examples_dir / filename
        if not spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")
        
        with open(spec_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def call_api(self, csv_content: str, spec_data: Dict[str, Any], industry: str) -> Dict[str, Any]:
        """Call ProofKit API v2 to generate live results."""
        # Prepare multipart form data  
        files = {
            'csv_file': ('data.csv', csv_content, 'text/csv')
        }
        
        data = {
            'spec_json': json.dumps(spec_data),
            'industry': industry
        }
        
        try:
            # Use the JSON API endpoint for cleaner response
            response = self.session.post(
                f"{self.base_url}/api/compile/json",
                files=files,
                data=data,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API call failed with status {response.status_code}: {response.text}")
                return {
                    "error": f"API call failed with status {response.status_code}",
                    "status_code": response.status_code,
                    "response": response.text
                }
                
        except Exception as e:
            logger.error(f"Exception during API call: {e}")
            return {
                "error": f"Exception during API call: {str(e)}"
            }
    
    def process_example(self, example: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single example and return result metadata."""
        logger.info(f"Processing example: {example['id']}")
        
        try:
            # Load files
            csv_content = self.load_csv_file(example['csv_file'])
            spec_data = self.load_spec_file(example['spec_file'])
            
            # Call API
            api_result = self.call_api(csv_content, spec_data, example['industry'])
            
            # Extract key information for manifest
            result = {
                "id": example['id'],
                "name": example['name'], 
                "industry": example['industry'],
                "category": example['category'],
                "icon": example['icon'],
                "description": example['description'],
                "details": example['details'],
                "csv_file": example['csv_file'],
                "spec_file": example['spec_file'],
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "api_success": "error" not in api_result
            }
            
            if result["api_success"]:
                # Extract result data
                result.update({
                    "status": api_result.get("status", "UNKNOWN"),
                    "job_id": api_result.get("job_id"),
                    "pdf_url": f"/download/{api_result.get('job_id')}/pdf" if api_result.get('job_id') else None,
                    "zip_url": f"/download/{api_result.get('job_id')}/zip" if api_result.get('job_id') else None,
                    "verify_url": f"/verify/{api_result.get('job_id')}" if api_result.get('job_id') else None,
                    "decision": api_result.get("decision", {}),
                    "metrics": api_result.get("metrics", {})
                })
                
                logger.info(f"✅ {example['id']}: {result['status']}")
            else:
                result.update({
                    "status": "ERROR", 
                    "error": api_result.get("error", "Unknown error"),
                    "api_response": api_result
                })
                logger.error(f"❌ {example['id']}: {result['error']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Exception processing {example['id']}: {e}")
            return {
                "id": example['id'],
                "name": example['name'],
                "industry": example['industry'], 
                "category": example['category'],
                "icon": example['icon'],
                "description": example['description'],
                "details": example['details'],
                "csv_file": example['csv_file'],
                "spec_file": example['spec_file'],
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "api_success": False,
                "status": "ERROR",
                "error": str(e)
            }
    
    def generate_manifest(self) -> Dict[str, Any]:
        """Generate the complete examples manifest."""
        logger.info(f"Generating examples manifest from {len(EXAMPLES)} examples")
        
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": self.base_url,
            "total_examples": len(EXAMPLES),
            "examples": []
        }
        
        # Process each example
        for example in EXAMPLES:
            result = self.process_example(example)
            manifest["examples"].append(result)
        
        # Add summary statistics
        successful = sum(1 for ex in manifest["examples"] if ex["api_success"])
        pass_count = sum(1 for ex in manifest["examples"] if ex.get("status") == "PASS")
        fail_count = sum(1 for ex in manifest["examples"] if ex.get("status") == "FAIL")
        indeterminate_count = sum(1 for ex in manifest["examples"] if ex.get("status") == "INDETERMINATE")
        error_count = sum(1 for ex in manifest["examples"] if ex.get("status") == "ERROR")
        
        manifest["summary"] = {
            "successful_calls": successful,
            "failed_calls": len(EXAMPLES) - successful,
            "pass_results": pass_count,
            "fail_results": fail_count,
            "indeterminate_results": indeterminate_count,
            "error_results": error_count
        }
        
        logger.info(f"Manifest complete: {successful}/{len(EXAMPLES)} successful API calls")
        logger.info(f"Results: {pass_count} PASS, {fail_count} FAIL, {indeterminate_count} INDETERMINATE, {error_count} ERROR")
        
        return manifest
    
    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Save manifest to web/static/examples/manifest.json."""
        manifest_path = self.examples_static_dir / "manifest.json"
        
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Manifest saved to: {manifest_path}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate live examples manifest")
    parser.add_argument(
        "--base-url", 
        default="http://localhost:8000",
        help="Base URL for ProofKit API (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
    
    generator = ExampleGenerator(base_url=args.base_url)
    
    try:
        manifest = generator.generate_manifest()
        generator.save_manifest(manifest)
        
        # Print summary
        print("\n" + "="*50)
        print("EXAMPLES MANIFEST GENERATION COMPLETE")
        print("="*50)
        print(f"Total examples processed: {manifest['total_examples']}")
        print(f"Successful API calls: {manifest['summary']['successful_calls']}")
        print(f"Failed API calls: {manifest['summary']['failed_calls']}")
        print(f"PASS results: {manifest['summary']['pass_results']}")
        print(f"FAIL results: {manifest['summary']['fail_results']}")
        print(f"INDETERMINATE results: {manifest['summary']['indeterminate_results']}")
        print(f"ERROR results: {manifest['summary']['error_results']}")
        print(f"\nManifest saved to: web/static/examples/manifest.json")
        
        if manifest['summary']['failed_calls'] > 0:
            print("\n⚠️  Some API calls failed - check logs above for details")
            sys.exit(1)
        else:
            print("\n✅ All examples processed successfully!")
            
    except Exception as e:
        logger.error(f"Failed to generate manifest: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()