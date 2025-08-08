"""
Payment and Billing API Routes

This module provides API endpoints for subscription upgrades, one-off purchases,
and Stripe webhook handling for the ProofKit billing system.

Example usage:
    POST /api/upgrade/starter - Create subscription checkout
    POST /api/buy-single - Create one-off certificate purchase  
    POST /api/billing/webhook - Handle Stripe webhooks
"""

import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, Body
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

from core.billing import get_plan, is_valid_plan, can_upgrade_from_plan
from core.stripe_util import (
    create_subscription_checkout,
    create_oneoff_checkout, 
    handle_stripe_webhook,
    get_checkout_session,
    is_stripe_configured
)
from middleware.quota import (
    load_user_quota_data, 
    update_user_plan,
    process_single_certificate_purchase,
    get_user_usage_summary
)
from auth.magic import get_current_user, require_auth
from auth.models import User
from core.logging import get_logger

logger = get_logger(__name__)

# Create router for payment endpoints
router = APIRouter(prefix="/api", tags=["billing"])


class UpgradeRequest(BaseModel):
    """Request model for plan upgrades."""
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class SinglePurchaseRequest(BaseModel):
    """Request model for single certificate purchases."""
    certificate_count: int = 1
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.post("/upgrade/{plan_name}")
async def create_upgrade_checkout(
    plan_name: str,
    request: Request,
    user: User = Depends(require_auth),
    upgrade_request: Optional[UpgradeRequest] = Body(default=None)
) -> JSONResponse:
    """
    Create Stripe checkout session for plan upgrade.
    
    Args:
        plan_name: Target plan (starter, pro, business)
        request: FastAPI request object
        upgrade_request: Upgrade configuration
        user: Authenticated user
        
    Returns:
        JSONResponse with checkout session URL or error
        
    Example:
        POST /api/upgrade/starter
        {
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503, 
            detail="Payment processing not available"
        )
    
    try:
        # Validate plan
        if not is_valid_plan(plan_name) or plan_name in ['free', 'enterprise']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan for upgrade: {plan_name}"
            )
        
        # Get current user plan
        quota_data = load_user_quota_data(user.email)
        current_plan = quota_data.get('plan', 'free')
        
        # Check if upgrade is allowed
        if current_plan == plan_name:
            # User already has this plan - redirect to customer portal for management
            raise HTTPException(
                status_code=409,
                detail=f"You already have the {plan_name} plan. Use the customer portal to manage your subscription."
            )
        
        if not can_upgrade_from_plan(current_plan, plan_name):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change from {current_plan} to {plan_name}. Please contact support if you need to downgrade."
            )
        
        # Create checkout session
        success_url = None
        cancel_url = None
        if upgrade_request:
            success_url = upgrade_request.success_url
            cancel_url = upgrade_request.cancel_url
        
        session = create_subscription_checkout(
            plan_name=plan_name,
            user_email=user.email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={'current_plan': current_plan}
        )
        
        if not session:
            raise HTTPException(
                status_code=500,
                detail="Failed to create checkout session"
            )
        
        logger.info(f"Created upgrade checkout for {user.email}: {current_plan} -> {plan_name}")
        
        return JSONResponse({
            "checkout_url": session['url'],
            "session_id": session['id'],
            "plan": plan_name,
            "current_plan": current_plan,
            "amount": session['amount'],
            "currency": session['currency']
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating upgrade checkout: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create upgrade checkout"
        )


@router.post("/buy-single")
async def create_single_purchase_checkout(
    request: Request,
    purchase_request: SinglePurchaseRequest,
    user: User = Depends(require_auth)
) -> JSONResponse:
    """
    Create Stripe checkout session for one-off certificate purchase.
    
    Args:
        request: FastAPI request object
        purchase_request: Purchase configuration
        user: Authenticated user
        
    Returns:
        JSONResponse with checkout session URL or error
        
    Example:
        POST /api/buy-single
        {
            "certificate_count": 3,
            "success_url": "https://example.com/success"
        }
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment processing not available"
        )
    
    try:
        # Validate certificate count
        if purchase_request.certificate_count < 1 or purchase_request.certificate_count > 50:
            raise HTTPException(
                status_code=400,
                detail="Certificate count must be between 1 and 50"
            )
        
        # Get current user plan
        quota_data = load_user_quota_data(user.email)
        current_plan = quota_data.get('plan', 'free')
        
        # Create checkout session
        session = create_oneoff_checkout(
            user_plan=current_plan,
            user_email=user.email,
            certificate_count=purchase_request.certificate_count,
            success_url=purchase_request.success_url,
            cancel_url=purchase_request.cancel_url
        )
        
        if not session:
            raise HTTPException(
                status_code=500,
                detail="Failed to create checkout session"
            )
        
        logger.info(f"Created single purchase checkout for {user.email}: {purchase_request.certificate_count} certs")
        
        return JSONResponse({
            "checkout_url": session['url'],
            "session_id": session['id'],
            "certificate_count": session['certificate_count'],
            "unit_price": session['unit_price'],
            "total_amount": session['total_amount'],
            "currency": session['currency']
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating single purchase checkout: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create single purchase checkout"
        )


@router.get("/usage")
async def get_usage_summary(
    request: Request,
    user: User = Depends(require_auth)
) -> JSONResponse:
    """
    Get current user's usage summary and quota information.
    
    Args:
        request: FastAPI request object
        user: Authenticated user
        
    Returns:
        JSONResponse with usage summary
        
    Example:
        GET /api/usage
        Returns: {"plan": "starter", "monthly_used": 5, "monthly_limit": 10, ...}
    """
    try:
        usage_summary = get_user_usage_summary(user.email)
        return JSONResponse(usage_summary)
        
    except Exception as e:
        logger.error(f"Error getting usage summary for {user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get usage summary"
        )


@router.get("/plans")
async def get_available_plans(request: Request) -> JSONResponse:
    """
    Get available pricing plans with features and pricing.
    
    Args:
        request: FastAPI request object
        
    Returns:
        JSONResponse with available plans
        
    Example:
        GET /api/plans
        Returns: {"free": {...}, "starter": {...}, "pro": {...}}
    """
    try:
        from core.billing import get_all_plans
        
        plans = get_all_plans()
        
        # Remove internal Stripe IDs from public API
        public_plans = {}
        for plan_name, plan_data in plans.items():
            # Handle infinity values for JSON serialization
            jobs_month = plan_data['jobs_month']
            if jobs_month == float('inf'):
                jobs_month = None  # Use None to represent unlimited
                
            public_plan = {
                'name': plan_data['name'],
                'price_usd': plan_data.get('price_usd', plan_data.get('price_eur', 0)),
                'jobs_month': jobs_month,
                'overage_price_usd': plan_data.get('overage_price_usd', plan_data.get('overage_price_eur')),
                'single_cert_price_usd': plan_data.get('single_cert_price_usd', plan_data.get('single_cert_price_eur')),
                'features': plan_data['features'],
                'pdf_template': plan_data['pdf_template']
            }
            public_plans[plan_name] = public_plan
        
        return JSONResponse(public_plans)
        
    except Exception as e:
        logger.error(f"Error getting available plans: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get available plans"
        )


@router.post("/billing/webhook")
async def handle_billing_webhook(request: Request) -> JSONResponse:
    """
    Handle Stripe webhook events for billing automation.
    
    Args:
        request: FastAPI request with webhook payload
        
    Returns:
        JSONResponse confirming webhook processing
        
    Example:
        POST /api/billing/webhook (called by Stripe)
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Billing webhooks not configured"
        )
    
    try:
        # Get webhook payload and signature
        payload = await request.body()
        signature = request.headers.get('stripe-signature')
        
        if not signature:
            raise HTTPException(
                status_code=400,
                detail="Missing Stripe signature"
            )
        
        # Verify and parse webhook
        event = handle_stripe_webhook(payload, signature)
        if not event:
            raise HTTPException(
                status_code=400,
                detail="Invalid webhook signature"
            )
        
        # Process different event types
        event_type = event['type']
        event_data = event['data']['object']
        
        logger.info(f"Processing webhook event: {event_type}")
        
        if event_type == 'checkout.session.completed':
            await handle_checkout_completed(event_data)
        elif event_type == 'customer.subscription.updated':
            await handle_subscription_updated(event_data)
        elif event_type == 'customer.subscription.deleted':
            await handle_subscription_cancelled(event_data)
        elif event_type == 'invoice.payment_succeeded':
            await handle_payment_succeeded(event_data)
        elif event_type == 'invoice.payment_failed':
            await handle_payment_failed(event_data)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
        
        return JSONResponse({"received": True, "event_type": event_type})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed"
        )


async def handle_checkout_completed(session_data: Dict[str, Any]) -> None:
    """Handle successful checkout completion."""
    try:
        customer_email = session_data.get('customer_email')
        metadata = session_data.get('metadata', {})
        session_id = session_data.get('id')
        
        if not customer_email:
            logger.error(f"No customer email in checkout session {session_id}")
            return
        
        # Get full session details
        full_session = get_checkout_session(session_id)
        if not full_session:
            logger.error(f"Could not retrieve full session details for {session_id}")
            return
        
        if metadata.get('type') == 'subscription_upgrade':
            # Handle subscription upgrade
            plan_name = metadata.get('plan')
            if plan_name:
                subscription_data = {
                    'id': full_session.get('subscription'),
                    'customer': full_session.get('customer'),
                    'status': 'active'
                }
                
                success = update_user_plan(customer_email, plan_name, subscription_data)
                if success:
                    logger.info(f"Updated plan for {customer_email} to {plan_name}")
                else:
                    logger.error(f"Failed to update plan for {customer_email}")
                    
        elif metadata.get('type') == 'single_certificate':
            # Handle single certificate purchase
            certificate_count = int(metadata.get('certificate_count', 1))
            success = process_single_certificate_purchase(customer_email, certificate_count)
            if success:
                logger.info(f"Processed single cert purchase for {customer_email}: {certificate_count} certs")
            else:
                logger.error(f"Failed to process single cert purchase for {customer_email}")
        
    except Exception as e:
        logger.error(f"Error handling checkout completion: {e}")


async def handle_subscription_updated(subscription_data: Dict[str, Any]) -> None:
    """Handle subscription status updates."""
    try:
        customer_id = subscription_data.get('customer')
        status = subscription_data.get('status')
        subscription_id = subscription_data.get('id')
        
        logger.info(f"Subscription {subscription_id} updated: {status}")
        
        # Additional subscription update logic can be added here
        # For example, updating plan limits based on subscription changes
        
    except Exception as e:
        logger.error(f"Error handling subscription update: {e}")


async def handle_subscription_cancelled(subscription_data: Dict[str, Any]) -> None:
    """Handle subscription cancellation."""
    try:
        subscription_id = subscription_data.get('id')
        customer_id = subscription_data.get('customer')
        
        logger.info(f"Subscription {subscription_id} cancelled")
        
        # Find user by customer ID and downgrade to free plan
        # Note: In real implementation, you'd need to store customer_id -> email mapping
        
    except Exception as e:
        logger.error(f"Error handling subscription cancellation: {e}")


async def handle_payment_succeeded(invoice_data: Dict[str, Any]) -> None:
    """Handle successful payment."""
    try:
        invoice_id = invoice_data.get('id')
        customer_id = invoice_data.get('customer')
        
        logger.info(f"Payment succeeded for invoice {invoice_id}")
        
    except Exception as e:
        logger.error(f"Error handling payment success: {e}")


async def handle_payment_failed(invoice_data: Dict[str, Any]) -> None:
    """Handle failed payment."""
    try:
        invoice_id = invoice_data.get('id')
        customer_id = invoice_data.get('customer')
        
        logger.warning(f"Payment failed for invoice {invoice_id}")
        
        # Additional logic for handling payment failures
        # For example, sending notification emails or suspending service
        
    except Exception as e:
        logger.error(f"Error handling payment failure: {e}")


# Billing status pages
@router.get("/billing/success")
async def billing_success(
    request: Request,
    session_id: Optional[str] = None,
    plan: Optional[str] = None
) -> JSONResponse:
    """
    Handle successful billing redirect.
    
    Args:
        request: FastAPI request object
        session_id: Stripe checkout session ID
        plan: Plan name for subscription upgrades
        
    Returns:
        Success response with next steps
    """
    return JSONResponse({
        "success": True,
        "message": "Payment completed successfully",
        "session_id": session_id,
        "plan": plan,
        "next_steps": [
            "Your account has been updated",
            "You can now use your new plan features",
            "Check your email for receipt"
        ]
    })


@router.get("/billing/cancel")
async def billing_cancel(request: Request) -> JSONResponse:
    """
    Handle cancelled billing redirect.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Response indicating cancellation
    """
    return JSONResponse({
        "cancelled": True,
        "message": "Payment was cancelled",
        "next_steps": [
            "No charges were made",
            "You can try again anytime", 
            "Contact support if you need help"
        ]
    })


@router.get("/billing/cert-success")
async def cert_purchase_success(
    request: Request,
    count: int = 1
) -> JSONResponse:
    """
    Handle successful certificate purchase redirect.
    
    Args:
        request: FastAPI request object
        count: Number of certificates purchased
        
    Returns:
        Success response for certificate purchase
    """
    return JSONResponse({
        "success": True,
        "message": f"Successfully purchased {count} certificate{'s' if count != 1 else ''}",
        "certificate_count": count,
        "next_steps": [
            f"You now have {count} additional certificate{'s' if count != 1 else ''} available",
            "You can compile your CSV files immediately",
            "Check your email for receipt"
        ]
    })


@router.get("/stripe-config")
async def get_stripe_config(request: Request) -> JSONResponse:
    """
    Get Stripe publishable key for frontend initialization.
    
    Returns:
        JSONResponse with Stripe publishable key
    """
    from core.billing import STRIPE_PUBLISHABLE_KEY
    
    return JSONResponse({
        "publishableKey": STRIPE_PUBLISHABLE_KEY,
        "testMode": STRIPE_PUBLISHABLE_KEY.startswith("pk_test_") if STRIPE_PUBLISHABLE_KEY else True
    })


@router.post("/customer-portal")
async def create_customer_portal_session(
    request: Request,
    user: User = Depends(require_auth)
) -> JSONResponse:
    """
    Create Stripe Customer Portal session for subscription management.
    
    Args:
        request: FastAPI request object
        user: Authenticated user
        
    Returns:
        JSONResponse with portal URL or error
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Customer portal not available"
        )
    
    try:
        import stripe
        from core.stripe_util import get_customer_subscriptions
        
        # Get customer subscriptions
        subscriptions = get_customer_subscriptions(user.email)
        if not subscriptions or not subscriptions.data:
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )
        
        # Get customer ID from first subscription
        customer_id = subscriptions.data[0].customer
        
        # Create portal session
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{os.environ.get('BASE_URL', 'https://www.proofkit.net')}/dashboard"
        )
        
        logger.info(f"Created customer portal session for {user.email}")
        
        return JSONResponse({
            "url": session.url
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating customer portal session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create customer portal session"
        )