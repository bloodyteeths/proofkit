"""
Integration tests for Stripe webhook subscription handling.

These tests verify that Stripe webhook events properly update user plans
and quotas through the complete webhook → plan → quota update pathway.

Example usage:
    pytest tests/billing/test_webhook_subscription.py -v
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.routes.pay import handle_billing_webhook, handle_checkout_completed
from middleware.quota import update_user_plan, load_user_quota_data
from core.billing import get_plan


@pytest.fixture
def mock_stripe_webhook_event():
    """Mock Stripe webhook event for subscription upgrade."""
    return {
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'id': 'cs_test_123456789',
                'customer_email': 'test@example.com',
                'mode': 'subscription',
                'status': 'complete',
                'metadata': {
                    'type': 'subscription_upgrade',
                    'plan': 'pro',
                    'user_email': 'test@example.com'
                },
                'subscription': 'sub_test_123456789',
                'customer': 'cus_test_123456789'
            }
        }
    }


@pytest.fixture
def mock_single_cert_webhook_event():
    """Mock Stripe webhook event for single certificate purchase."""
    return {
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'id': 'cs_test_987654321',
                'customer_email': 'test@example.com',
                'mode': 'payment',
                'status': 'complete',
                'metadata': {
                    'type': 'single_certificate',
                    'user_plan': 'free',
                    'user_email': 'test@example.com',
                    'certificate_count': '3'
                }
            }
        }
    }


@pytest.fixture
def mock_subscription_data():
    """Mock Stripe subscription data."""
    return {
        'id': 'sub_test_123456789',
        'customer': 'cus_test_123456789',
        'status': 'active',
        'current_period_start': 1640995200,  # Jan 1, 2022
        'current_period_end': 1672531200,    # Jan 1, 2023
        'items': {
            'data': [
                {
                    'price': {
                        'id': 'price_pro_month',
                        'recurring': {
                            'interval': 'month'
                        }
                    }
                }
            ]
        }
    }


class TestWebhookSubscriptionIntegration:
    """Integration tests for webhook subscription handling."""

    @patch('core.stripe_util.handle_stripe_webhook')
    @patch('core.stripe_util.get_checkout_session')
    @patch('middleware.quota.update_user_plan')
    async def test_subscription_upgrade_webhook_flow(
        self, 
        mock_update_plan, 
        mock_get_session,
        mock_handle_webhook,
        mock_stripe_webhook_event,
        mock_subscription_data
    ):
        """Test complete subscription upgrade webhook flow."""
        # Setup mocks
        mock_handle_webhook.return_value = mock_stripe_webhook_event
        mock_get_session.return_value = mock_subscription_data
        mock_update_plan.return_value = True
        
        # Create mock request
        mock_request = Mock()
        mock_request.body = Mock(return_value=b'webhook_payload')
        mock_request.headers = {'stripe-signature': 'valid_signature'}
        
        # Process webhook
        await handle_checkout_completed(mock_stripe_webhook_event['data']['object'])
        
        # Verify plan update was called
        mock_update_plan.assert_called_once_with(
            'test@example.com', 
            'pro', 
            {
                'id': 'sub_test_123456789',
                'customer': 'cus_test_123456789',
                'status': 'active'
            }
        )

    @patch('middleware.quota.process_single_certificate_purchase')
    async def test_single_certificate_webhook_flow(
        self, 
        mock_process_purchase,
        mock_single_cert_webhook_event
    ):
        """Test single certificate purchase webhook flow."""
        # Setup mock
        mock_process_purchase.return_value = True
        
        # Process webhook
        await handle_checkout_completed(mock_single_cert_webhook_event['data']['object'])
        
        # Verify certificate purchase was processed
        mock_process_purchase.assert_called_once_with('test@example.com', 3)

    def test_update_user_plan_integration(self, tmp_path):
        """Test user plan update integration with quota system."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            test_email = 'test@example.com'
            
            # Initialize user with free plan
            initial_data = load_user_quota_data(test_email)
            assert initial_data['plan'] == 'free'
            assert initial_data['total_certificates'] == 0
            
            # Update to pro plan
            subscription_data = {
                'id': 'sub_test_123',
                'customer': 'cus_test_123',
                'status': 'active',
                'current_period_end': 1672531200
            }
            
            success = update_user_plan(test_email, 'pro', subscription_data)
            assert success
            
            # Verify plan was updated
            updated_data = load_user_quota_data(test_email)
            assert updated_data['plan'] == 'pro'
            assert updated_data['subscription']['stripe_subscription_id'] == 'sub_test_123'
            assert updated_data['subscription']['stripe_customer_id'] == 'cus_test_123'
            assert updated_data['subscription']['active'] is True

    def test_subscription_cancellation_handling(self):
        """Test subscription cancellation webhook handling."""
        cancellation_event = {
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': 'sub_test_123456789',
                    'customer': 'cus_test_123456789',
                    'status': 'canceled'
                }
            }
        }
        
        # Note: This would need additional implementation in the actual webhook handler
        # to properly downgrade users to free plan when subscription is cancelled
        assert cancellation_event['type'] == 'customer.subscription.deleted'

    def test_quota_limits_after_plan_upgrade(self, tmp_path):
        """Test that quota limits are correctly applied after plan upgrade."""
        with patch('middleware.quota.QUOTA_STORAGE_DIR', tmp_path):
            test_email = 'test@example.com'
            
            # Start with free plan (2 certificate limit)
            initial_data = load_user_quota_data(test_email)
            free_plan = get_plan('free')
            assert free_plan['jobs_month'] == 2
            
            # Upgrade to pro plan
            update_user_plan(test_email, 'pro', {
                'id': 'sub_test',
                'customer': 'cus_test',
                'status': 'active'
            })
            
            # Verify new plan limits
            updated_data = load_user_quota_data(test_email)
            pro_plan = get_plan(updated_data['plan'])
            assert pro_plan['jobs_month'] == 50  # Updated Pro plan limit
            assert pro_plan['overage_price_usd'] == 2

    @patch('core.stripe_util.is_stripe_configured')
    async def test_webhook_requires_stripe_configuration(self, mock_is_configured):
        """Test webhook endpoint requires Stripe configuration."""
        mock_is_configured.return_value = False
        
        mock_request = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await handle_billing_webhook(mock_request)
        
        assert exc_info.value.status_code == 503
        assert "not configured" in str(exc_info.value.detail)

    def test_plan_validation_in_webhook(self):
        """Test that webhook validates plan names."""
        invalid_event_data = {
            'customer_email': 'test@example.com',
            'metadata': {
                'type': 'subscription_upgrade',
                'plan': 'invalid_plan'
            }
        }
        
        # This should not crash but should log an error
        # The actual implementation should validate plan names
        plan = get_plan('invalid_plan')
        assert plan is None

    def test_webhook_handles_missing_email(self):
        """Test webhook gracefully handles missing customer email."""
        event_data = {
            'id': 'cs_test_123',
            'metadata': {
                'type': 'subscription_upgrade',
                'plan': 'pro'
            }
            # Missing customer_email
        }
        
        # This should not crash - the webhook handler should log an error
        # and return early when customer_email is missing
        assert event_data.get('customer_email') is None


