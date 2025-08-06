"""
Tests for Quota and Plan Enforcement

This module tests the quota enforcement logic for different pricing tiers,
including free tier limits, monthly quotas, and overage billing.

Example usage:
    pytest tests/test_quota_plan.py -v
    pytest tests/test_quota_plan.py::test_free_tier_limit -v
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from middleware.quota import (
    check_compilation_quota,
    record_usage,
    load_user_quota_data,
    save_user_quota_data,
    update_user_plan,
    get_user_usage_summary,
    process_single_certificate_purchase,
    QUOTA_STORAGE_DIR
)
from core.billing import get_plan
from auth.models import User, UserRole


@pytest.fixture
def temp_quota_storage():
    """Create temporary quota storage directory for testing."""
    temp_dir = tempfile.mkdtemp()
    original_storage_dir = str(QUOTA_STORAGE_DIR)
    
    # Replace global storage directory for tests
    import middleware.quota
    middleware.quota.QUOTA_STORAGE_DIR = Path(temp_dir)
    
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    middleware.quota.QUOTA_STORAGE_DIR = Path(original_storage_dir)


@pytest.fixture
def test_user():
    """Create test user."""
    return User(email="test@example.com", role=UserRole.OPERATOR)


@pytest.fixture
def free_user():
    """Create free tier user."""
    return User(email="free@example.com", role=UserRole.OPERATOR)


@pytest.fixture
def starter_user():
    """Create starter tier user.""" 
    return User(email="starter@example.com", role=UserRole.OPERATOR)


class TestQuotaEnforcement:
    """Test quota enforcement logic."""
    
    def test_free_tier_initial_quota(self, temp_quota_storage, free_user):
        """Test that free tier users start with 0 usage."""
        quota_data = load_user_quota_data(free_user.email)
        
        assert quota_data['plan'] == 'free'
        assert quota_data['total_certificates'] == 0
        assert quota_data['current_month']['certificates_compiled'] == 0
    
    def test_free_tier_within_limit(self, temp_quota_storage, free_user):
        """Test that free tier allows first certificate."""
        can_compile, error = check_compilation_quota(free_user)
        
        assert can_compile is True
        assert error is None
    
    def test_free_tier_at_limit(self, temp_quota_storage, free_user):
        """Test that free tier allows second certificate."""
        # Use one certificate
        record_usage(free_user, 'certificate_compiled')
        
        can_compile, error = check_compilation_quota(free_user)
        
        assert can_compile is True
        assert error is None
    
    def test_free_tier_exceeds_limit(self, temp_quota_storage, free_user):
        """Test that free tier blocks third certificate with upgrade options."""
        # Use both free certificates
        record_usage(free_user, 'certificate_compiled')
        record_usage(free_user, 'certificate_compiled')
        
        with patch('middleware.quota.create_oneoff_checkout') as mock_checkout:
            mock_checkout.return_value = {'url': 'https://checkout.stripe.com/test'}
            
            can_compile, error = check_compilation_quota(free_user)
        
        assert can_compile is False
        assert error is not None
        assert error['code'] == 'FREE_TIER_EXCEEDED'
        assert error['total_used'] == 2
        assert error['limit'] == 2
        assert 'upgrade_options' in error
        assert 'single_purchase' in error
    
    def test_starter_tier_within_quota(self, temp_quota_storage, starter_user):
        """Test that starter tier allows compilation within monthly quota."""
        # Set user to starter plan
        update_user_plan(starter_user.email, 'starter')
        
        # Use 5 certificates (within 10 limit)
        for _ in range(5):
            record_usage(starter_user, 'certificate_compiled')
        
        can_compile, error = check_compilation_quota(starter_user)
        
        assert can_compile is True
        assert error is None
    
    def test_starter_tier_with_overage(self, temp_quota_storage, starter_user):
        """Test that starter tier allows overage compilation."""
        # Set user to starter plan
        update_user_plan(starter_user.email, 'starter')
        
        # Use 10 certificates (at limit)
        for _ in range(10):
            record_usage(starter_user, 'certificate_compiled')
        
        # Should still allow compilation due to overage billing
        can_compile, error = check_compilation_quota(starter_user)
        
        assert can_compile is True
        assert error is None
    
    def test_enterprise_tier_unlimited(self, temp_quota_storage, test_user):
        """Test that enterprise tier has unlimited usage."""
        # Set user to enterprise plan
        update_user_plan(test_user.email, 'enterprise')
        
        # Use many certificates
        for _ in range(1000):
            record_usage(test_user, 'certificate_compiled')
        
        can_compile, error = check_compilation_quota(test_user)
        
        assert can_compile is True
        assert error is None
    
    def test_anonymous_user_unlimited(self, temp_quota_storage):
        """Test that anonymous users have unlimited access for now."""
        can_compile, error = check_compilation_quota(None)
        
        assert can_compile is True
        assert error is None


class TestUsageRecording:
    """Test usage recording and tracking."""
    
    def test_record_certificate_usage(self, temp_quota_storage, test_user):
        """Test recording certificate compilation usage."""
        # Record usage
        success = record_usage(test_user, 'certificate_compiled')
        assert success is True
        
        # Check quota data
        quota_data = load_user_quota_data(test_user.email)
        assert quota_data['current_month']['certificates_compiled'] == 1
        assert quota_data['total_certificates'] == 1  # Free tier tracks total
    
    def test_record_multiple_usage(self, temp_quota_storage, test_user):
        """Test recording multiple certificate compilations."""
        # Record multiple usage
        for _ in range(5):
            record_usage(test_user, 'certificate_compiled')
        
        # Check quota data
        quota_data = load_user_quota_data(test_user.email)
        assert quota_data['current_month']['certificates_compiled'] == 5
        assert quota_data['total_certificates'] == 5
    
    def test_overage_tracking(self, temp_quota_storage, starter_user):
        """Test that overage usage is tracked for paid plans."""
        # Set user to starter plan
        update_user_plan(starter_user.email, 'starter')
        
        # Use 12 certificates (2 over limit)
        for _ in range(12):
            record_usage(starter_user, 'certificate_compiled')
        
        quota_data = load_user_quota_data(starter_user.email)
        assert quota_data['current_month']['certificates_compiled'] == 12
        assert quota_data['current_month']['overage_used'] == 2


class TestPlanManagement:
    """Test plan updates and management."""
    
    def test_update_user_plan(self, temp_quota_storage, test_user):
        """Test updating user's plan."""
        subscription_data = {
            'id': 'sub_test123',
            'customer': 'cus_test123',
            'status': 'active',
            'current_period_end': 1234567890
        }
        
        success = update_user_plan(test_user.email, 'pro', subscription_data)
        assert success is True
        
        quota_data = load_user_quota_data(test_user.email)
        assert quota_data['plan'] == 'pro'
        assert quota_data['subscription']['stripe_subscription_id'] == 'sub_test123'
        assert quota_data['subscription']['active'] is True
    
    def test_single_certificate_purchase(self, temp_quota_storage, test_user):
        """Test processing single certificate purchase."""
        success = process_single_certificate_purchase(test_user.email, 3)
        assert success is True
        
        quota_data = load_user_quota_data(test_user.email)
        assert quota_data['current_month']['single_certs_purchased'] == 3


