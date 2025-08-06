"""
Tests for M13 Authentication and QA Approval system.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from auth.models import User, UserRole, MagicLinkRequest, MagicLinkResponse, AuthToken
from auth.magic import MagicLinkAuth, AuthMiddleware, get_current_user, require_auth, require_qa


class TestAuthModels:
    """Test authentication models."""
    
    def test_user_role_enum(self):
        """Test UserRole enum values."""
        assert UserRole.OPERATOR == "op"
        assert UserRole.QA == "qa"
    
    def test_user_model(self):
        """Test User model creation."""
        user = User(
            email="test@example.com",
            role=UserRole.OPERATOR,
            created_at=datetime.now(timezone.utc)
        )
        assert user.email == "test@example.com"
        assert user.role == UserRole.OPERATOR
    
    def test_magic_link_request(self):
        """Test MagicLinkRequest model."""
        request = MagicLinkRequest(
            email="test@example.com",
            role=UserRole.QA
        )
        assert request.email == "test@example.com"
        assert request.role == UserRole.QA


class TestMagicLinkAuth:
    """Test magic link authentication."""
    
    def setup_method(self):
        """Set up test environment."""
        self.auth = MagicLinkAuth()
        self.temp_dir = tempfile.mkdtemp()
        self.auth.storage_dir = Path(self.temp_dir)
        # Clear in-memory storage
        from auth.magic import MAGIC_LINKS
        MAGIC_LINKS.clear()
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_magic_link(self):
        """Test magic link generation."""
        token = self.auth.generate_magic_link("test@example.com", UserRole.OPERATOR)
        assert len(token) > 32  # Should be a secure random token
        # Check that the token was stored (we can't access MAGIC_LINKS directly in test)
        link_data = self.auth.validate_magic_link(token)
        assert link_data is not None
    
    def test_validate_magic_link(self):
        """Test magic link validation."""
        # Generate a valid link
        token = self.auth.generate_magic_link("test@example.com", UserRole.QA)
        
        # Validate it
        link_data = self.auth.validate_magic_link(token)
        assert link_data is not None
        assert link_data["email"] == "test@example.com"
        assert link_data["role"] == UserRole.QA
        
        # Should be marked as used
        assert link_data["used"] is True
    
    def test_validate_expired_link(self):
        """Test expired magic link validation."""
        # Generate a link
        token = self.auth.generate_magic_link("test@example.com", UserRole.OPERATOR)
        
        # Clear in-memory storage to force reload from file
        from auth.magic import MAGIC_LINKS
        if token in MAGIC_LINKS:
            del MAGIC_LINKS[token]
        
        # Manually expire it by modifying the stored file
        import json
        from datetime import datetime, timezone
        file_path = self.auth.storage_dir / f"{token}.json"
        if file_path.exists():
            with open(file_path, 'r') as f:
                data = json.load(f)
            data["expires_at"] = "2020-01-01T00:00:00+00:00"
            with open(file_path, 'w') as f:
                json.dump(data, f)
        
        # Should not validate
        link_data = self.auth.validate_magic_link(token)
        assert link_data is None
    
    def test_validate_used_link(self):
        """Test used magic link validation."""
        # Generate and use a link
        token = self.auth.generate_magic_link("test@example.com", UserRole.OPERATOR)
        self.auth.validate_magic_link(token)
        
        # Should not validate again
        link_data = self.auth.validate_magic_link(token)
        assert link_data is None
    
    def test_create_jwt_token(self):
        """Test JWT token creation."""
        token = self.auth.create_jwt_token("test@example.com", UserRole.QA)
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_verify_jwt_token(self):
        """Test JWT token verification."""
        # Create a token
        original_token = self.auth.create_jwt_token("test@example.com", UserRole.OPERATOR)
        
        # Verify it
        payload = self.auth.verify_jwt_token(original_token)
        assert payload is not None
        assert payload["sub"] == "test@example.com"
        assert payload["role"] == UserRole.OPERATOR
    
    def test_verify_invalid_token(self):
        """Test invalid JWT token verification."""
        payload = self.auth.verify_jwt_token("invalid.token.here")
        assert payload is None


class TestAuthMiddleware:
    """Test authentication middleware."""
    
    def setup_method(self):
        """Set up test environment."""
        self.auth_handler = MagicLinkAuth()
        self.middleware = AuthMiddleware(MagicMock(), self.auth_handler)
    
    def test_should_skip_auth(self):
        """Test authentication skip logic."""
        # Should skip these paths
        assert self.middleware._should_skip_auth("/health") is True
        assert self.middleware._should_skip_auth("/auth/login") is True
        assert self.middleware._should_skip_auth("/static/css/style.css") is True
        assert self.middleware._should_skip_auth("/docs") is True
        
        # Should not skip these paths
        assert self.middleware._should_skip_auth("/") is False
        assert self.middleware._should_skip_auth("/api/compile") is False
    
    def test_extract_token_from_header(self):
        """Test token extraction from Authorization header."""
        request = MagicMock()
        request.headers = {"Authorization": "Bearer test.token.here"}
        
        token = self.middleware._extract_token(request)
        assert token == "test.token.here"
    
    def test_extract_token_from_cookie(self):
        """Test token extraction from cookie."""
        request = MagicMock()
        request.headers = {}
        request.cookies = {"auth_token": "test.token.here"}
        
        token = self.middleware._extract_token(request)
        assert token == "test.token.here"


class TestAuthFunctions:
    """Test authentication utility functions."""
    
    def test_get_current_user(self):
        """Test getting current user from request state."""
        request = MagicMock()
        request.state.user = User(
            email="test@example.com",
            role=UserRole.QA,
            created_at=datetime.now(timezone.utc)
        )
        
        user = get_current_user(request)
        assert user is not None
        assert user.email == "test@example.com"
    
    def test_get_current_user_none(self):
        """Test getting current user when not authenticated."""
        request = MagicMock()
        request.state = MagicMock()
        delattr(request.state, 'user')
        
        user = get_current_user(request)
        assert user is None
    
    def test_require_auth_authenticated(self):
        """Test require_auth with authenticated user."""
        request = MagicMock()
        request.state.user = User(
            email="test@example.com",
            role=UserRole.OPERATOR,
            created_at=datetime.now(timezone.utc)
        )
        
        user = require_auth(request)
        assert user.email == "test@example.com"
    
    def test_require_auth_unauthenticated(self):
        """Test require_auth with unauthenticated user."""
        request = MagicMock()
        request.state = MagicMock()
        delattr(request.state, 'user')
        
        with pytest.raises(Exception):  # Should raise HTTPException
            require_auth(request)
    
    def test_require_qa_with_qa_role(self):
        """Test require_qa with QA role."""
        request = MagicMock()
        request.state.user = User(
            email="qa@example.com",
            role=UserRole.QA,
            created_at=datetime.now(timezone.utc)
        )
        
        user = require_qa(request)
        assert user.role == UserRole.QA
    
    def test_require_qa_with_operator_role(self):
        """Test require_qa with operator role (should fail)."""
        request = MagicMock()
        request.state.user = User(
            email="op@example.com",
            role=UserRole.OPERATOR,
            created_at=datetime.now(timezone.utc)
        )
        
        with pytest.raises(Exception):  # Should raise HTTPException
            require_qa(request)


if __name__ == "__main__":
    pytest.main([__file__]) 