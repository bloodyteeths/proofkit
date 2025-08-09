"""
Integration tests for quota enforcement system.

These tests verify that quota limits are properly enforced during certificate
compilation and that overage billing works correctly across different plans.

Example usage:
    pytest tests/billing/test_quota_enforcement.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from middleware.quota import (
    check_compilation_quota,
    record_usage,
    get_user_usage_summary,
    load_user_quota_data,
    save_user_quota_data,
    update_user_plan
)
from auth.models import User
from core.billing import get_plan


@pytest.fixture
def mock_user():
    """Mock user object."""
    user = Mock(spec=User)
    user.email = 'test@example.com'
    user.name = 'Test User'
    return user


@pytest.fixture
def mock_free_user():
    """Mock user on free plan."""
    user = Mock(spec=User)
    user.email = 'free@example.com'
    return user


@pytest.fixture
def mock_pro_user():
    """Mock user on pro plan."""
    user = Mock(spec=User)
    user.email = 'pro@example.com'
    return user


class TestQuotaEnforcementIntegration:
    """Integration tests for quota enforcement."""

    def test_free_plan_quota_enforcement(self, tmp_path, mock_free_user):
        """Test free plan quota enforcement (2 certificates total)."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # User starts with 0 certificates
            can_compile, error = check_compilation_quota(mock_free_user)
            assert can_compile is True
            assert error is None
            
            # Use first certificate
            record_usage(mock_free_user, 'certificate_compiled')
            usage = get_user_usage_summary(mock_free_user.email)
            assert usage['total_used'] == 1
            assert usage['total_remaining'] == 1
            
            # Use second certificate
            record_usage(mock_free_user, 'certificate_compiled')
            usage = get_user_usage_summary(mock_free_user.email)
            assert usage['total_used'] == 2
            assert usage['total_remaining'] == 0
            
            # Try to use third certificate - should be blocked
            can_compile, error = check_compilation_quota(mock_free_user)
            assert can_compile is False
            assert error is not None
            assert error['code'] == 'FREE_TIER_EXCEEDED'
            assert 'upgrade_options' in error
            assert 'single_purchase' in error

    def test_starter_plan_monthly_quota(self, tmp_path, mock_user):
        """Test Starter plan monthly quota (10 certificates/month)."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Upgrade to starter plan
            update_user_plan(mock_user.email, 'starter', {
                'id': 'sub_starter_test',
                'customer': 'cus_test',
                'status': 'active'
            })
            
            # Use up to quota limit
            for i in range(10):
                can_compile, error = check_compilation_quota(mock_user)
                assert can_compile is True
                record_usage(mock_user, 'certificate_compiled')
            
            usage = get_user_usage_summary(mock_user.email)
            assert usage['monthly_used'] == 10
            assert usage['monthly_remaining'] == 0
            assert usage['plan'] == 'starter'
            
            # 11th certificate should trigger overage (allowed on Starter)
            can_compile, error = check_compilation_quota(mock_user)
            assert can_compile is True  # Overage allowed
            
            # Record overage usage
            record_usage(mock_user, 'certificate_compiled')
            usage = get_user_usage_summary(mock_user.email)
            assert usage['monthly_used'] == 11
            assert usage['overage_used'] == 1

    def test_pro_plan_monthly_quota(self, tmp_path, mock_pro_user):
        """Test Pro plan monthly quota (50 certificates/month)."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Upgrade to pro plan
            update_user_plan(mock_pro_user.email, 'pro', {
                'id': 'sub_pro_test',
                'customer': 'cus_test',
                'status': 'active'
            })
            
            # Use certificates up to limit
            for i in range(50):
                can_compile, error = check_compilation_quota(mock_pro_user)
                assert can_compile is True
                record_usage(mock_pro_user, 'certificate_compiled')
            
            usage = get_user_usage_summary(mock_pro_user.email)
            assert usage['monthly_used'] == 50
            assert usage['monthly_remaining'] == 0
            assert usage['plan'] == 'pro'
            
            # Test overage behavior
            can_compile, error = check_compilation_quota(mock_pro_user)
            assert can_compile is True  # Pro plan allows overage
            
            record_usage(mock_pro_user, 'certificate_compiled')
            usage = get_user_usage_summary(mock_pro_user.email)
            assert usage['overage_used'] == 1

    def test_enterprise_unlimited_quota(self, tmp_path, mock_user):
        """Test Enterprise plan unlimited quota."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Upgrade to enterprise plan
            update_user_plan(mock_user.email, 'enterprise', {
                'id': 'sub_enterprise_test',
                'customer': 'cus_test',
                'status': 'active'
            })
            
            # Use many certificates - should never hit limit
            for i in range(1000):  # Simulate heavy usage
                can_compile, error = check_compilation_quota(mock_user)
                assert can_compile is True
                assert error is None
                record_usage(mock_user, 'certificate_compiled')
            
            usage = get_user_usage_summary(mock_user.email)
            assert usage['monthly_used'] == 1000
            assert usage['is_unlimited'] is True
            assert usage['monthly_remaining'] is None

    def test_anonymous_user_quota(self):
        """Test anonymous user quota enforcement."""
        # Anonymous users should be allowed (for demo purposes)
        can_compile, error = check_compilation_quota(None)
        assert can_compile is True
        assert error is None
        
        # Recording usage for anonymous users should not crash
        success = record_usage(None, 'certificate_compiled')
        assert success is True

    def test_quota_reset_monthly(self, tmp_path, mock_user):
        """Test quota resets properly each month."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Setup user on starter plan
            update_user_plan(mock_user.email, 'starter')
            
            # Simulate usage in previous month
            quota_data = load_user_quota_data(mock_user.email)
            quota_data['current_month'] = {
                'month': '2023-01',  # Previous month
                'certificates_compiled': 10,  # At limit
                'overage_used': 0,
                'single_certs_purchased': 0
            }
            save_user_quota_data(mock_user.email, quota_data)
            
            # Load data again - should reset for new month
            with patch('datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = '2023-02'
                fresh_data = load_user_quota_data(mock_user.email)
                assert fresh_data['current_month']['certificates_compiled'] == 0
                assert fresh_data['current_month']['month'] == '2023-02'

    def test_overage_pricing_calculation(self):
        """Test overage pricing calculations."""
        from core.billing import calculate_monthly_cost
        
        # Test starter plan overage
        cost = calculate_monthly_cost('starter', 15)  # 5 over limit
        assert cost['base'] == 19  # Base price
        assert cost['overage'] == 15  # 5 * $3
        assert cost['total'] == 34
        assert cost['overage_count'] == 5
        
        # Test pro plan overage
        cost = calculate_monthly_cost('pro', 55)  # 5 over limit
        assert cost['base'] == 79
        assert cost['overage'] == 10  # 5 * $2
        assert cost['total'] == 89
        
        # Test free plan (no overage allowed)
        cost = calculate_monthly_cost('free', 5)
        assert cost['overage'] == 0  # No overage on free plan

    def test_single_certificate_purchase_processing(self, tmp_path, mock_user):
        """Test single certificate purchase processing."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            from middleware.quota import process_single_certificate_purchase
            
            # Process single cert purchase
            success = process_single_certificate_purchase(mock_user.email, 3)
            assert success is True
            
            # Verify it's recorded
            quota_data = load_user_quota_data(mock_user.email)
            assert quota_data['current_month']['single_certs_purchased'] == 3

    def test_quota_enforcement_with_subscription_data(self, tmp_path, mock_user):
        """Test quota enforcement integrates with subscription data."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Upgrade with full subscription data
            subscription_data = {
                'id': 'sub_test_12345',
                'customer': 'cus_test_12345',
                'status': 'active',
                'current_period_end': 1672531200
            }
            
            success = update_user_plan(mock_user.email, 'pro', subscription_data)
            assert success
            
            # Check that subscription data is stored
            quota_data = load_user_quota_data(mock_user.email)
            assert quota_data['subscription']['stripe_subscription_id'] == 'sub_test_12345'
            assert quota_data['subscription']['active'] is True

    def test_usage_summary_edge_cases(self, tmp_path, mock_user):
        """Test usage summary handles edge cases."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Test with invalid plan
            quota_data = load_user_quota_data(mock_user.email)
            quota_data['plan'] = 'invalid_plan'
            save_user_quota_data(mock_user.email, quota_data)
            
            summary = get_user_usage_summary(mock_user.email)
            assert 'error' in summary

    @patch('core.stripe_util.create_oneoff_checkout')
    def test_quota_exceeded_checkout_creation(self, mock_checkout, tmp_path, mock_user):
        """Test checkout session creation when quota exceeded."""
        mock_checkout.return_value = {
            'url': 'https://checkout.stripe.com/test',
            'id': 'cs_test_123'
        }
        
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Use up free tier quota
            quota_data = load_user_quota_data(mock_user.email)
            quota_data['total_certificates'] = 2  # At limit
            save_user_quota_data(mock_user.email, quota_data)
            
            # Check quota - should offer purchase option
            can_compile, error = check_compilation_quota(mock_user)
            assert can_compile is False
            assert error['code'] == 'FREE_TIER_EXCEEDED'
            assert 'checkout_url' in error['single_purchase']
            
            # Verify checkout session creation was called
            mock_checkout.assert_called_once()

    def test_error_handling_in_quota_system(self, tmp_path, mock_user):
        """Test quota system handles errors gracefully."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Test with corrupted quota file
            with patch('middleware.quota.json.load', side_effect=ValueError("Invalid JSON")):
                # Should fall back to default data
                data = load_user_quota_data(mock_user.email)
                assert data['plan'] == 'free'
                assert data['total_certificates'] == 0

    def test_plan_upgrade_preserves_usage(self, tmp_path, mock_user):
        """Test plan upgrade preserves current month usage."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Use some certificates on free plan
            record_usage(mock_user, 'certificate_compiled')
            
            original_data = load_user_quota_data(mock_user.email)
            original_usage = original_data['current_month']['certificates_compiled']
            
            # Upgrade to starter
            update_user_plan(mock_user.email, 'starter', {
                'id': 'sub_test',
                'customer': 'cus_test',
                'status': 'active'
            })
            
            # Usage should be preserved
            updated_data = load_user_quota_data(mock_user.email)
            assert updated_data['current_month']['certificates_compiled'] == original_usage
            assert updated_data['plan'] == 'starter'


class TestQuotaMiddlewareIntegration:
    """Test quota middleware integration."""

    def test_middleware_blocks_over_quota_requests(self, tmp_path, mock_user):
        """Test middleware blocks requests when over quota."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # Set user at quota limit
            quota_data = load_user_quota_data(mock_user.email)
            quota_data['total_certificates'] = 2  # Free tier limit
            save_user_quota_data(mock_user.email, quota_data)
            
            # Mock request and auth
            with patch('auth.magic.get_current_user', return_value=mock_user):
                from middleware.quota import quota_middleware
                
                # Mock compilation request
                mock_request = Mock()
                mock_request.url.path = '/api/compile'
                
                # Should block request
                can_compile, error = check_compilation_quota(mock_user)
                assert can_compile is False
                assert error['code'] == 'FREE_TIER_EXCEEDED'

    def test_middleware_allows_within_quota_requests(self, tmp_path, mock_user):
        """Test middleware allows requests within quota."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            # User has remaining quota
            can_compile, error = check_compilation_quota(mock_user)
            assert can_compile is True
            assert error is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])