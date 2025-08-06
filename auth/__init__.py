"""
Authentication module for ProofKit.

This module provides magic link authentication with PostgreSQL and DynamoDB.
"""

# Import existing auth components
from .magic import auth_handler, AuthMiddleware, get_current_user, require_auth, require_qa

__all__ = [
    "auth_handler",
    "AuthMiddleware",
    "get_current_user",
    "require_auth",
    "require_qa"
] 