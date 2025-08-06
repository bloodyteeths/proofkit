"""
Stripe Integration Utilities

This module provides helper functions for creating Stripe checkout sessions, handling
webhooks, and managing subscription billing for ProofKit pricing tiers.

Example usage:
    # Create upgrade checkout session
    session = create_subscription_checkout('starter', user_email='user@example.com')
    
    # Create one-off certificate purchase
    session = create_oneoff_checkout('pro', user_email='user@example.com')
    
    # Handle webhook events
    event = handle_stripe_webhook(payload, signature)
"""

import stripe
import os
from typing import Dict, Any, Optional
from urllib.parse import urljoin
from core.billing import (
    get_plan, 
    get_stripe_price_id, 
    get_single_cert_price,
    STRIPE_SECRET_KEY,
    STRIPE_TEST_MODE
)
from core.logging import get_logger

logger = get_logger(__name__)

# Initialize Stripe with secret key
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY not configured - Stripe functionality disabled")

# Base URL configuration
BASE_URL = os.environ.get("BASE_URL", "https://www.proofkit.net")


def create_subscription_checkout(
    plan_name: str, 
    user_email: str,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Create a Stripe checkout session for a subscription plan upgrade.
    
    Args:
        plan_name: Target plan identifier (starter, pro, business)
        user_email: User email address
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect after canceled payment
        metadata: Additional metadata to include in session
        
    Returns:
        Stripe checkout session data or None if failed
        
    Example:
        >>> session = create_subscription_checkout('pro', 'user@example.com')
        >>> redirect_url = session['url']
    """
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe not configured - cannot create checkout session")
        return None
        
    try:
        plan = get_plan(plan_name)
        if not plan or plan_name == 'free' or plan_name == 'enterprise':
            logger.error(f"Invalid plan for subscription checkout: {plan_name}")
            return None
            
        price_id = get_stripe_price_id(plan_name, 'monthly')
        if not price_id:
            logger.error(f"No Stripe price ID configured for plan: {plan_name}")
            return None
            
        # Default URLs
        if not success_url:
            success_url = urljoin(BASE_URL, f"/billing/success?plan={plan_name}")
        if not cancel_url:
            cancel_url = urljoin(BASE_URL, "/billing/cancel")
            
        # Session metadata
        session_metadata = {
            'plan': plan_name,
            'user_email': user_email,
            'type': 'subscription_upgrade'
        }
        if metadata:
            session_metadata.update(metadata)
            
        # Create checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            customer_email=user_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=session_metadata,
            allow_promotion_codes=True,
            billing_address_collection='required',
            tax_id_collection={'enabled': True},
            automatic_tax={'enabled': False},  # Enable if you have tax calculation set up
        )
        
        logger.info(f"Created subscription checkout session for {user_email} -> {plan_name}")
        return {
            'id': session.id,
            'url': session.url,
            'plan': plan_name,
            'amount': plan['price_eur'] * 100,  # Stripe uses cents
            'currency': 'eur'
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating subscription checkout: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating subscription checkout: {e}")
        return None


def create_oneoff_checkout(
    user_plan: str,
    user_email: str, 
    certificate_count: int = 1,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Create a Stripe checkout session for one-off certificate purchase.
    
    Args:
        user_plan: Current user plan (determines certificate price)
        user_email: User email address
        certificate_count: Number of certificates to purchase
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect after canceled payment 
        metadata: Additional metadata to include in session
        
    Returns:
        Stripe checkout session data or None if failed
        
    Example:
        >>> session = create_oneoff_checkout('free', 'user@example.com', 1)
        >>> redirect_url = session['url']
    """
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe not configured - cannot create checkout session")
        return None
        
    try:
        cert_price = get_single_cert_price(user_plan)
        if not cert_price:
            logger.error(f"No single certificate pricing for plan: {user_plan}")
            return None
            
        price_id = get_stripe_price_id(user_plan, 'single_cert')
        if not price_id:
            logger.error(f"No single cert price ID configured for plan: {user_plan}")
            return None
            
        # Default URLs
        if not success_url:
            success_url = urljoin(BASE_URL, f"/billing/cert-success?count={certificate_count}")
        if not cancel_url:
            cancel_url = urljoin(BASE_URL, "/billing/cancel")
            
        # Session metadata
        session_metadata = {
            'user_plan': user_plan,
            'user_email': user_email,
            'certificate_count': str(certificate_count),
            'type': 'single_certificate'
        }
        if metadata:
            session_metadata.update(metadata)
            
        # Create checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': certificate_count,
            }],
            mode='payment',
            customer_email=user_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=session_metadata,
            billing_address_collection='required',
        )
        
        logger.info(f"Created one-off checkout session for {user_email}: {certificate_count} certs")
        return {
            'id': session.id,
            'url': session.url,
            'certificate_count': certificate_count,
            'unit_price': cert_price,
            'total_amount': cert_price * certificate_count * 100,  # Stripe uses cents
            'currency': 'eur'
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating one-off checkout: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating one-off checkout: {e}")
        return None


def create_usage_record(subscription_item_id: str, quantity: int) -> bool:
    """
    Create a usage record for metered billing (overage charges).
    
    Args:
        subscription_item_id: Stripe subscription item ID
        quantity: Number of units consumed
        
    Returns:
        True if usage record created successfully, False otherwise
        
    Example:
        >>> success = create_usage_record('si_abc123', 3)
    """
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe not configured - cannot create usage record")
        return False
        
    try:
        usage_record = stripe.UsageRecord.create(
            quantity=quantity,
            timestamp='now',
            subscription_item=subscription_item_id,
        )
        
        logger.info(f"Created usage record: {quantity} units for {subscription_item_id}")
        return True
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating usage record: {e}")
        return False
    except Exception as e:
        logger.error(f"Error creating usage record: {e}")
        return False


def handle_stripe_webhook(payload: bytes, sig_header: str) -> Optional[Dict[str, Any]]:
    """
    Handle and verify Stripe webhook events.
    
    Args:
        payload: Raw webhook payload
        sig_header: Stripe signature header
        
    Returns:
        Parsed webhook event or None if verification failed
        
    Example:
        >>> event = handle_stripe_webhook(request.body, request.headers['stripe-signature'])
        >>> if event['type'] == 'checkout.session.completed':
        ...     handle_successful_payment(event['data']['object'])
    """
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return None
        
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        
        logger.info(f"Verified webhook event: {event['type']}")
        return event
        
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        return None
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        return None
    except Exception as e:
        logger.error(f"Webhook handling error: {e}")
        return None


def get_customer_subscriptions(customer_email: str) -> Optional[Dict[str, Any]]:
    """
    Get active subscriptions for a customer by email.
    
    Args:
        customer_email: Customer email address
        
    Returns:
        Subscription data or None if not found
        
    Example:
        >>> subs = get_customer_subscriptions('user@example.com')
        >>> active_plan = subs['data'][0]['items']['data'][0]['price']['id']
    """
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe not configured - cannot get subscriptions")
        return None
        
    try:
        # Find customer by email
        customers = stripe.Customer.list(email=customer_email, limit=1)
        if not customers.data:
            return None
            
        customer = customers.data[0]
        
        # Get active subscriptions
        subscriptions = stripe.Subscription.list(
            customer=customer.id,
            status='active',
            limit=10
        )
        
        return subscriptions
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error getting subscriptions: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting subscriptions: {e}")
        return None


def cancel_subscription(subscription_id: str) -> bool:
    """
    Cancel a Stripe subscription immediately.
    
    Args:
        subscription_id: Stripe subscription ID
        
    Returns:
        True if canceled successfully, False otherwise
        
    Example:
        >>> success = cancel_subscription('sub_abc123')
    """
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe not configured - cannot cancel subscription")
        return False
        
    try:
        stripe.Subscription.delete(subscription_id)
        logger.info(f"Canceled subscription: {subscription_id}")
        return True
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error canceling subscription: {e}")
        return False
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
        return False


def get_checkout_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a checkout session by ID.
    
    Args:
        session_id: Stripe checkout session ID
        
    Returns:
        Session data or None if not found
        
    Example:
        >>> session = get_checkout_session('cs_abc123')
        >>> customer_email = session['customer_email']
    """
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe not configured - cannot get checkout session")
        return None
        
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error getting checkout session: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting checkout session: {e}")
        return None


def is_stripe_configured() -> bool:
    """
    Check if Stripe is properly configured.
    
    Returns:
        True if Stripe keys are available, False otherwise
        
    Example:
        >>> if is_stripe_configured():
        ...     session = create_subscription_checkout('pro', 'user@example.com')
    """
    return bool(STRIPE_SECRET_KEY and os.environ.get("STRIPE_WEBHOOK_SECRET"))