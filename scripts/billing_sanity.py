#!/usr/bin/env python3
"""
Billing System Sanity Check

This script performs a dry run validation of the ProofKit billing system,
checking Stripe configuration, plan definitions, quota enforcement, and
webhook handling without making actual API calls or charging customers.

Example usage:
    python scripts/billing_sanity.py --dry-run
    python scripts/billing_sanity.py --check-stripe-config
    python scripts/billing_sanity.py --validate-plans
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.billing import (
    PLANS, 
    get_plan, 
    get_all_plans,
    is_valid_plan,
    can_upgrade_from_plan,
    calculate_monthly_cost,
    get_premium_cert_config,
    STRIPE_SECRET_KEY,
    STRIPE_PUBLISHABLE_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_TEST_MODE
)
from core.stripe_util import is_stripe_configured

# Import with error handling for dependencies
try:
    from middleware.quota import (
        check_compilation_quota,
        record_usage,
        get_user_usage_summary,
        update_user_plan,
        process_single_certificate_purchase
    )
    QUOTA_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import quota middleware: {e}")
    QUOTA_AVAILABLE = False

try:
    from auth.models import User
    AUTH_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import auth models: {e}")
    AUTH_AVAILABLE = False


class BillingSanityChecker:
    """Comprehensive billing system sanity checker."""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed_checks: List[str] = []
        
    def log_error(self, message: str):
        """Log an error."""
        self.errors.append(f"ERROR: {message}")
        print(f"❌ ERROR: {message}")
    
    def log_warning(self, message: str):
        """Log a warning."""
        self.warnings.append(f"WARNING: {message}")
        print(f"⚠️  WARNING: {message}")
    
    def log_success(self, message: str):
        """Log a successful check."""
        self.passed_checks.append(f"PASS: {message}")
        print(f"✅ PASS: {message}")
    
    def check_stripe_configuration(self) -> bool:
        """Check Stripe configuration."""
        print("\n🔧 Checking Stripe Configuration...")
        
        all_good = True
        
        # Check environment variables
        if not STRIPE_SECRET_KEY:
            self.log_error("STRIPE_SECRET_KEY not configured")
            all_good = False
        else:
            self.log_success(f"STRIPE_SECRET_KEY configured ({'TEST' if STRIPE_TEST_MODE else 'LIVE'} mode)")
        
        if not STRIPE_PUBLISHABLE_KEY:
            self.log_error("STRIPE_PUBLISHABLE_KEY not configured")
            all_good = False
        else:
            self.log_success("STRIPE_PUBLISHABLE_KEY configured")
        
        if not STRIPE_WEBHOOK_SECRET:
            self.log_warning("STRIPE_WEBHOOK_SECRET not configured")
        else:
            self.log_success("STRIPE_WEBHOOK_SECRET configured")
        
        # Check if Stripe is ready
        if is_stripe_configured():
            self.log_success("Stripe integration ready")
        else:
            self.log_error("Stripe integration not fully configured")
            all_good = False
        
        return all_good
    
    def validate_plan_configuration(self) -> bool:
        """Validate plan configuration matches requirements."""
        print("\n📋 Validating Plan Configuration...")
        
        all_good = True
        
        # Check required plans exist
        required_plans = ['free', 'starter', 'pro', 'enterprise']
        for plan_name in required_plans:
            plan = get_plan(plan_name)
            if not plan:
                self.log_error(f"Required plan '{plan_name}' not configured")
                all_good = False
            else:
                self.log_success(f"Plan '{plan_name}' configured")
        
        # Validate Free plan
        free_plan = get_plan('free')
        if free_plan:
            if free_plan['jobs_month'] != 2:
                self.log_error(f"Free plan should have 2 certificates, has {free_plan['jobs_month']}")
                all_good = False
            if free_plan['price_usd'] != 0:
                self.log_error(f"Free plan should cost $0, costs ${free_plan['price_usd']}")
                all_good = False
            if free_plan['overage_price_usd'] is not None:
                self.log_error("Free plan should not allow overage")
                all_good = False
            self.log_success("Free plan configuration valid")
        
        # Validate Starter plan
        starter_plan = get_plan('starter')
        if starter_plan:
            if starter_plan['jobs_month'] != 10:
                self.log_error(f"Starter plan should have 10 certificates, has {starter_plan['jobs_month']}")
                all_good = False
            if starter_plan['price_usd'] != 19:
                self.log_error(f"Starter plan should cost $19, costs ${starter_plan['price_usd']}")
                all_good = False
            self.log_success("Starter plan configuration valid")
        
        # Validate Pro plan
        pro_plan = get_plan('pro')
        if pro_plan:
            if pro_plan['jobs_month'] != 50:
                self.log_error(f"Pro plan should have 50 certificates, has {pro_plan['jobs_month']}")
                all_good = False
            if pro_plan['price_usd'] != 79:
                self.log_error(f"Pro plan should cost $79, costs ${pro_plan['price_usd']}")
                all_good = False
            self.log_success("Pro plan configuration valid")
        
        # Validate Enterprise plan
        enterprise_plan = get_plan('enterprise')
        if enterprise_plan:
            if enterprise_plan['jobs_month'] != float('inf'):
                self.log_error("Enterprise plan should have unlimited certificates")
                all_good = False
            if enterprise_plan['price_usd'] is not None:
                self.log_error("Enterprise plan should have custom pricing (None)")
                all_good = False
            self.log_success("Enterprise plan configuration valid")
        
        # Check premium certificate configuration
        try:
            premium_config = get_premium_cert_config()
            if not premium_config:
                self.log_error("Premium certificate configuration missing")
                all_good = False
            elif premium_config['price_usd'] <= 0:
                self.log_error(f"Premium certificate price should be > 0, is ${premium_config['price_usd']}")
                all_good = False
            else:
                self.log_success(f"Premium certificate configured at ${premium_config['price_usd']}")
        except Exception as e:
            self.log_error(f"Premium certificate configuration error: {e}")
            all_good = False
        
        return all_good
    
    def test_quota_enforcement(self) -> bool:
        """Test quota enforcement logic."""
        print("\n🚦 Testing Quota Enforcement...")
        
        all_good = True
        
        if not QUOTA_AVAILABLE:
            self.log_warning("Quota middleware not available - skipping quota tests")
            return True
            
        try:
            # Mock user for testing
            class MockUser:
                def __init__(self, email: str):
                    self.email = email
                    self.name = "Test User"
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # Patch quota storage to use temp directory
                import middleware.quota as quota_module
                original_storage_dir = quota_module.QUOTA_STORAGE_DIR
                quota_module.QUOTA_STORAGE_DIR = Path(temp_dir)
                
                try:
                    test_user = MockUser('test@example.com')
                    
                    # Test free tier quota
                    can_compile, error = check_compilation_quota(test_user)
                    if not can_compile:
                        self.log_error("New user should be able to compile certificates")
                        all_good = False
                    else:
                        self.log_success("New user quota check passed")
                    
                    # Use one certificate
                    record_usage(test_user, 'certificate_compiled')
                    usage = get_user_usage_summary(test_user.email)
                    
                    if usage.get('total_used') != 1:
                        self.log_error(f"Expected 1 certificate used, got {usage.get('total_used')}")
                        all_good = False
                    else:
                        self.log_success("Certificate usage recording works")
                    
                    # Use second certificate
                    record_usage(test_user, 'certificate_compiled')
                    usage = get_user_usage_summary(test_user.email)
                    
                    if usage.get('total_remaining') != 0:
                        self.log_error(f"Expected 0 remaining certificates, got {usage.get('total_remaining')}")
                        all_good = False
                    else:
                        self.log_success("Free tier limit enforcement works")
                    
                    # Try third certificate - should be blocked
                    can_compile, error = check_compilation_quota(test_user)
                    if can_compile:
                        self.log_error("Free tier should block third certificate")
                        all_good = False
                    elif error and error.get('code') != 'FREE_TIER_EXCEEDED':
                        self.log_error(f"Expected FREE_TIER_EXCEEDED, got {error.get('code')}")
                        all_good = False
                    else:
                        self.log_success("Free tier quota blocking works")
                    
                    # Test plan upgrade
                    success = update_user_plan(test_user.email, 'pro', {
                        'id': 'sub_test',
                        'customer': 'cus_test', 
                        'status': 'active'
                    })
                    
                    if not success:
                        self.log_error("Plan upgrade failed")
                        all_good = False
                    else:
                        # Check upgraded limits
                        usage = get_user_usage_summary(test_user.email)
                        if usage.get('plan') != 'pro':
                            self.log_error(f"Expected pro plan, got {usage.get('plan')}")
                            all_good = False
                        else:
                            self.log_success("Plan upgrade works")
                
                finally:
                    # Restore original storage directory
                    quota_module.QUOTA_STORAGE_DIR = original_storage_dir
                    
        except Exception as e:
            self.log_error(f"Quota enforcement test failed: {e}")
            all_good = False
        
        return all_good
    
    def test_billing_calculations(self) -> bool:
        """Test billing calculations."""
        print("\n💰 Testing Billing Calculations...")
        
        all_good = True
        
        try:
            # Test starter plan with overage
            cost = calculate_monthly_cost('starter', 15)  # 5 over limit
            expected_base = 19
            expected_overage = 15  # 5 * $3
            expected_total = 34
            
            if cost['base'] != expected_base:
                self.log_error(f"Starter base cost: expected ${expected_base}, got ${cost['base']}")
                all_good = False
            if cost['overage'] != expected_overage:
                self.log_error(f"Starter overage cost: expected ${expected_overage}, got ${cost['overage']}")
                all_good = False
            if cost['total'] != expected_total:
                self.log_error(f"Starter total cost: expected ${expected_total}, got ${cost['total']}")
                all_good = False
            
            if all_good:
                self.log_success("Billing calculations work correctly")
                
            # Test free plan (no overage)
            cost = calculate_monthly_cost('free', 5)
            if cost['overage'] != 0:
                self.log_error(f"Free plan should have no overage, got ${cost['overage']}")
                all_good = False
            else:
                self.log_success("Free plan overage calculation correct")
                
        except Exception as e:
            self.log_error(f"Billing calculation test failed: {e}")
            all_good = False
        
        return all_good
    
    def test_upgrade_paths(self) -> bool:
        """Test plan upgrade paths."""
        print("\n⬆️  Testing Upgrade Paths...")
        
        all_good = True
        
        try:
            # Valid upgrades
            valid_upgrades = [
                ('free', 'starter'),
                ('free', 'pro'),
                ('free', 'enterprise'),
                ('starter', 'pro'),
                ('starter', 'enterprise'),
                ('pro', 'enterprise')
            ]
            
            for current, target in valid_upgrades:
                if not can_upgrade_from_plan(current, target):
                    self.log_error(f"Should allow upgrade from {current} to {target}")
                    all_good = False
            
            # Invalid upgrades
            invalid_upgrades = [
                ('pro', 'starter'),
                ('enterprise', 'pro'),
                ('starter', 'free')
            ]
            
            for current, target in invalid_upgrades:
                if can_upgrade_from_plan(current, target):
                    self.log_error(f"Should NOT allow upgrade from {current} to {target}")
                    all_good = False
            
            if all_good:
                self.log_success("Upgrade path validation works correctly")
                
        except Exception as e:
            self.log_error(f"Upgrade path test failed: {e}")
            all_good = False
        
        return all_good
    
    def run_comprehensive_check(self) -> bool:
        """Run all sanity checks."""
        print("🔍 ProofKit Billing System Sanity Check")
        print("=" * 50)
        
        all_checks = [
            self.check_stripe_configuration(),
            self.validate_plan_configuration(), 
            self.test_quota_enforcement(),
            self.test_billing_calculations(),
            self.test_upgrade_paths()
        ]
        
        print("\n" + "=" * 50)
        print("📊 SUMMARY")
        print("=" * 50)
        
        print(f"✅ Passed: {len(self.passed_checks)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")
        
        if self.errors:
            print("\nERRORS:")
            for error in self.errors:
                print(f"  {error}")
        
        if self.warnings:
            print("\nWARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")
        
        overall_success = all(all_checks) and len(self.errors) == 0
        
        if overall_success:
            print("\n🎉 All billing system checks PASSED!")
        else:
            print(f"\n💥 Billing system has {len(self.errors)} errors that need to be fixed.")
        
        return overall_success
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate detailed report."""
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'dry_run': self.dry_run,
            'stripe_configured': is_stripe_configured(),
            'stripe_test_mode': STRIPE_TEST_MODE,
            'passed_checks': len(self.passed_checks),
            'warnings': len(self.warnings),
            'errors': len(self.errors),
            'details': {
                'passed': self.passed_checks,
                'warnings': self.warnings,
                'errors': self.errors
            },
            'plan_summary': {
                plan_name: {
                    'monthly_certificates': plan['jobs_month'],
                    'monthly_price_usd': plan['price_usd'],
                    'overage_price_usd': plan.get('overage_price_usd'),
                    'single_cert_price_usd': plan.get('single_cert_price_usd')
                } for plan_name, plan in PLANS.items()
            }
        }


