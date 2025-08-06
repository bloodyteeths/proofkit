"""
Authentication API Routes

This module provides authentication endpoints for user signup, magic link consumption,
and login/logout functionality for the ProofKit authentication system.

Example usage:
    POST /api/signup - Create user and send magic link
    POST /api/magic/consume - Consume magic link token and get JWT
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from auth.magic import auth_handler, get_current_user, require_auth
from auth.models import User, UserRole, MagicLinkRequest, MagicLinkResponse, AuthToken
from core.logging import get_logger
from middleware.quota import load_user_quota_data, update_user_plan

logger = get_logger(__name__)

# Create router for auth endpoints
router = APIRouter(prefix="/api", tags=["auth"])


class SignupRequest(BaseModel):
    """Request model for user signup."""
    email: EmailStr
    plan: Optional[str] = "free"
    role: UserRole = UserRole.OPERATOR


class MagicLinkConsumeRequest(BaseModel):
    """Request model for magic link consumption."""
    token: str


class AuthResponse(BaseModel):
    """Response model for authentication success."""
    user: Dict[str, Any]
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=MagicLinkResponse)
async def signup(request: SignupRequest) -> MagicLinkResponse:
    """
    Create user account and send magic link for authentication.
    
    Args:
        request: Signup request with email and optional plan
        
    Returns:
        Magic link response with confirmation message
        
    Example:
        POST /api/signup
        {
            "email": "user@example.com",
            "plan": "free",
            "role": "op"
        }
    """
    try:
        # Validate plan if provided
        valid_plans = ["free", "starter", "pro", "business", "enterprise"]
        if request.plan and request.plan not in valid_plans:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan. Must be one of: {', '.join(valid_plans)}"
            )
        
        # Check if user already exists and update plan if needed
        user_email = str(request.email)
        quota_data = load_user_quota_data(user_email)
        
        # Update plan if different
        if request.plan and quota_data.get('plan') != request.plan:
            update_user_plan(user_email, request.plan)
            logger.info(f"Updated plan for existing user {user_email}: {request.plan}")
        
        # Generate magic link
        magic_token = auth_handler.generate_magic_link(user_email, request.role)
        
        # Send magic link email
        email_sent = auth_handler.send_magic_link_email(
            user_email, 
            magic_token, 
            request.role
        )
        
        if not email_sent:
            logger.error(f"Failed to send magic link email to {user_email}")
            raise HTTPException(
                status_code=500,
                detail="Failed to send authentication email"
            )
        
        logger.info(f"Signup successful for {user_email} with plan {request.plan}")
        
        return MagicLinkResponse(
            message=f"Authentication email sent to {user_email}. Check your inbox and click the link to continue.",
            expires_in=15 * 60  # 15 minutes in seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error for {request.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during signup"
        )


@router.post("/magic/consume", response_model=AuthResponse)
async def consume_magic_link(request: MagicLinkConsumeRequest) -> AuthResponse:
    """
    Consume magic link token and return JWT access token.
    
    Args:
        request: Magic link consumption request with token
        
    Returns:
        Authentication response with JWT token and user data
        
    Example:
        POST /api/magic/consume
        {
            "token": "abc123..."
        }
    """
    try:
        # Validate magic link token
        link_data = auth_handler.validate_magic_link(request.token)
        
        if not link_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired magic link token"
            )
        
        user_email = link_data["email"]
        user_role = UserRole(link_data["role"])
        
        # Create JWT token
        access_token = auth_handler.create_jwt_token(user_email, user_role)
        
        # Get user quota data for plan information
        quota_data = load_user_quota_data(user_email)
        user_plan = quota_data.get('plan', 'free')
        
        # Create user object
        user_data = {
            "email": user_email,
            "role": user_role,
            "plan": user_plan,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Magic link consumed successfully for {user_email}")
        
        return AuthResponse(
            user=user_data,
            access_token=access_token,
            token_type="bearer"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Magic link consumption error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during authentication"
        )


@router.post("/logout")
async def logout(current_user: User = Depends(require_auth)) -> JSONResponse:
    """
    Logout current user (mainly for audit logging).
    
    Args:
        current_user: Currently authenticated user
        
    Returns:
        Success response
        
    Example:
        POST /api/logout
        Authorization: Bearer <jwt_token>
    """
    try:
        logger.info(f"User logged out: {current_user.email}")
        
        return JSONResponse(
            content={
                "message": "Logged out successfully",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Logout error for {current_user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during logout"
        )


@router.get("/me")
async def get_current_user_info(current_user: User = Depends(require_auth)) -> Dict[str, Any]:
    """
    Get current authenticated user information.
    
    Args:
        current_user: Currently authenticated user
        
    Returns:
        User information with plan and quota data
        
    Example:
        GET /api/me
        Authorization: Bearer <jwt_token>
    """
    try:
        # Get detailed quota information
        quota_data = load_user_quota_data(current_user.email)
        
        return {
            "email": current_user.email,
            "role": current_user.role,
            "plan": current_user.plan,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
            "quota": {
                "plan": quota_data.get('plan', 'free'),
                "current_month": quota_data.get('current_month', {}),
                "total_certificates": quota_data.get('total_certificates', 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Get user info error for {current_user.email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error getting user information"
        )