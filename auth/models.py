"""
Authentication models for ProofKit.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserRole(str, Enum):
    """User roles for role-based access control."""
    OPERATOR = "op"
    QA = "qa"


class User(BaseModel):
    """User model for authentication."""
    email: EmailStr
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    plan: str = "free"  # Pricing plan: free, starter, pro, business, enterprise
    
    class Config:
        use_enum_values = True


class MagicLinkRequest(BaseModel):
    """Request model for magic link generation."""
    email: EmailStr
    role: UserRole = UserRole.OPERATOR


class MagicLinkResponse(BaseModel):
    """Response model for magic link generation."""
    message: str
    expires_in: int  # seconds


class AuthToken(BaseModel):
    """JWT token model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds 