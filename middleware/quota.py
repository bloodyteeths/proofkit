"""
Quota Enforcement Middleware

This module implements quota enforcement for different pricing tiers,
including free tier limits, monthly quotas, and overage billing logic.

Example usage:
    # Check if user can compile certificate
    can_compile, error_data = check_compilation_quota(user)
    if not can_compile:
        return JSONResponse(status_code=402, content=error_data)
        
    # Record usage after successful compilation
    record_usage(user, 'certificate_compiled')
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from core.billing import get_plan, get_single_cert_price, get_stripe_price_id
from core.stripe_util import create_oneoff_checkout, create_usage_record
from core.logging import get_logger
from auth.models import User

logger = get_logger(__name__)

# Storage for quota tracking
QUOTA_STORAGE_DIR = Path("storage/quota")
QUOTA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_user_quota_file(user_email: str) -> Path:
    """
    Get path to user's quota tracking file.
    
    Args:
        user_email: User email address
        
    Returns:
        Path to quota file
        
    Example:
        >>> quota_file = get_user_quota_file('user@example.com')
    """
    # Hash email for privacy and filesystem safety
    import hashlib
    email_hash = hashlib.sha256(user_email.encode()).hexdigest()[:16]
    return QUOTA_STORAGE_DIR / f"quota_{email_hash}.json"


def load_user_quota_data(user_email: str) -> Dict[str, Any]:
    """
    Load user's quota usage data.
    
    Args:
        user_email: User email address
        
    Returns:
        Dictionary with quota usage data
        
    Example:
        >>> data = load_user_quota_data('user@example.com')
        >>> monthly_usage = data['current_month']['certificates_compiled']
    """
    quota_file = get_user_quota_file(user_email)
    
    if not quota_file.exists():
        # Initialize new user quota data
        return {
            'user_email': user_email,
            'plan': 'free',
            'total_certificates': 0,  # All-time count for free tier
            'current_month': {
                'month': datetime.now(timezone.utc).strftime('%Y-%m'),
                'certificates_compiled': 0,
                'overage_used': 0,
                'single_certs_purchased': 0
            },
            'subscription': {
                'stripe_subscription_id': None,
                'stripe_customer_id': None,
                'active': False,
                'current_period_end': None
            },
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    
    try:
        with open(quota_file, 'r') as f:
            data = json.load(f)
            
        # Reset monthly counters if new month
        current_month = datetime.now(timezone.utc).strftime('%Y-%m')
        if data['current_month']['month'] != current_month:
            data['current_month'] = {
                'month': current_month,
                'certificates_compiled': 0,
                'overage_used': 0,
                'single_certs_purchased': 0
            }
            save_user_quota_data(user_email, data)
            
        return data
        
    except Exception as e:
        logger.error(f"Error loading quota data for {user_email}: {e}")
        return load_user_quota_data(user_email)  # Return default


def save_user_quota_data(user_email: str, data: Dict[str, Any]) -> bool:
    """
    Save user's quota usage data.
    
    Args:
        user_email: User email address
        data: Quota data to save
        
    Returns:
        True if saved successfully, False otherwise
        
    Example:
        >>> data['current_month']['certificates_compiled'] += 1
        >>> save_user_quota_data('user@example.com', data)
    """
    try:
        quota_file = get_user_quota_file(user_email)
        data['last_updated'] = datetime.now(timezone.utc).isoformat()
        
        with open(quota_file, 'w') as f:
            json.dump(data, f, indent=2)
            
        return True
        
    except Exception as e:
        logger.error(f"Error saving quota data for {user_email}: {e}")
        return False


def check_compilation_quota(user: Optional[User]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if user can compile another certificate within their quota.
    
    Args:
        user: Authenticated user object (None for anonymous)
        
    Returns:
        Tuple of (can_compile, error_response_data)
        
    Example:
        >>> can_compile, error = check_compilation_quota(current_user)
        >>> if not can_compile:
        ...     return JSONResponse(status_code=402, content=error)
    """
    # Anonymous users get free tier with 2 total certificates
    if not user:
        # For anonymous users, we could track by IP but for simplicity
        # we'll allow unlimited for now and rely on rate limiting
        return True, None
        
    user_email = user.email
    quota_data = load_user_quota_data(user_email)
    user_plan = quota_data.get('plan', 'free')
    
    plan = get_plan(user_plan)
    if not plan:
        logger.error(f"Invalid plan for user {user_email}: {user_plan}")
        return False, {
            'error': 'Invalid user plan configuration',
            'code': 'INVALID_PLAN'
        }
    
    current_month_usage = quota_data['current_month']['certificates_compiled']
    
    # Free tier logic - 2 certificates total (lifetime)
    if user_plan == 'free':
        total_certificates = quota_data.get('total_certificates', 0)
        
        if total_certificates >= 2:
            # Free tier exceeded - offer upgrade or single purchase
            single_cert_price = get_single_cert_price('free')
            checkout_session = create_oneoff_checkout(
                user_plan='free',
                user_email=user_email,
                certificate_count=1
            )
            
            return False, {
                'error': 'Free tier limit exceeded',
                'code': 'FREE_TIER_EXCEEDED',
                'message': f'You have used all {plan["jobs_month"]} free certificates. Upgrade or purchase individual certificates.',
                'total_used': total_certificates,
                'limit': 2,
                'upgrade_options': {
                    'starter_plan': {
                        'name': 'Starter',
                        'price': 14,
                        'monthly_certificates': 10,
                        'upgrade_url': f'/api/upgrade/starter'
                    }
                },
                'single_purchase': {
                    'price': single_cert_price,
                    'checkout_url': checkout_session['url'] if checkout_session else None
                }
            }
    
    # Paid tier logic - monthly quota with overage
    else:
        monthly_quota = plan['jobs_month']
        
        if current_month_usage >= monthly_quota:
            # Over monthly quota - check if overage is available
            overage_price = plan.get('overage_price_eur')
            
            if overage_price and overage_price > 0:
                # Overage allowed - auto-bill and continue
                logger.info(f"User {user_email} using overage: {current_month_usage + 1}/{monthly_quota}")
                return True, None  # Allow compilation, overage will be billed
            else:
                # No overage - offer single certificate purchase
                single_cert_price = get_single_cert_price(user_plan)
                checkout_session = create_oneoff_checkout(
                    user_plan=user_plan,
                    user_email=user_email,
                    certificate_count=1
                )
                
                return False, {
                    'error': 'Monthly quota exceeded',
                    'code': 'MONTHLY_QUOTA_EXCEEDED',
                    'message': f'You have used all {monthly_quota} certificates this month.',
                    'monthly_used': current_month_usage,
                    'monthly_limit': monthly_quota,
                    'plan': user_plan,
                    'single_purchase': {
                        'price': single_cert_price,
                        'checkout_url': checkout_session['url'] if checkout_session else None
                    }
                }
    
    # Within quota - allow compilation
    return True, None


