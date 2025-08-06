"""
ProofKit Billing and Pricing Configuration

This module defines pricing tiers, subscription plans, and billing-related data structures
for the ProofKit revenue model. Supports tiered pricing with monthly quotas, overage 
charges, and one-off certificate purchases.

Example usage:
    # Get plan information
    plan = get_plan('starter')
    print(f"Monthly quota: {plan['jobs_month']}")
    
    # Check if user can upgrade
    if can_upgrade_from_plan('free', 'pro'):
        create_stripe_checkout('pro')
"""

from typing import Dict, Any, Optional
from enum import Enum
import os


class PlanTier(str, Enum):
    """Available pricing tiers for ProofKit."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


# Pricing configuration - update with actual Stripe price IDs after setup
PLANS: Dict[str, Dict[str, Any]] = {
    "free": {
        "name": "Free",
        "price_eur": 0,
        "jobs_month": 2,  # 2 total certificates allowed
        "overage_price_eur": None,  # No overage allowed
        "single_cert_price_eur": 7,
        "features": [
            "2 total certificates",
            "Basic PDF template",
            "Community support"
        ],
        "pdf_template": "free",
        "stripe_product_id": None,
        "stripe_price_id": None,
        "stripe_overage_price_id": None,
        "single_cert_price_id": "price_single_cert"  # €7 one-off cert
    },
    "starter": {
        "name": "Starter",
        "price_eur": 14,
        "jobs_month": 10,
        "overage_price_eur": 3,
        "single_cert_price_eur": 5,
        "features": [
            "10 certificates/month",
            "Standard PDF template", 
            "Email support",
            "€3 overage per certificate"
        ],
        "pdf_template": "standard",
        "stripe_product_id": "proofkit_starter",
        "stripe_price_id": os.environ.get("STRIPE_PRICE_ID_STARTER", "price_starter_month"),
        "stripe_overage_price_id": "price_starter_over",
        "single_cert_price_id": "price_single_cert"
    },
    "pro": {
        "name": "Pro",
        "price_eur": 59,
        "jobs_month": 75,
        "overage_price_eur": 1.5,
        "single_cert_price_eur": 4,
        "features": [
            "75 certificates/month",
            "Custom logo template",
            "Priority support",
            "€1.50 overage per certificate"
        ],
        "pdf_template": "pro",
        "stripe_product_id": "proofkit_pro", 
        "stripe_price_id": os.environ.get("STRIPE_PRICE_ID_PRO", "price_pro_month"),
        "stripe_overage_price_id": "price_pro_over",
        "single_cert_price_id": "price_single_cert"
    },
    "business": {
        "name": "Business",
        "price_eur": 199,
        "jobs_month": 300,
        "overage_price_eur": 0.75,
        "single_cert_price_eur": 4,
        "features": [
            "300 certificates/month",
            "Custom logo + header template",
            "Phone & email support",
            "€0.75 overage per certificate"
        ],
        "pdf_template": "business",
        "stripe_product_id": "proofkit_business",
        "stripe_price_id": os.environ.get("STRIPE_PRICE_ID_BUSINESS", "price_business_month"), 
        "stripe_overage_price_id": "price_business_over",
        "single_cert_price_id": "price_single_cert"
    },
    "enterprise": {
        "name": "Enterprise",
        "price_eur": None,  # Custom pricing
        "jobs_month": float('inf'),  # Unlimited
        "overage_price_eur": None,
        "single_cert_price_eur": None,
        "features": [
            "Unlimited certificates",
            "White-label template",
            "Dedicated support",
            "Custom integrations"
        ],
        "pdf_template": "enterprise",
        "stripe_product_id": None,
        "stripe_price_id": None,
        "stripe_overage_price_id": None,
        "single_cert_price_id": None
    }
}


def get_plan(plan_name: str) -> Optional[Dict[str, Any]]:
    """
    Get plan configuration by name.
    
    Args:
        plan_name: Plan identifier (free, starter, pro, business, enterprise)
        
    Returns:
        Plan configuration dictionary or None if not found
        
    Example:
        >>> plan = get_plan('pro')
        >>> print(plan['jobs_month'])
        75
    """
    return PLANS.get(plan_name)


def get_all_plans() -> Dict[str, Dict[str, Any]]:
    """
    Get all available pricing plans.
    
    Returns:
        Dictionary of all plans with their configurations
        
    Example:
        >>> plans = get_all_plans()
        >>> for name, config in plans.items():
        ...     print(f"{name}: €{config['price_eur']}/month")
    """
    return PLANS.copy()


def is_valid_plan(plan_name: str) -> bool:
    """
    Check if plan name is valid.
    
    Args:
        plan_name: Plan identifier to validate
        
    Returns:
        True if plan exists, False otherwise
        
    Example:
        >>> is_valid_plan('pro')
        True
        >>> is_valid_plan('invalid')
        False
    """
    return plan_name in PLANS


def can_upgrade_from_plan(current_plan: str, target_plan: str) -> bool:
    """
    Check if upgrade from current plan to target plan is allowed.
    
    Args:
        current_plan: Current user plan
        target_plan: Plan user wants to upgrade to
        
    Returns:
        True if upgrade is allowed, False otherwise
        
    Example:
        >>> can_upgrade_from_plan('free', 'starter')
        True
        >>> can_upgrade_from_plan('pro', 'starter')
        False
    """
    if not is_valid_plan(current_plan) or not is_valid_plan(target_plan):
        return False
    
    # Define plan hierarchy
    plan_order = ['free', 'starter', 'pro', 'business', 'enterprise']
    
    try:
        current_idx = plan_order.index(current_plan)
        target_idx = plan_order.index(target_plan)
        return target_idx > current_idx
    except ValueError:
        return False


def get_overage_price(plan_name: str) -> Optional[float]:
    """
    Get overage price per certificate for a plan.
    
    Args:
        plan_name: Plan identifier
        
    Returns:
        Overage price in EUR or None if no overage allowed
        
    Example:
        >>> get_overage_price('starter')
        3.0
        >>> get_overage_price('free')
        None
    """
    plan = get_plan(plan_name)
    return plan.get('overage_price_eur') if plan else None


def get_single_cert_price(plan_name: str) -> Optional[float]:
    """
    Get one-off certificate price for a plan.
    
    Args:
        plan_name: Plan identifier
        
    Returns:
        Single certificate price in EUR or None if not available
        
    Example:
        >>> get_single_cert_price('free')
        7.0
        >>> get_single_cert_price('starter')
        5.0
    """
    plan = get_plan(plan_name)
    return plan.get('single_cert_price_eur') if plan else None


def get_stripe_price_id(plan_name: str, price_type: str = 'monthly') -> Optional[str]:
    """
    Get Stripe price ID for a plan and price type.
    
    Args:
        plan_name: Plan identifier
        price_type: Type of price ('monthly', 'overage', 'single_cert')
        
    Returns:
        Stripe price ID or None if not configured
        
    Example:
        >>> get_stripe_price_id('starter', 'monthly')
        'price_starter_month'
        >>> get_stripe_price_id('pro', 'overage') 
        'price_pro_over'
    """
    plan = get_plan(plan_name)
    if not plan:
        return None
    
    price_mapping = {
        'monthly': 'stripe_price_id',
        'overage': 'stripe_overage_price_id', 
        'single_cert': 'single_cert_price_id'
    }
    
    price_key = price_mapping.get(price_type)
    return plan.get(price_key) if price_key else None


def calculate_monthly_cost(plan_name: str, jobs_used: int) -> Dict[str, float]:
    """
    Calculate total monthly cost including base price and overage.
    
    Args:
        plan_name: Plan identifier
        jobs_used: Number of certificates used this month
        
    Returns:
        Dictionary with cost breakdown
        
    Example:
        >>> cost = calculate_monthly_cost('starter', 15)
        >>> print(f"Total: €{cost['total']}")
        Total: €29.0
    """
    plan = get_plan(plan_name)
    if not plan:
        return {'base': 0, 'overage': 0, 'total': 0, 'overage_count': 0}
    
    base_cost = plan['price_eur'] or 0
    jobs_included = plan['jobs_month']
    overage_price = plan['overage_price_eur'] or 0
    
    # Calculate overage
    if jobs_used > jobs_included and overage_price > 0:
        overage_count = jobs_used - jobs_included
        overage_cost = overage_count * overage_price
    else:
        overage_count = 0
        overage_cost = 0
    
    return {
        'base': base_cost,
        'overage': overage_cost, 
        'total': base_cost + overage_cost,
        'overage_count': overage_count
    }


def get_pdf_template_type(plan_name: str) -> str:
    """
    Get PDF template type for a plan.
    
    Args:
        plan_name: Plan identifier
        
    Returns:
        PDF template type identifier
        
    Example:
        >>> get_pdf_template_type('pro')
        'pro'
        >>> get_pdf_template_type('free')
        'free'
    """
    plan = get_plan(plan_name)
    return plan.get('pdf_template', 'free') if plan else 'free'


# Environment variables for Stripe configuration
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY") 
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Test mode detection
STRIPE_TEST_MODE = bool(STRIPE_SECRET_KEY and STRIPE_SECRET_KEY.startswith('sk_test_'))