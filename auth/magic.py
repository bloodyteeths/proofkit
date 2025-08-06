"""
Magic link authentication system for ProofKit.

This module provides:
- Magic link generation and validation
- JWT token creation and verification
- Role-based access control (Operator vs QA)
- Email sending via Amazon SES
"""

import os
import secrets
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pathlib import Path
import httpx
import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .models import User, UserRole, MagicLinkRequest, MagicLinkResponse, AuthToken

logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
MAGIC_LINK_EXPIRY_MINUTES = 15

# Email configuration - moved to function level to ensure runtime evaluation

# Storage for magic links (in production, use Redis or database)
MAGIC_LINKS: Dict[str, Dict[str, Any]] = {}


class MagicLinkAuth:
    """Magic link authentication handler."""
    
    def __init__(self):
        self.storage_dir = Path("storage/auth")
        self.storage_dir.mkdir(exist_ok=True)
    
    def generate_magic_link(self, email: str, role: UserRole = UserRole.OPERATOR) -> str:
        """Generate a magic link for authentication."""
        # Create a secure random token
        token = secrets.token_urlsafe(32)
        
        # Store the magic link data
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)
        
        MAGIC_LINKS[token] = {
            "email": email,
            "role": role,
            "expires_at": expires_at.isoformat(),
            "used": False
        }
        
        # Save to persistent storage
        self._save_magic_link(token, MAGIC_LINKS[token])
        
        logger.info(f"Generated magic link for {email} with role {role}")
        return token
    
    def validate_magic_link(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a magic link token."""
        if token not in MAGIC_LINKS:
            # Try to load from persistent storage
            stored_data = self._load_magic_link(token)
            if not stored_data:
                return None
            MAGIC_LINKS[token] = stored_data
        
        link_data = MAGIC_LINKS[token]
        
        # Check if already used
        if link_data.get("used", False):
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(link_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return None
        
        # Mark as used
        link_data["used"] = True
        self._save_magic_link(token, link_data)
        
        return link_data
    
    def create_jwt_token(self, email: str, role: UserRole) -> str:
        """Create a JWT token for authenticated user."""
        payload = {
            "sub": email,
            "role": role,
            "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
            "iat": datetime.now(timezone.utc)
        }
        
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid JWT token")
            return None
    
    def send_magic_link_email(self, email: str, magic_link: str, role: UserRole) -> bool:
        """Send magic link email via Postmark."""
        try:
            # Ensure role is a UserRole instance
            if isinstance(role, str):
                role = UserRole(role)
            # Create verification URL
            base_url = os.environ.get("BASE_URL", "https://www.proofkit.net")
            verify_url = f"{base_url}/auth/verify?token={magic_link}"
            
            # Get Postmark configuration at runtime
            postmark_token = os.environ.get('POSTMARK_TOKEN', os.environ.get('POSTMARK_API_TOKEN', ''))
            from_email = os.environ.get('FROM_EMAIL', 'no-reply@proofkit.net')
            reply_to = os.environ.get('REPLY_TO_EMAIL', 'support@proofkit.net')
            
            # Evaluate dev mode at runtime
            email_dev_mode = os.environ.get("EMAIL_DEV_MODE", "false").lower() == "true"
            
            # Log configuration for debugging
            logger.info(f"Email config - Token present: {bool(postmark_token)}, Token prefix: {postmark_token[:5] if postmark_token else 'None'}, Dev mode: {email_dev_mode}, From: {from_email}")
            
            # Check if we should use Postmark or development mode
            # Always use Postmark if token is present and dev mode is not explicitly enabled
            if postmark_token and not email_dev_mode:
                # Production mode - send via Postmark
                html_body = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>ProofKit Magic Link</title>
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                        <h1 style="color: white; margin: 0 0 20px 0; text-align: center;">
                            🔐 ProofKit Authentication
                        </h1>
                        
                        <div style="background: white; padding: 30px; border-radius: 8px;">
                            <p style="font-size: 16px; color: #374151; margin: 20px 0;">
                                You requested access to ProofKit with {role.value.upper()} privileges.
                            </p>
                            
                            <p style="font-size: 16px; color: #374151; margin: 20px 0;">
                                Click the button below to verify your email and access the system:
                            </p>
                            
                            <div style="text-align: center; margin: 30px 0;">
                                <a href="{verify_url}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                                    🔓 Access ProofKit
                                </a>
                            </div>
                            
                            <p style="font-size: 14px; color: #6b7280; margin-top: 20px;">
                                Or copy and paste this link:<br>
                                <code style="background: #f3f4f6; padding: 4px 8px; border-radius: 3px; word-break: break-all;">{verify_url}</code>
                            </p>
                            
                            <p style="font-size: 14px; color: #dc2626; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                                ⏱️ This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes.
                            </p>
                            
                            <p style="font-size: 12px; color: #6b7280; margin-top: 20px;">
                                If you didn't request this access, please ignore this email.
                            </p>
                        </div>
                        
                        <p style="font-size: 12px; color: rgba(255,255,255,0.8); text-align: center; margin-top: 20px;">
                            ProofKit - Industrial Temperature Validation<br>
                            © 2024 ProofKit. All rights reserved.
                        </p>
                    </div>
                </body>
                </html>
                """
                
                text_body = f"""
                🔐 ProofKit Magic Link Authentication
                
                You requested access to ProofKit with {role.value.upper()} privileges.
                
                Click this link to verify your email and access the system:
                {verify_url}
                
                This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes.
                
                If you didn't request this access, please ignore this email.
                
                ---
                ProofKit - Industrial Temperature Validation
                © 2024 ProofKit. All rights reserved.
                """
                
                # Send via Postmark API
                url = "https://api.postmarkapp.com/email"
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": postmark_token
                }
                
                data = {
                    "From": from_email,
                    "To": email,
                    "ReplyTo": reply_to,
                    "Subject": f"ProofKit Login - {role.value.upper()} Access",
                    "HtmlBody": html_body,
                    "TextBody": text_body,
                    "MessageStream": "outbound"
                }
                
                logger.info(f"Sending Postmark email to {email} with token starting with {postmark_token[:10] if postmark_token else 'MISSING'}...")
                
                with httpx.Client() as client:
                    response = client.post(url, headers=headers, json=data)
                
                logger.info(f"Postmark API response: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Magic link email sent to {email} via Postmark. MessageID: {result.get('MessageID')}")
                    return True
                else:
                    logger.error(f"Postmark API error: {response.status_code} - {response.text}")
                    # Only fall back to dev mode if explicitly enabled
                    if email_dev_mode:
                        logger.info(f"Falling back to development mode. Magic link for {email}: {verify_url}")
                        self._store_dev_link(email, verify_url)
                    return False  # Return False if Postmark fails in production
            else:
                # Development mode - log the link and show it in response
                logger.info(f"Development mode or no Postmark token. Magic link for {email}: {verify_url}")
                # Store the link temporarily for development access
                self._store_dev_link(email, verify_url)
                return True
                
        except Exception as e:
            logger.error(f"Failed to send magic link email to {email}: {e}")
            # Only store dev link if in dev mode
            if email_dev_mode:
                try:
                    self._store_dev_link(email, verify_url)
                    return True
                except:
                    pass
            return False
    
    def _store_dev_link(self, email: str, verify_url: str) -> None:
        """Store development magic link for temporary access."""
        try:
            dev_links_file = self.storage_dir / "dev_links.json"
            dev_links = {}
            
            if dev_links_file.exists():
                with open(dev_links_file, 'r') as f:
                    dev_links = json.load(f)
            
            # Store with timestamp for cleanup
            dev_links[email] = {
                "url": verify_url,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)).isoformat()
            }
            
            with open(dev_links_file, 'w') as f:
                json.dump(dev_links, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to store dev link for {email}: {e}")
    
    def get_dev_link(self, email: str) -> Optional[str]:
        """Get development magic link for an email."""
        try:
            dev_links_file = self.storage_dir / "dev_links.json"
            if not dev_links_file.exists():
                return None
                
            with open(dev_links_file, 'r') as f:
                dev_links = json.load(f)
            
            if email in dev_links:
                link_data = dev_links[email]
                expires_at = datetime.fromisoformat(link_data["expires_at"])
                
                if datetime.now(timezone.utc) < expires_at:
                    return link_data["url"]
                else:
                    # Remove expired link
                    del dev_links[email]
                    with open(dev_links_file, 'w') as f:
                        json.dump(dev_links, f, indent=2)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get dev link for {email}: {e}")
            return None
    
    def _save_magic_link(self, token: str, data: Dict[str, Any]) -> None:
        """Save magic link data to persistent storage."""
        try:
            file_path = self.storage_dir / f"{token}.json"
            with open(file_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Failed to save magic link {token}: {e}")
    
    def _load_magic_link(self, token: str) -> Optional[Dict[str, Any]]:
        """Load magic link data from persistent storage."""
        try:
            file_path = self.storage_dir / f"{token}.json"
            if file_path.exists():
                with open(file_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load magic link {token}: {e}")
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT authentication."""
    
    def __init__(self, app, auth_handler: MagicLinkAuth):
        super().__init__(app)
        self.auth_handler = auth_handler
    
    async def dispatch(self, request: Request, call_next):
        """Process request and inject user state if authenticated."""
        # Skip authentication for certain paths
        if self._should_skip_auth(request.url.path):
            return await call_next(request)
        
        # Extract token from Authorization header or cookie
        token = self._extract_token(request)
        
        if token:
            payload = self.auth_handler.verify_jwt_token(token)
            if payload:
                # Get user's current plan from quota system
                try:
                    from middleware.quota import load_user_quota_data
                    quota_data = load_user_quota_data(payload["sub"])
                    user_plan = quota_data.get('plan', 'free')
                except Exception:
                    user_plan = 'free'  # Default to free plan if lookup fails
                
                # Inject user state into request
                request.state.user = User(
                    email=payload["sub"],
                    role=UserRole(payload["role"]),
                    created_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
                    last_login=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
                    plan=user_plan
                )
        
        response = await call_next(request)
        return response
    
    def _should_skip_auth(self, path: str) -> bool:
        """Check if authentication should be skipped for this path."""
        skip_paths = {
            "/health",
            "/auth/login",
            "/auth/verify",
            "/static",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
        
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request."""
        # Try Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Try cookie
        return request.cookies.get("auth_token")


# Global auth handler instance
auth_handler = MagicLinkAuth()


def get_current_user(request: Request) -> Optional[User]:
    """Get current authenticated user from request state."""
    # Test hook for automated testing
    fake_role = os.environ.get("PK_TEST_FAKE_ROLE")
    if fake_role:
        if fake_role == "qa":
            return User(
                email="test-qa@example.com",
                role=UserRole.QA,
                created_at=datetime.now(timezone.utc),
                last_login=datetime.now(timezone.utc),
                plan="free"
            )
        elif fake_role == "op":
            return User(
                email="test-op@example.com", 
                role=UserRole.OPERATOR,
                created_at=datetime.now(timezone.utc),
                last_login=datetime.now(timezone.utc),
                plan="free"
            )
    
    return getattr(request.state, 'user', None)


def require_auth(request: Request) -> User:
    """Require authentication - raise 401 if not authenticated."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_role(required_role: UserRole):
    """Decorator to require specific role."""
    def decorator(request: Request) -> User:
        user = require_auth(request)
        if user.role != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. {required_role.value.upper()} role required."
            )
        return user
    return decorator


def require_qa(request: Request) -> User:
    """Require QA role."""
    return require_role(UserRole.QA)(request)


def require_auth_redirect(request: Request) -> User:
    """Require authentication - redirect to login if not authenticated."""
    user = get_current_user(request)
    if not user:
        # Get the current URL for return redirect
        return_url = str(request.url)
        login_url = f"/auth/login?return_url={return_url}"
        raise HTTPException(
            status_code=302,
            detail="Redirect to login",
            headers={"Location": login_url}
        )
    return user


def require_role_redirect(required_role: UserRole):
    """Decorator to require specific role with redirect."""
    def decorator(request: Request) -> User:
        user = require_auth_redirect(request)
        if user.role != required_role:
            # Get the current URL for return redirect
            return_url = str(request.url)
            login_url = f"/auth/login?return_url={return_url}&error=insufficient_role"
            raise HTTPException(
                status_code=302,
                detail="Redirect to login",
                headers={"Location": login_url}
            )
        return user
    return decorator


def require_qa_redirect(request: Request) -> User:
    """Require QA role with redirect to login."""
    return require_role_redirect(UserRole.QA)(request) 