def record_usage(user: Optional[User], usage_type: str = 'certificate_compiled') -> bool:
    """
    Record usage after successful operation.
    
    Args:
        user: Authenticated user object (None for anonymous)
        usage_type: Type of usage to record
        
    Returns:
        True if recorded successfully, False otherwise
        
    Example:
        >>> record_usage(current_user, 'certificate_compiled')
    """
    if not user:
        # Skip tracking for anonymous users
        return True
        
    try:
        user_email = user.email
        quota_data = load_user_quota_data(user_email)
        user_plan = quota_data.get('plan', 'free')
        
        # Update counters
        if usage_type == 'certificate_compiled':
            quota_data['current_month']['certificates_compiled'] += 1
            
            # Update total for free tier
            if user_plan == 'free':
                quota_data['total_certificates'] = quota_data.get('total_certificates', 0) + 1
            
            # Check if this is overage usage for paid plans
            plan = get_plan(user_plan)
            if plan and user_plan != 'free':
                monthly_quota = plan['jobs_month']
                current_usage = quota_data['current_month']['certificates_compiled']
                
                if current_usage > monthly_quota:
                    # This is overage - increment overage counter
                    quota_data['current_month']['overage_used'] += 1
                    
                    # Create Stripe usage record if subscription active
                    subscription_id = quota_data.get('subscription', {}).get('stripe_subscription_id')
                    if subscription_id:
                        # Note: In real implementation, you'd need the subscription_item_id
                        # for the overage price. This would be stored during subscription creation.
                        logger.info(f"Overage usage recorded for {user_email}: {current_usage}/{monthly_quota}")
        
        # Save updated data
        return save_user_quota_data(user_email, quota_data)
        
    except Exception as e:
        logger.error(f"Error recording usage for user {user.email if user else 'anonymous'}: {e}")
        return False