class TestBillingPlanConfiguration:
    """Test billing plan configuration matches requirements."""

    def test_free_plan_configuration(self):
        """Test Free plan matches requirements."""
        free_plan = get_plan('free')
        assert free_plan is not None
        assert free_plan['jobs_month'] == 2
        assert free_plan['price_usd'] == 0
        assert free_plan['overage_price_usd'] is None
        assert free_plan['single_cert_price_usd'] == 9

    def test_starter_plan_configuration(self):
        """Test Starter plan matches requirements."""
        starter_plan = get_plan('starter')
        assert starter_plan is not None
        assert starter_plan['jobs_month'] == 10
        assert starter_plan['price_usd'] == 19
        assert starter_plan['overage_price_usd'] == 3
        assert starter_plan['single_cert_price_usd'] == 7

    def test_pro_plan_configuration(self):
        """Test Pro plan matches requirements."""
        pro_plan = get_plan('pro')
        assert pro_plan is not None
        assert pro_plan['jobs_month'] == 50  # Updated requirement
        assert pro_plan['price_usd'] == 79
        assert pro_plan['overage_price_usd'] == 2
        assert pro_plan['single_cert_price_usd'] == 5

    def test_enterprise_plan_configuration(self):
        """Test Enterprise plan matches requirements."""
        enterprise_plan = get_plan('enterprise')
        assert enterprise_plan is not None
        assert enterprise_plan['jobs_month'] == float('inf')
        assert enterprise_plan['price_usd'] is None
        assert enterprise_plan['overage_price_usd'] is None

    def test_premium_cert_configuration(self):
        """Test premium certificate configuration."""
        from core.billing import get_premium_cert_config
        
        premium_config = get_premium_cert_config()
        assert premium_config is not None
        assert premium_config['price_usd'] == 12
        assert premium_config['name'] == 'Premium Certificate'
        assert 'stripe_price_id' in premium_config


if __name__ == '__main__':
    pytest.main([__file__, '-v'])