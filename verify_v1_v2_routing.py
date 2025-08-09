#!/usr/bin/env python3
"""
Simple verification script to test v1/v2 API routing against a running application.

This script sends real HTTP requests to verify that the v1/v2 routing works correctly
for all supported industries. It can be run against localhost or a deployed instance.

Usage:
    python verify_v1_v2_routing.py [--host http://localhost:8000] [--industry powder]
"""

import json
import requests
import argparse
import sys
from typing import Dict, Any, Optional

# Test data for different industries
TEST_CSV_DATA = {
    "powder": "timestamp,temperature\n0,25\n30,160\n60,180\n90,180\n120,180\n150,180\n180,180\n210,180\n240,180\n270,180\n300,180\n330,180\n360,180\n390,180\n420,180\n450,180\n480,180\n510,180\n540,180\n570,180\n600,180\n630,25",
    "autoclave": "timestamp,temperature,pressure\n0,25,1.0\n60,100,2.1\n120,121,2.1\n180,121,2.1\n240,121,2.1\n300,121,2.1\n360,121,2.1\n420,121,2.1\n480,121,2.1\n540,121,2.1\n600,121,2.1\n660,121,2.1\n720,121,2.1\n780,121,2.1\n840,121,2.1\n900,121,2.1\n960,25,1.0",
    "coldchain": "timestamp,temperature\n0,4\n60,5\n120,6\n180,4\n240,3\n300,5\n360,4\n420,6\n480,4\n540,5",
    "haccp": "timestamp,temperature\n0,140\n30,135\n60,135\n90,80\n120,70\n150,70\n180,50\n210,41\n240,41",
    "concrete": "timestamp,temperature,humidity\n0,15,85\n300,20,87\n600,18,83\n900,22,85\n1200,19,84",
    "sterile": "timestamp,temperature,humidity\n0,55,60\n3600,58,65\n7200,56,62\n10800,57,63\n14400,55,61"
}

# V1 legacy format specifications
V1_SPECS = {
    "powder": {
        "spec": {
            "target_temp_C": 180,
            "hold_time_s": 600,
            "sensor_uncertainty_C": 2,
            "method": "PMT"
        },
        "data_requirements": {
            "max_sample_period_s": 30
        }
    },
    "autoclave": {
        "spec": {
            "sterilization_temp_C": 121,
            "sterilization_time_s": 900,
            "min_pressure_bar": 2.0,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 30
        }
    },
    "coldchain": {
        "spec": {
            "min_temp_C": 2,
            "max_temp_C": 8,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 60
        }
    },
    "haccp": {
        "spec": {
            "temp_1_C": 135,
            "temp_2_C": 70,
            "temp_3_C": 41,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 30
        }
    },
    "concrete": {
        "spec": {
            "min_temp_C": 10,
            "max_temp_C": 30,
            "min_humidity": 80,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 300
        }
    },
    "sterile": {
        "spec": {
            "min_temp_C": 55,
            "max_temp_C": 60,
            "exposure_hours": 12,
            "method": "OVEN_AIR"
        },
        "data_requirements": {
            "max_sample_period_s": 60
        }
    }
}

# V2 format specifications
V2_SPECS = {
    "powder": {
        "industry": "powder",
        "parameters": {
            "target_temp": 180,
            "hold_duration_minutes": 10,
            "sensor_uncertainty": 2,
            "hysteresis": 2
        }
    },
    "autoclave": {
        "industry": "autoclave",
        "parameters": {
            "sterilization_temp": 121,
            "sterilization_time_minutes": 15,
            "min_pressure_bar": 2.0,
            "z_value": 10
        }
    },
    "coldchain": {
        "industry": "coldchain",
        "parameters": {
            "min_temp": 2,
            "max_temp": 8,
            "compliance_percentage": 95
        }
    },
    "haccp": {
        "industry": "haccp",
        "parameters": {
            "temp_1": 135,
            "temp_2": 70,
            "temp_3": 41,
            "time_1_to_2_hours": 2
        }
    },
    "concrete": {
        "industry": "concrete",
        "parameters": {
            "min_temp": 10,
            "max_temp": 30,
            "min_humidity": 80,
            "compliance_percentage": 95
        }
    },
    "sterile": {
        "industry": "sterile",
        "parameters": {
            "min_temp": 55,
            "max_temp": 60,
            "exposure_hours": 12,
            "min_humidity": 50
        }
    }
}