def update_user_plan(user_email: str, new_plan: str, subscription_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    Update user's plan after successful subscription.
    
    Args:
        user_email: User email address
        new_plan: New plan name
        subscription_data: Stripe subscription data
        
    Returns:
        True if updated successfully, False otherwise
        
    Example:
        >>> update_user_plan('user@example.com', 'pro', stripe_subscription_data)
    """
    try:
        quota_data = load_user_quota_data(user_email)
        quota_data['plan'] = new_plan
        
        if subscription_data:
            quota_data['subscription'] = {
                'stripe_subscription_id': subscription_data.get('id'),
                'stripe_customer_id': subscription_data.get('customer'),
                'active': subscription_data.get('status') == 'active',
                'current_period_end': subscription_data.get('current_period_end')
            }
        
        logger.info(f"Updated plan for {user_email}: {new_plan}")
        return save_user_quota_data(user_email, quota_data)
        
    except Exception as e:
        logger.error(f"Error updating plan for {user_email}: {e}")
        return False


def get_user_usage_summary(user_email: str) -> Dict[str, Any]:
    """
    Get user's current usage summary.
    
    Args:
        user_email: User email address
        
    Returns:
        Dictionary with usage summary
        
    Example:
        >>> summary = get_user_usage_summary('user@example.com')
        >>> remaining = summary['monthly_remaining']
    """
    quota_data = load_user_quota_data(user_email)
    user_plan = quota_data.get('plan', 'free')
    plan = get_plan(user_plan)
    
    if not plan:
        return {'error': 'Invalid plan configuration'}
    
    current_month_usage = quota_data['current_month']['certificates_compiled']
    
    if user_plan == 'free':
        total_used = quota_data.get('total_certificates', 0)
        return {
            'plan': user_plan,
            'plan_name': plan['name'],
            'total_used': total_used,
            'total_limit': 2,
            'total_remaining': max(0, 2 - total_used),
            'is_unlimited': False,
            'overage_available': False
        }
    else:
        monthly_quota = plan['jobs_month']
        monthly_remaining = max(0, monthly_quota - current_month_usage)
        overage_used = quota_data['current_month']['overage_used']
        
        return {
            'plan': user_plan,
            'plan_name': plan['name'],
            'monthly_used': current_month_usage,
            'monthly_limit': monthly_quota,
            'monthly_remaining': monthly_remaining,
            'overage_used': overage_used,
            'overage_price': plan.get('overage_price_eur'),
            'is_unlimited': monthly_quota == float('inf'),
            'overage_available': bool(plan.get('overage_price_eur'))
        }


def process_single_certificate_purchase(user_email: str, certificate_count: int = 1) -> bool:
    """
    Process a single certificate purchase - add to user's quota.
    
    Args:
        user_email: User email address
        certificate_count: Number of certificates purchased
        
    Returns:
        True if processed successfully, False otherwise
        
    Example:
        >>> process_single_certificate_purchase('user@example.com', 3)
    """
    try:
        quota_data = load_user_quota_data(user_email)
        quota_data['current_month']['single_certs_purchased'] += certificate_count
        
        logger.info(f"Processed single cert purchase for {user_email}: {certificate_count} certificates")
        return save_user_quota_data(user_email, quota_data)
        
    except Exception as e:
        logger.error(f"Error processing single cert purchase for {user_email}: {e}")
        return False


def quota_middleware(request: Request, call_next):
    """
    Middleware to enforce quota limits on compilation endpoints.
    
    Args:
        request: FastAPI request
        call_next: Next handler in chain
        
    Returns:
        Response with quota enforcement applied
        
    Example:
        app.add_middleware(BaseHTTPMiddleware, dispatch=quota_middleware)
    """
    # Only apply quota check to compilation endpoints
    if request.url.path not in ['/api/compile', '/api/compile/json']:
        return call_next(request)
    
    # Get current user
    from auth.magic import get_current_user
    user = get_current_user(request)
    
    # Check quota
    can_compile, error_data = check_compilation_quota(user)
    
    if not can_compile:
        return JSONResponse(
            status_code=402,
            content=error_data
        )
    
    # Allow request to proceed
    response = call_next(request)
    
    # Record usage after successful compilation
    if response.status_code == 200:
        record_usage(user, 'certificate_compiled')
    
    return response