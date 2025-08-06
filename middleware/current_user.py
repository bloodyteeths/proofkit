"""
Current User Middleware

This middleware extracts JWT tokens from requests and populates the current user
context for authenticated requests in the ProofKit application.

Example usage:
    app.add_middleware(BaseHTTPMiddleware, dispatch=current_user_middleware)
    
    # In route handlers:
    current_user = get_current_user_from_context(request)
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from auth.magic import auth_handler
from auth.models import User, UserRole
from core.logging import get_logger
from middleware.quota import load_user_quota_data

logger = get_logger(__name__)


class CurrentUserMiddleware(BaseHTTPMiddleware):
    """Middleware for extracting and validating JWT tokens."""
    
    def __init__(self, app):
        super().__init__(app)
        self.auth_handler = auth_handler
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and inject current user if JWT token is valid.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response from next handler with user context injected
        """
        # Skip authentication for certain paths
        if self._should_skip_auth(request.url.path):
            return await call_next(request)
        
        # Extract token from request
        token = self._extract_token(request)
        
        if token:
            try:
                # Verify JWT token
                payload = self.auth_handler.verify_jwt_token(token)
                
                if payload:
                    # Get user's current plan from quota system
                    try:
                        quota_data = load_user_quota_data(payload["sub"])
                        user_plan = quota_data.get('plan', 'free')
                    except Exception as e:
                        logger.warning(f"Failed to load quota data for {payload['sub']}: {e}")
                        user_plan = 'free'  # Default to free plan if lookup fails
                    
                    # Create user object and inject into request state
                    user = User(
                        email=payload["sub"],
                        role=UserRole(payload["role"]),
                        plan=user_plan
                    )
                    
                    # Store user in request state
                    request.state.current_user = user
                    request.state.is_authenticated = True
                    
                    logger.debug(f"Authenticated user: {user.email} ({user.role}, {user.plan})")
                else:
                    # Invalid token
                    request.state.current_user = None
                    request.state.is_authenticated = False
                    logger.debug("Invalid JWT token provided")
            
            except Exception as e:
                logger.error(f"Error processing JWT token: {e}")
                request.state.current_user = None
                request.state.is_authenticated = False
        else:
            # No token provided
            request.state.current_user = None
            request.state.is_authenticated = False
        
        # Continue processing request
        response = await call_next(request)
        return response
    
    def _should_skip_auth(self, path: str) -> bool:
        """
        Check if authentication should be skipped for this path.
        
        Args:
            path: Request path
            
        Returns:
            True if authentication should be skipped
        """
        skip_paths = {
            "/health",
            "/favicon.ico",
            "/robots.txt",
            "/sitemap.xml",
            "/api/signup",
            "/api/magic/consume",
            "/auth/login",
            "/auth/verify",
            "/static",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
        
        # Check for exact matches or path prefixes
        return any(
            path == skip_path or path.startswith(skip_path + "/")
            for skip_path in skip_paths
        )
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract JWT token from request headers or cookies.
        
        Args:
            request: FastAPI request object
            
        Returns:
            JWT token string if found, None otherwise
        """
        # Try Authorization header first (Bearer token)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        
        # Try cookie fallback
        token = request.cookies.get("auth_token")
        if token:
            return token
        
        # Try X-Auth-Token header (for API clients)
        token = request.headers.get("X-Auth-Token")
        if token:
            return token
        
        return None


def get_current_user_from_context(request: Request) -> Optional[User]:
    """
    Get current authenticated user from request context.
    
    Args:
        request: FastAPI request object
        
    Returns:
        User object if authenticated, None otherwise
        
    Example:
        @app.get("/protected")
        async def protected_route(request: Request):
            user = get_current_user_from_context(request)
            if not user:
                raise HTTPException(401, "Authentication required")
            return {"user": user.email}
    """
    return getattr(request.state, 'current_user', None)


def is_authenticated(request: Request) -> bool:
    """
    Check if current request is authenticated.
    
    Args:
        request: FastAPI request object
        
    Returns:
        True if authenticated, False otherwise
        
    Example:
        @app.get("/maybe-protected")
        async def maybe_protected_route(request: Request):
            if is_authenticated(request):
                return {"message": "Welcome back!"}
            else:
                return {"message": "Hello, guest!"}
    """
    return getattr(request.state, 'is_authenticated', False)


def require_authentication(request: Request) -> User:
    """
    Require authentication and return current user.
    Raises HTTPException if not authenticated.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Current authenticated user
        
    Raises:
        HTTPException: If not authenticated (401)
        
    Example:
        @app.get("/admin")
        async def admin_route(request: Request):
            user = require_authentication(request)
            return {"admin": user.email}
    """
    user = get_current_user_from_context(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_role(request: Request, required_role: UserRole) -> User:
    """
    Require authentication and specific role.
    
    Args:
        request: FastAPI request object
        required_role: Required user role
        
    Returns:
        Current authenticated user with required role
        
    Raises:
        HTTPException: If not authenticated (401) or insufficient permissions (403)
        
    Example:
        @app.get("/qa-only")
        async def qa_route(request: Request):
            user = require_role(request, UserRole.QA)
            return {"qa_user": user.email}
    """
    user = require_authentication(request)
    
    if user.role != required_role:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. {required_role.value.upper()} role required."
        )
    
    return user


# Convenience functions for common use cases
def require_qa_role(request: Request) -> User:
    """Require QA role for request."""
    return require_role(request, UserRole.QA)


def require_operator_role(request: Request) -> User:
    """Require Operator role for request."""
    return require_role(request, UserRole.OPERATOR)


# Instance for app registration
current_user_middleware = CurrentUserMiddleware