class TestUsageSummary:
    """Test usage summary generation."""
    
    def test_free_tier_usage_summary(self, temp_quota_storage, free_user):
        """Test usage summary for free tier user."""
        # Use one certificate
        record_usage(free_user, 'certificate_compiled')
        
        summary = get_user_usage_summary(free_user.email)
        
        assert summary['plan'] == 'free'
        assert summary['total_used'] == 1
        assert summary['total_limit'] == 2
        assert summary['total_remaining'] == 1
        assert summary['is_unlimited'] is False
        assert summary['overage_available'] is False
    
    def test_starter_tier_usage_summary(self, temp_quota_storage, starter_user):
        """Test usage summary for starter tier user."""
        # Set user to starter plan and use 7 certificates
        update_user_plan(starter_user.email, 'starter')
        for _ in range(7):
            record_usage(starter_user, 'certificate_compiled')
        
        summary = get_user_usage_summary(starter_user.email)
        
        assert summary['plan'] == 'starter'
        assert summary['monthly_used'] == 7
        assert summary['monthly_limit'] == 10
        assert summary['monthly_remaining'] == 3
        assert summary['overage_used'] == 0
        assert summary['overage_price'] == 3.0
        assert summary['overage_available'] is True
    
    def test_overage_usage_summary(self, temp_quota_storage, starter_user):
        """Test usage summary with overage usage."""
        # Set user to starter plan and use 13 certificates
        update_user_plan(starter_user.email, 'starter')
        for _ in range(13):
            record_usage(starter_user, 'certificate_compiled')
        
        summary = get_user_usage_summary(starter_user.email)
        
        assert summary['plan'] == 'starter'
        assert summary['monthly_used'] == 13
        assert summary['monthly_limit'] == 10
        assert summary['monthly_remaining'] == 0
        assert summary['overage_used'] == 3