class RoutingVerifier:
    """Verifies v1/v2 API routing behavior against a running application."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.compile_url = f"{self.base_url}/api/compile/json"
        self.results = []
    
    def test_industry(self, industry: str) -> Dict[str, Any]:
        """Test both v1 and v2 formats for a specific industry."""
        print(f"\n=== Testing {industry.upper()} ===")
        
        results = {
            "industry": industry,
            "v1_test": self._test_v1_format(industry),
            "v2_test": self._test_v2_format(industry),
            "mixed_test": self._test_mixed_format(industry),
            "invalid_test": self._test_invalid_format(industry)
        }
        
        return results
    
    def _test_v1_format(self, industry: str) -> Dict[str, Any]:
        """Test v1 legacy format."""
        print(f"  Testing v1 format for {industry}...")
        
        spec = V1_SPECS[industry]
        csv_data = TEST_CSV_DATA[industry]
        
        try:
            response = requests.post(
                self.compile_url,
                files={"csv_file": ("test.csv", csv_data, "text/csv")},
                data={"spec_json": json.dumps(spec)},
                timeout=30
            )
            
            result = {
                "status_code": response.status_code,
                "success": response.status_code in [200, 400, 401, 402],
                "routing_error": False,
                "response_data": None
            }
            
            if response.status_code == 400:
                try:
                    data = response.json()
                    error_message = str(data).lower()
                    result["routing_error"] = "invalid specification format" in error_message
                    result["response_data"] = data
                except:
                    pass
            
            status = "✓ SUCCESS" if result["success"] and not result["routing_error"] else "✗ FAILED"
            print(f"    v1 format: {status} (HTTP {response.status_code})")
            
            return result
            
        except Exception as e:
            print(f"    v1 format: ✗ ERROR - {str(e)}")
            return {"status_code": None, "success": False, "routing_error": True, "error": str(e)}
    
    def _test_v2_format(self, industry: str) -> Dict[str, Any]:
        """Test v2 format."""
        print(f"  Testing v2 format for {industry}...")
        
        spec = V2_SPECS[industry]
        csv_data = TEST_CSV_DATA[industry]
        
        try:
            response = requests.post(
                self.compile_url,
                files={"csv_file": ("test.csv", csv_data, "text/csv")},
                data={"spec_json": json.dumps(spec)},
                timeout=30
            )
            
            result = {
                "status_code": response.status_code,
                "success": response.status_code in [200, 400, 401, 402],
                "routing_error": False,
                "response_data": None
            }
            
            if response.status_code == 400:
                try:
                    data = response.json()
                    error_message = str(data).lower()
                    result["routing_error"] = "invalid specification format" in error_message
                    result["response_data"] = data
                except:
                    pass
            
            status = "✓ SUCCESS" if result["success"] and not result["routing_error"] else "✗ FAILED"
            print(f"    v2 format: {status} (HTTP {response.status_code})")
            
            return result
            
        except Exception as e:
            print(f"    v2 format: ✗ ERROR - {str(e)}")
            return {"status_code": None, "success": False, "routing_error": True, "error": str(e)}
    
    def _test_mixed_format(self, industry: str) -> Dict[str, Any]:
        """Test mixed format (both v1 and v2 fields) - should prefer v2."""
        print(f"  Testing mixed format for {industry}...")
        
        # Create spec with both v1 and v2 fields
        mixed_spec = {
            "industry": industry,  # v2 field
            "parameters": V2_SPECS[industry]["parameters"],
            "spec": V1_SPECS[industry]["spec"],  # v1 field (should be ignored)
            "data_requirements": V1_SPECS[industry]["data_requirements"]
        }
        csv_data = TEST_CSV_DATA[industry]
        
        try:
            response = requests.post(
                self.compile_url,
                files={"csv_file": ("test.csv", csv_data, "text/csv")},
                data={"spec_json": json.dumps(mixed_spec)},
                timeout=30
            )
            
            result = {
                "status_code": response.status_code,
                "success": response.status_code in [200, 400, 401, 402],
                "routing_error": False,
                "response_data": None
            }
            
            if response.status_code == 400:
                try:
                    data = response.json()
                    error_message = str(data).lower()
                    result["routing_error"] = "invalid specification format" in error_message
                    result["response_data"] = data
                except:
                    pass
            
            status = "✓ SUCCESS" if result["success"] and not result["routing_error"] else "✗ FAILED"
            print(f"    mixed format: {status} (HTTP {response.status_code})")
            
            return result
            
        except Exception as e:
            print(f"    mixed format: ✗ ERROR - {str(e)}")
            return {"status_code": None, "success": False, "routing_error": True, "error": str(e)}
    
    def _test_invalid_format(self, industry: str) -> Dict[str, Any]:
        """Test invalid format - should return proper error."""
        print(f"  Testing invalid format for {industry}...")
        
        invalid_spec = {"invalid": "format", "random": "data"}
        csv_data = TEST_CSV_DATA[industry]
        
        try:
            response = requests.post(
                self.compile_url,
                files={"csv_file": ("test.csv", csv_data, "text/csv")},
                data={"spec_json": json.dumps(invalid_spec)},
                timeout=30
            )
            
            result = {
                "status_code": response.status_code,
                "success": response.status_code == 400,  # Should return 400 for invalid format
                "proper_error": False,
                "response_data": None
            }
            
            if response.status_code == 400:
                try:
                    data = response.json()
                    error_message = str(data).lower()
                    result["proper_error"] = any([
                        "invalid specification format" in error_message,
                        "include 'industry' field" in error_message,
                        "include 'spec' field" in error_message
                    ])
                    result["response_data"] = data
                except:
                    pass
            
            status = "✓ SUCCESS" if result["success"] and result["proper_error"] else "✗ FAILED"
            print(f"    invalid format: {status} (HTTP {response.status_code})")
            
            return result
            
        except Exception as e:
            print(f"    invalid format: ✗ ERROR - {str(e)}")
            return {"status_code": None, "success": False, "proper_error": False, "error": str(e)}
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run tests for all supported industries."""
        print(f"Testing v1/v2 API routing at: {self.base_url}")
        print("=" * 60)
        
        industries = ["powder", "autoclave", "coldchain", "haccp", "concrete", "sterile"]
        all_results = []
        
        for industry in industries:
            result = self.test_industry(industry)
            all_results.append(result)
            self.results.append(result)
        
        # Summary
        print(f"\n{'=' * 60}")
        print("SUMMARY REPORT")
        print("=" * 60)
        
        total_tests = len(industries) * 4  # 4 tests per industry
        passed_tests = 0
        
        for result in all_results:
            industry = result["industry"]
            v1_ok = result["v1_test"]["success"] and not result["v1_test"]["routing_error"]
            v2_ok = result["v2_test"]["success"] and not result["v2_test"]["routing_error"]
            mixed_ok = result["mixed_test"]["success"] and not result["mixed_test"]["routing_error"]
            invalid_ok = result["invalid_test"]["success"] and result["invalid_test"]["proper_error"]
            
            industry_passed = sum([v1_ok, v2_ok, mixed_ok, invalid_ok])
            passed_tests += industry_passed
            
            status = "✓" if industry_passed == 4 else "✗"
            print(f"{status} {industry.upper()}: {industry_passed}/4 tests passed")
        
        print(f"\nOVERALL: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All routing tests PASSED! v1/v2 routing is working correctly.")
            return {"status": "success", "results": all_results}
        else:
            print("❌ Some routing tests FAILED. Check the details above.")
            return {"status": "failure", "results": all_results}
    
    def run_single_industry(self, industry: str) -> Dict[str, Any]:
        """Run tests for a single industry."""
        if industry not in TEST_CSV_DATA:
            print(f"❌ Unknown industry: {industry}")
            print(f"Available industries: {', '.join(TEST_CSV_DATA.keys())}")
            return {"status": "error", "message": f"Unknown industry: {industry}"}
        
        print(f"Testing v1/v2 API routing for {industry} at: {self.base_url}")
        print("=" * 60)
        
        result = self.test_industry(industry)
        
        # Summary
        print(f"\n{'=' * 60}")
        print(f"SUMMARY for {industry.upper()}")
        print("=" * 60)
        
        v1_ok = result["v1_test"]["success"] and not result["v1_test"]["routing_error"]
        v2_ok = result["v2_test"]["success"] and not result["v2_test"]["routing_error"]
        mixed_ok = result["mixed_test"]["success"] and not result["mixed_test"]["routing_error"]
        invalid_ok = result["invalid_test"]["success"] and result["invalid_test"]["proper_error"]
        
        tests_passed = sum([v1_ok, v2_ok, mixed_ok, invalid_ok])
        
        print(f"Tests passed: {tests_passed}/4")
        
        if tests_passed == 4:
            print(f"🎉 All {industry} routing tests PASSED!")
            return {"status": "success", "industry": industry, "result": result}
        else:
            print(f"❌ Some {industry} routing tests FAILED.")
            return {"status": "failure", "industry": industry, "result": result}

def main():
    parser = argparse.ArgumentParser(description="Verify v1/v2 API routing")
    parser.add_argument("--host", default="http://localhost:8000", 
                       help="Base URL of the application (default: http://localhost:8000)")
    parser.add_argument("--industry", help="Test specific industry only")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Show detailed response data")
    
    args = parser.parse_args()
    
    verifier = RoutingVerifier(args.host)
    
    try:
        if args.industry:
            result = verifier.run_single_industry(args.industry)
        else:
            result = verifier.run_all_tests()
        
        # Exit with appropriate code
        if result["status"] == "success":
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()