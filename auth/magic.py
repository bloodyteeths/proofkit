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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import jwt
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .models import User, UserRole, MagicLinkRequest, MagicLinkResponse, AuthToken

logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
MAGIC_LINK_EXPIRY_MINUTES = 15

# Email configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@proofkit.com")
# Enable development mode if no email credentials are provided
EMAIL_DEV_MODE = os.environ.get("EMAIL_DEV_MODE", "true").lower() == "true"

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
        """Send magic link email via Amazon SES."""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = FROM_EMAIL
            msg['To'] = email
            msg['Subject'] = f"ProofKit Login - {role.value.upper()} Access"
            
            # Create verification URL
            base_url = os.environ.get("BASE_URL", "http://localhost:8000")
            verify_url = f"{base_url}/auth/verify?token={magic_link}"
            
            # Email body
            body = f"""
            <html>
            <body>
                <h2>ProofKit Authentication</h2>
                <p>You requested access to ProofKit with {role.value.upper()} privileges.</p>
                <p>Click the link below to verify your email and access the system:</p>
                <p><a href="{verify_url}">{verify_url}</a></p>
                <p>This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes.</p>
                <p>If you didn't request this access, please ignore this email.</p>
                <hr>
                <p><small>ProofKit - Quality Control Validation System</small></p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            if SMTP_USERNAME and SMTP_PASSWORD and not EMAIL_DEV_MODE:
                # Production mode - send real email
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
                server.quit()
                logger.info(f"Magic link email sent to {email}")
                return True
            else:
                # Development mode - log the link and show it in response
                logger.info(f"Magic link for {email}: {verify_url}")
                # Store the link temporarily for development access
                self._store_dev_link(email, verify_url)
                return True
                
        except Exception as e:
            logger.error(f"Failed to send magic link email to {email}: {e}")
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
                # Inject user state into request
                request.state.user = User(
                    email=payload["sub"],
                    role=UserRole(payload["role"]),
                    created_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
                    last_login=datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
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
                last_login=datetime.now(timezone.utc)
            )
        elif fake_role == "op":
            return User(
                email="test-op@example.com", 
                role=UserRole.OPERATOR,
                created_at=datetime.now(timezone.utc),
                last_login=datetime.now(timezone.utc)
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