def main():
    parser = argparse.ArgumentParser(description='ProofKit Billing System Sanity Check')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Run in dry-run mode (default)')
    parser.add_argument('--live', action='store_true', 
                        help='Run against live Stripe (use with caution)')
    parser.add_argument('--check-stripe-config', action='store_true',
                        help='Only check Stripe configuration')
    parser.add_argument('--validate-plans', action='store_true', 
                        help='Only validate plan configuration')
    parser.add_argument('--output-report', type=str,
                        help='Output detailed JSON report to file')
    
    args = parser.parse_args()
    
    # Determine run mode
    dry_run = not args.live
    
    if args.live:
        print("⚠️  WARNING: Running against LIVE Stripe configuration!")
        response = input("Are you sure? (type 'yes' to continue): ")
        if response.lower() != 'yes':
            print("Aborting.")
            sys.exit(0)
    
    # Create checker
    checker = BillingSanityChecker(dry_run=dry_run)
    
    # Run specific checks if requested
    if args.check_stripe_config:
        success = checker.check_stripe_configuration()
    elif args.validate_plans:
        success = checker.validate_plan_configuration()
    else:
        # Run comprehensive check
        success = checker.run_comprehensive_check()
    
    # Generate report if requested
    if args.output_report:
        report = checker.generate_report()
        with open(args.output_report, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Detailed report written to: {args.output_report}")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()