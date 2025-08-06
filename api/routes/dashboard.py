"""
Dashboard API Routes

This module provides dashboard endpoints for user metrics, recent jobs,
and subscription information for the ProofKit dashboard system.

Example usage:
    GET /api/dashboard - Get user dashboard metrics and recent jobs
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.magic import get_current_user, require_auth
from auth.models import User
from core.db import get_recent_jobs
from core.logging import get_logger
from middleware.quota import load_user_quota_data, get_user_usage_summary
from core.billing import get_plan

logger = get_logger(__name__)

# Create router for dashboard endpoints
router = APIRouter(prefix="/api", tags=["dashboard"])


class DashboardResponse(BaseModel):
    """Response model for dashboard data."""
    user: Dict[str, Any]
    plan: Dict[str, Any]
    jobs_this_month: int
    jobs_limit: int
    next_reset_at: str
    recent_jobs: List[Dict[str, Any]]
    usage_summary: Dict[str, Any]


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(current_user: User = Depends(require_auth)) -> DashboardResponse:
    """
    Get user dashboard with metrics, plan info, and recent jobs.
    
    Args:
        current_user: Currently authenticated user
        
    Returns:
        Dashboard data with user metrics and recent jobs
        
    Example:
        GET /api/dashboard
        Authorization: Bearer <jwt_token>
        
        Response:
        {
            "user": {"email": "user@example.com", "plan": "free"},
            "plan": {"name": "Free", "jobs_month": 2},
            "jobs_this_month": 1,
            "jobs_limit": 2,
            "next_reset_at": "2025-09-01T00:00:00Z",
            "recent_jobs": [...],
            "usage_summary": {...}
        }
    """
    try:
        # Get user quota and usage data
        quota_data = load_user_quota_data(current_user.email)
        usage_summary = get_user_usage_summary(current_user.email)
        
        # Get plan information
        user_plan = quota_data.get('plan', 'free')
        plan_data = get_plan(user_plan)
        
        if not plan_data:
            logger.error(f"Invalid plan for user {current_user.email}: {user_plan}")
            plan_data = get_plan('free')  # Fallback to free plan
        
        # Calculate current month usage
        current_month_data = quota_data.get('current_month', {})
        jobs_this_month = current_month_data.get('certificates_compiled', 0)
        
        # Determine jobs limit based on plan
        if user_plan == 'free':
            # Free plan has lifetime limit of 2 certificates
            total_certificates = quota_data.get('total_certificates', 0)
            jobs_limit = 2
            jobs_remaining = max(0, jobs_limit - total_certificates)
            jobs_this_month = total_certificates  # Show total usage for free plan
        else:
            # Paid plans have monthly limits
            jobs_limit = plan_data.get('jobs_month', 0)
            jobs_remaining = max(0, jobs_limit - jobs_this_month)
        
        # Calculate next reset date (first day of next month)
        now = datetime.now(timezone.utc)
        if now.month == 12:
            next_reset = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_reset = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        
        # Get recent jobs for the user
        try:
            recent_jobs = await get_recent_jobs(current_user.email, limit=10)
        except Exception as e:
            logger.warning(f"Failed to get recent jobs for {current_user.email}: {e}")
            recent_jobs = []
        
        # Prepare user data
        user_data = {
            "email": current_user.email,
            "role": current_user.role,
            "plan": user_plan,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None
        }
        
        # Prepare plan data
        plan_response = {
            "name": plan_data.get('name', 'Free'),
            "tier": user_plan,
            "jobs_month": jobs_limit,
            "jobs_remaining": jobs_remaining,
            "price_eur": plan_data.get('price_eur', 0),
            "features": plan_data.get('features', []),
            "is_free": user_plan == 'free',
            "overage_available": bool(plan_data.get('overage_price_eur', 0) > 0)
        }
        
        logger.info(f"Dashboard data retrieved for {current_user.email}")
        
        return DashboardResponse(
            user=user_data,
            plan=plan_response,
            jobs_this_month=jobs_this_month,
            jobs_limit=jobs_limit,
            next_reset_at=next_reset.isoformat(),
            recent_jobs=recent_jobs,
            usage_summary=usage_summary
        )
        
    except Exception as e:
        logger.error(f"Dashboard error for {current_user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error retrieving dashboard data"
        )


@router.get("/dashboard/usage")
async def get_usage_details(current_user: User = Depends(require_auth)) -> Dict[str, Any]:
    """
    Get detailed usage information for the current user.
    
    Args:
        current_user: Currently authenticated user
        
    Returns:
        Detailed usage information
        
    Example:
        GET /api/dashboard/usage
        Authorization: Bearer <jwt_token>
    """
    try:
        usage_summary = get_user_usage_summary(current_user.email)
        quota_data = load_user_quota_data(current_user.email)
        
        # Add historical data (last 6 months)
        usage_history = []
        now = datetime.now(timezone.utc)
        
        for i in range(6):
            # Calculate month offset
            month_date = now.replace(day=1) - timedelta(days=32 * i)
            month_key = month_date.strftime('%Y-%m')
            
            # This would need to be enhanced to track historical data
            # For now, we'll return current month data
            if month_key == quota_data.get('current_month', {}).get('month'):
                usage_count = quota_data.get('current_month', {}).get('certificates_compiled', 0)
            else:
                usage_count = 0
            
            usage_history.append({
                "month": month_key,
                "certificates_compiled": usage_count,
                "month_name": month_date.strftime('%B %Y')
            })
        
        return {
            "current_usage": usage_summary,
            "quota_data": quota_data,
            "usage_history": list(reversed(usage_history))  # Most recent first
        }
        
    except Exception as e:
        logger.error(f"Usage details error for {current_user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error retrieving usage details"
        )


@router.get("/dashboard/recent-jobs")
async def get_recent_jobs_endpoint(
    current_user: User = Depends(require_auth),
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recent jobs for the current user.
    
    Args:
        current_user: Currently authenticated user
        limit: Maximum number of jobs to return (default 10)
        
    Returns:
        List of recent jobs
        
    Example:
        GET /api/dashboard/recent-jobs?limit=5
        Authorization: Bearer <jwt_token>
    """
    try:
        if limit > 50:  # Reasonable upper bound
            limit = 50
        
        recent_jobs = await get_recent_jobs(current_user.email, limit=limit)
        
        logger.info(f"Retrieved {len(recent_jobs)} recent jobs for {current_user.email}")
        
        return recent_jobs
        
    except Exception as e:
        logger.error(f"Recent jobs error for {current_user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error retrieving recent jobs"
        )