class TestMonthlyReset:
    """Test monthly quota reset functionality."""
    
    @patch('middleware.quota.datetime')
    def test_monthly_reset(self, mock_datetime, temp_quota_storage, test_user):
        """Test that monthly counters reset in new month."""
        # Mock current date as January
        mock_datetime.now.return_value.strftime.return_value = '2024-01'
        mock_datetime.now.return_value.isoformat.return_value = '2024-01-15T00:00:00'
        
        # Use some certificates in January
        record_usage(test_user, 'certificate_compiled')
        record_usage(test_user, 'certificate_compiled')
        
        quota_data = load_user_quota_data(test_user.email)
        assert quota_data['current_month']['certificates_compiled'] == 2
        assert quota_data['current_month']['month'] == '2024-01'
        
        # Mock date change to February
        mock_datetime.now.return_value.strftime.return_value = '2024-02'
        mock_datetime.now.return_value.isoformat.return_value = '2024-02-01T00:00:00'
        
        # Load quota data again - should reset monthly counters
        quota_data = load_user_quota_data(test_user.email)
        assert quota_data['current_month']['certificates_compiled'] == 0
        assert quota_data['current_month']['month'] == '2024-02'
        assert quota_data['total_certificates'] == 2  # Total should persist


class TestErrorHandling:
    """Test error handling in quota system."""
    
    def test_invalid_plan_handling(self, temp_quota_storage, test_user):
        """Test handling of invalid plan configurations."""
        # Corrupt quota data with invalid plan
        quota_data = load_user_quota_data(test_user.email)
        quota_data['plan'] = 'invalid_plan'
        save_user_quota_data(test_user.email, quota_data)
        
        can_compile, error = check_compilation_quota(test_user)
        
        assert can_compile is False
        assert error is not None
        assert error['code'] == 'INVALID_PLAN'
    
    def test_missing_quota_file_recovery(self, temp_quota_storage, test_user):
        """Test recovery when quota file is missing."""
        # Ensure quota file doesn't exist initially
        quota_file = temp_quota_storage / "nonexistent"
        
        # Should create new quota data
        quota_data = load_user_quota_data(test_user.email)
        
        assert quota_data['plan'] == 'free'
        assert quota_data['total_certificates'] == 0


# Integration tests
class TestQuotaIntegration:
    """Test integration with billing and Stripe systems."""
    
    @patch('middleware.quota.create_oneoff_checkout')
    def test_free_tier_upgrade_offer(self, mock_checkout, temp_quota_storage, free_user):
        """Test that free tier users get upgrade offers when limit exceeded."""
        mock_checkout.return_value = {
            'url': 'https://checkout.stripe.com/test123'
        }
        
        # Exceed free tier limit
        record_usage(free_user, 'certificate_compiled')
        record_usage(free_user, 'certificate_compiled')
        
        can_compile, error = check_compilation_quota(free_user)
        
        assert can_compile is False
        assert error['code'] == 'FREE_TIER_EXCEEDED'
        assert 'upgrade_options' in error
        assert error['upgrade_options']['starter_plan']['upgrade_url'] == '/api/upgrade/starter'
        assert error['single_purchase']['checkout_url'] == 'https://checkout.stripe.com/test123'
        
        # Verify checkout was called with correct parameters
        mock_checkout.assert_called_once_with(
            user_plan='free',
            user_email=free_user.email,
            certificate_count=1
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])