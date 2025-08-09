#!/usr/bin/env python3
"""
Live smoke tests against production environment.

Validates that critical endpoints are working, industry pages load correctly,
and API presets are available. These tests run against the live production
environment to catch issues that might not appear in unit/integration tests.

Usage:
    python -m tests.smoke.test_live_smoke --base-url https://proofkit.net --output-json results.json
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class LiveSmokeTestRunner:
    """Runs live smoke tests against production environment."""
    
    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.results: List[Dict[str, Any]] = []
        
        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            'User-Agent': 'ProofKit-LiveSmoke/1.0'
        })

    def test_health_endpoint(self) -> Dict[str, Any]:
        """Test health endpoint availability and response format."""
        test_name = "health_endpoint"
        start_time = time.time()
        
        try:
            response = self.session.get(
                urljoin(self.base_url, '/health'),
                timeout=self.timeout
            )
            duration = time.time() - start_time
            
            if response.status_code != 200:
                return {
                    'test': test_name,
                    'status': 'FAIL',
                    'error': f'HTTP {response.status_code}',
                    'duration': duration
                }
            
            # Validate JSON structure
            try:
                data = response.json()
                if not isinstance(data, dict) or 'status' not in data:
                    return {
                        'test': test_name,
                        'status': 'FAIL',
                        'error': 'Invalid JSON structure',
                        'duration': duration
                    }
            except json.JSONDecodeError:
                return {
                    'test': test_name,
                    'status': 'FAIL',
                    'error': 'Invalid JSON response',
                    'duration': duration
                }
            
            return {
                'test': test_name,
                'status': 'PASS',
                'duration': duration,
                'response_time': duration,
                'details': {
                    'status_code': response.status_code,
                    'response_size': len(response.content),
                    'has_status_field': 'status' in data
                }
            }
            
        except Exception as e:
            duration = time.time() - start_time
            return {
                'test': test_name,
                'status': 'FAIL',
                'error': str(e),
                'duration': duration
            }

    def test_home_page(self) -> Dict[str, Any]:
        """Test home page loads and contains expected content."""
        test_name = "home_page"
        start_time = time.time()
        
        try:
            response = self.session.get(
                self.base_url,
                timeout=self.timeout
            )
            duration = time.time() - start_time
            
            if response.status_code != 200:
                return {
                    'test': test_name,
                    'status': 'FAIL',
                    'error': f'HTTP {response.status_code}',
                    'duration': duration
                }
            
            content = response.text.lower()
            has_proofkit = 'proofkit' in content
            has_html = '</html>' in content
            has_form = 'csv' in content and ('file' in content or 'upload' in content)
            
            return {
                'test': test_name,
                'status': 'PASS',
                'duration': duration,
                'details': {
                    'status_code': response.status_code,
                    'content_length': len(response.text),
                    'has_proofkit_branding': has_proofkit,
                    'has_complete_html': has_html,
                    'has_upload_form': has_form
                }
            }
            
        except Exception as e:
            duration = time.time() - start_time
            return {
                'test': test_name,
                'status': 'FAIL',
                'error': str(e),
                'duration': duration
            }

    def test_api_presets(self) -> Dict[str, Any]:
        """Test API presets endpoint returns valid industry configurations."""
        test_name = "api_presets"
        start_time = time.time()
        
        try:
            response = self.session.get(
                urljoin(self.base_url, '/api/presets'),
                headers={'Accept': 'application/json'},
                timeout=self.timeout
            )
            duration = time.time() - start_time
            
            if response.status_code != 200:
                return {
                    'test': test_name,
                    'status': 'FAIL',
                    'error': f'HTTP {response.status_code}',
                    'duration': duration
                }
            
            try:
                presets = response.json()
                if not isinstance(presets, dict):
                    return {
                        'test': test_name,
                        'status': 'FAIL',
                        'error': 'Invalid presets format - not a dictionary',
                        'duration': duration
                    }
                
                preset_count = len(presets)
                expected_industries = {'powder', 'haccp', 'autoclave', 'sterile', 'concrete', 'coldchain'}
                available_industries = set(presets.keys())
                missing_industries = expected_industries - available_industries
                
                # Check each preset has required structure
                invalid_presets = []
                for industry, preset in presets.items():
                    if not isinstance(preset, dict) or 'spec' not in preset:
                        invalid_presets.append(industry)
                
                if preset_count < 5:
                    return {
                        'test': test_name,
                        'status': 'FAIL',
                        'error': f'Insufficient presets: {preset_count} (expected ≥5)',
                        'duration': duration
                    }
                
                if invalid_presets:
                    return {
                        'test': test_name,
                        'status': 'FAIL',
                        'error': f'Invalid presets: {invalid_presets}',
                        'duration': duration
                    }
                
                return {
                    'test': test_name,
                    'status': 'PASS',
                    'duration': duration,
                    'details': {
                        'preset_count': preset_count,
                        'available_industries': list(available_industries),
                        'missing_industries': list(missing_industries),
                        'response_time': duration
                    }
                }
                
            except json.JSONDecodeError:
                return {
                    'test': test_name,
                    'status': 'FAIL',
                    'error': 'Invalid JSON response',
                    'duration': duration
                }
                
        except Exception as e:
            duration = time.time() - start_time
            return {
                'test': test_name,
                'status': 'FAIL',
                'error': str(e),
                'duration': duration
            }

    def test_industry_pages(self) -> Dict[str, Any]:
        """Test industry-specific pages load correctly."""
        test_name = "industry_pages"
        start_time = time.time()
        
        industries = ['powder', 'autoclave', 'coldchain', 'haccp', 'concrete', 'sterile']
        results = {}
        total_errors = 0
        
        for industry in industries:
            try:
                response = self.session.get(
                    urljoin(self.base_url, f'/industries/{industry}'),
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    results[industry] = {
                        'status': 'PASS',
                        'response_time': response.elapsed.total_seconds(),
                        'content_length': len(response.text)
                    }
                else:
                    results[industry] = {
                        'status': 'FAIL',
                        'error': f'HTTP {response.status_code}'
                    }
                    total_errors += 1
                    
            except Exception as e:
                results[industry] = {
                    'status': 'FAIL',
                    'error': str(e)
                }
                total_errors += 1
        
        duration = time.time() - start_time
        overall_status = 'PASS' if total_errors == 0 else 'FAIL'
        
        return {
            'test': test_name,
            'status': overall_status,
            'duration': duration,
            'details': {
                'total_industries': len(industries),
                'passed': len(industries) - total_errors,
                'failed': total_errors,
                'results': results
            }
        }

    def test_examples_page(self) -> Dict[str, Any]:
        """Test examples page loads successfully."""
        test_name = "examples_page"
        start_time = time.time()
        
        try:
            response = self.session.get(
                urljoin(self.base_url, '/examples'),
                timeout=self.timeout
            )
            duration = time.time() - start_time
            
            if response.status_code != 200:
                return {
                    'test': test_name,
                    'status': 'FAIL',
                    'error': f'HTTP {response.status_code}',
                    'duration': duration
                }
            
            content = response.text.lower()
            has_examples = 'example' in content
            has_industries = any(industry in content for industry in 
                               ['powder', 'autoclave', 'coldchain', 'haccp', 'concrete', 'sterile'])
            
            return {
                'test': test_name,
                'status': 'PASS',
                'duration': duration,
                'details': {
                    'status_code': response.status_code,
                    'content_length': len(response.text),
                    'has_examples': has_examples,
                    'has_industries': has_industries
                }
            }
            
        except Exception as e:
            duration = time.time() - start_time
            return {
                'test': test_name,
                'status': 'FAIL',
                'error': str(e),
                'duration': duration
            }

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all smoke tests and return comprehensive results."""
        print(f"Running live smoke tests against {self.base_url}")
        start_time = time.time()
        
        tests = [
            self.test_health_endpoint,
            self.test_home_page,
            self.test_api_presets,
            self.test_industry_pages,
            self.test_examples_page
        ]
        
        results = []
        passed = 0
        failed = 0
        
        for test_func in tests:
            print(f"Running {test_func.__name__}...", end=' ')
            result = test_func()
            results.append(result)
            
            if result['status'] == 'PASS':
                print("✅ PASS")
                passed += 1
            else:
                print(f"❌ FAIL - {result.get('error', 'Unknown error')}")
                failed += 1
        
        total_duration = time.time() - start_time
        
        summary = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'base_url': self.base_url,
            'total_tests': len(tests),
            'passed': passed,
            'failed': failed,
            'success_rate': (passed / len(tests)) * 100 if tests else 0,
            'total_duration': total_duration,
            'overall_status': 'PASS' if failed == 0 else 'FAIL'
        }
        
        return {
            'summary': summary,
            'results': results
        }


def main():
    """Main entry point for live smoke tests."""
    parser = argparse.ArgumentParser(description='Run live smoke tests')
    parser.add_argument('--base-url', required=True, help='Base URL of the application')
    parser.add_argument('--output-json', help='Output file for JSON results')
    parser.add_argument('--timeout', type=float, default=15.0, help='Request timeout in seconds')
    
    args = parser.parse_args()
    
    runner = LiveSmokeTestRunner(args.base_url, args.timeout)
    test_results = runner.run_all_tests()
    
    # Print summary
    summary = test_results['summary']
    print(f"\n=== LIVE SMOKE TEST SUMMARY ===")
    print(f"Environment: {summary['base_url']}")
    print(f"Tests: {summary['passed']}/{summary['total_tests']} passed")
    print(f"Success Rate: {summary['success_rate']:.1f}%")
    print(f"Duration: {summary['total_duration']:.2f}s")
    print(f"Overall Status: {summary['overall_status']}")
    
    # Save results to file if requested
    if args.output_json:
        with open(args.output_json, 'w') as f:
            json.dump(test_results, f, indent=2)
        print(f"Results saved to {args.output_json}")
    
    # Exit with appropriate code
    sys.exit(0 if summary['overall_status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()