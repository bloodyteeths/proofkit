"""
Tests for PR-BE-DASH Authentication Flow

Tests for auth routes, dashboard endpoints, and JWT middleware functionality.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from api.routes.auth import router as auth_router
from api.routes.dashboard import router as dashboard_router
from auth.models import User, UserRole
from auth.magic import auth_handler
from middleware.current_user import CurrentUserMiddleware
from core.db import get_recent_jobs


@pytest.fixture
def app():
    """Create test FastAPI app with auth and dashboard routes."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.add_middleware(CurrentUserMiddleware)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_auth_handler():
    """Mock auth handler for testing."""
    with patch('api.routes.auth.auth_handler') as mock:
        yield mock


@pytest.fixture
def mock_quota_data():
    """Mock quota data for testing."""
    return {
        'user_email': 'test@example.com',
        'plan': 'free',
        'total_certificates': 1,
        'current_month': {
            'month': '2025-08',
            'certificates_compiled': 1,
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


class TestAuthRoutes:
    """Test authentication API routes."""
    
    def test_signup_success(self, client, mock_auth_handler):
        """Test successful user signup."""
        mock_auth_handler.generate_magic_link.return_value = "test_token_123"
        mock_auth_handler.send_magic_link_email.return_value = True
        
        with patch('api.routes.auth.load_user_quota_data') as mock_quota, \
             patch('api.routes.auth.update_user_plan') as mock_update_plan:
            
            mock_quota.return_value = {'plan': 'free'}
            
            response = client.post("/api/signup", json={
                "email": "test@example.com",
                "plan": "free",
                "role": "op"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "Authentication email sent" in data["message"]
            assert data["expires_in"] == 900  # 15 minutes
            
            mock_auth_handler.generate_magic_link.assert_called_once_with(
                "test@example.com", UserRole.OPERATOR
            )
            mock_auth_handler.send_magic_link_email.assert_called_once()
    
    def test_signup_invalid_plan(self, client):
        """Test signup with invalid plan."""
        response = client.post("/api/signup", json={
            "email": "test@example.com",
            "plan": "invalid_plan",
            "role": "op"
        })
        
        assert response.status_code == 400
        assert "Invalid plan" in response.json()["detail"]
    
    def test_signup_email_failure(self, client, mock_auth_handler):
        """Test signup when email sending fails."""
        mock_auth_handler.generate_magic_link.return_value = "test_token_123"
        mock_auth_handler.send_magic_link_email.return_value = False
        
        with patch('api.routes.auth.load_user_quota_data') as mock_quota:
            mock_quota.return_value = {'plan': 'free'}
            
            response = client.post("/api/signup", json={
                "email": "test@example.com",
                "plan": "free",
                "role": "op"
            })
            
            assert response.status_code == 500
            assert "Failed to send authentication email" in response.json()["detail"]
    
    def test_consume_magic_link_success(self, client, mock_auth_handler):
        """Test successful magic link consumption."""
        mock_link_data = {
            "email": "test@example.com",
            "role": "op",
            "expires_at": "2025-08-06T12:00:00Z",
            "used": False
        }
        
        mock_auth_handler.validate_magic_link.return_value = mock_link_data
        mock_auth_handler.create_jwt_token.return_value = "jwt_token_123"
        
        with patch('api.routes.auth.load_user_quota_data') as mock_quota:
            mock_quota.return_value = {'plan': 'starter'}
            
            response = client.post("/api/magic/consume", json={
                "token": "test_token_123"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "jwt_token_123"
            assert data["token_type"] == "bearer"
            assert data["user"]["email"] == "test@example.com"
            assert data["user"]["role"] == "op"
            assert data["user"]["plan"] == "starter"
    
    def test_consume_magic_link_invalid_token(self, client, mock_auth_handler):
        """Test magic link consumption with invalid token."""
        mock_auth_handler.validate_magic_link.return_value = None
        
        response = client.post("/api/magic/consume", json={
            "token": "invalid_token"
        })
        
        assert response.status_code == 400
        assert "Invalid or expired magic link token" in response.json()["detail"]
    
    def test_logout_success(self, client):
        """Test successful logout."""
        # Mock authenticated user
        with patch('api.routes.auth.require_auth') as mock_require_auth:
            mock_user = User(
                email="test@example.com",
                role=UserRole.OPERATOR,
                created_at=datetime.now(timezone.utc)
            )
            mock_require_auth.return_value = mock_user
            
            response = client.post("/api/logout")
            
            assert response.status_code == 200
            data = response.json()
            assert "Logged out successfully" in data["message"]
    
    def test_get_me_success(self, client, mock_quota_data):
        """Test getting current user information."""
        with patch('api.routes.auth.require_auth') as mock_require_auth, \
             patch('api.routes.auth.load_user_quota_data') as mock_quota:
            
            mock_user = User(
                email="test@example.com",
                role=UserRole.OPERATOR,
                plan="free",
                created_at=datetime.now(timezone.utc)
            )
            mock_require_auth.return_value = mock_user
            mock_quota.return_value = mock_quota_data
            
            response = client.get("/api/me")
            
            assert response.status_code == 200
            data = response.json()
            assert data["email"] == "test@example.com"
            assert data["role"] == "op"
            assert data["plan"] == "free"
            assert "quota" in data


class TestDashboardRoutes:
    """Test dashboard API routes."""
    
    @pytest.mark.asyncio
    async def test_get_dashboard_success(self, client, mock_quota_data):
        """Test successful dashboard data retrieval."""
        mock_jobs = [
            {
                "id": "job123",
                "spec_name": "Powder Coat Cure",
                "csv_filename": "test.csv",
                "pass_bool": True,
                "pdf_url": "/download/cert.pdf",
                "evidence_url": "/download/evidence.zip",
                "status": "completed",
                "created_at": "2025-08-06T10:00:00Z",
                "completed_at": "2025-08-06T10:05:00Z",
                "error_message": None,
                "metadata": {}
            }
        ]
        
        with patch('api.routes.dashboard.require_auth') as mock_require_auth, \
             patch('api.routes.dashboard.load_user_quota_data') as mock_quota, \
             patch('api.routes.dashboard.get_user_usage_summary') as mock_usage, \
             patch('api.routes.dashboard.get_plan') as mock_plan, \
             patch('api.routes.dashboard.get_recent_jobs') as mock_get_jobs:
            
            mock_user = User(
                email="test@example.com",
                role=UserRole.OPERATOR,
                plan="free",
                created_at=datetime.now(timezone.utc)
            )
            mock_require_auth.return_value = mock_user
            mock_quota.return_value = mock_quota_data
            mock_usage.return_value = {
                'plan': 'free',
                'total_used': 1,
                'total_limit': 2,
                'total_remaining': 1
            }
            mock_plan.return_value = {
                'name': 'Free',
                'jobs_month': 2,
                'price_eur': 0,
                'features': []
            }
            mock_get_jobs.return_value = mock_jobs
            
            response = client.get("/api/dashboard")
            
            assert response.status_code == 200
            data = response.json()
            assert data["user"]["email"] == "test@example.com"
            assert data["plan"]["name"] == "Free"
            assert data["jobs_this_month"] == 1
            assert data["jobs_limit"] == 2
            assert len(data["recent_jobs"]) == 1
            assert data["recent_jobs"][0]["pass_bool"] is True
    
    def test_get_usage_details_success(self, client, mock_quota_data):
        """Test getting detailed usage information."""
        with patch('api.routes.dashboard.require_auth') as mock_require_auth, \
             patch('api.routes.dashboard.get_user_usage_summary') as mock_usage, \
             patch('api.routes.dashboard.load_user_quota_data') as mock_quota:
            
            mock_user = User(
                email="test@example.com",
                role=UserRole.OPERATOR,
                plan="free",
                created_at=datetime.now(timezone.utc)
            )
            mock_require_auth.return_value = mock_user
            mock_usage.return_value = {'plan': 'free', 'total_used': 1}
            mock_quota.return_value = mock_quota_data
            
            response = client.get("/api/dashboard/usage")
            
            assert response.status_code == 200
            data = response.json()
            assert "current_usage" in data
            assert "quota_data" in data
            assert "usage_history" in data
    
    @pytest.mark.asyncio
    async def test_get_recent_jobs_success(self, client):
        """Test getting recent jobs."""
        mock_jobs = [
            {
                "id": "job123",
                "spec_name": "Test Spec",
                "pass_bool": True,
                "created_at": "2025-08-06T10:00:00Z"
            }
        ]
        
        with patch('api.routes.dashboard.require_auth') as mock_require_auth, \
             patch('api.routes.dashboard.get_recent_jobs') as mock_get_jobs:
            
            mock_user = User(
                email="test@example.com",
                role=UserRole.OPERATOR,
                plan="free",
                created_at=datetime.now(timezone.utc)
            )
            mock_require_auth.return_value = mock_user
            mock_get_jobs.return_value = mock_jobs
            
            response = client.get("/api/dashboard/recent-jobs?limit=5")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "job123"


class TestCurrentUserMiddleware:
    """Test JWT extraction middleware."""
    
    def test_middleware_extracts_bearer_token(self, app):
        """Test middleware extracts JWT from Authorization header."""
        with patch('middleware.current_user.auth_handler') as mock_auth, \
             patch('middleware.current_user.load_user_quota_data') as mock_quota:
            
            mock_auth.verify_jwt_token.return_value = {
                "sub": "test@example.com",
                "role": "op",
                "exp": 9999999999
            }
            mock_quota.return_value = {'plan': 'free'}
            
            client = TestClient(app)
            
            # Test endpoint that checks for user
            @app.get("/test-auth")
            async def test_auth(request):
                user = getattr(request.state, 'current_user', None)
                if user:
                    return {"authenticated": True, "email": user.email}
                return {"authenticated": False}
            
            response = client.get("/test-auth", headers={
                "Authorization": "Bearer test_jwt_token"
            })
            
            # Should extract token and verify it
            mock_auth.verify_jwt_token.assert_called_once_with("test_jwt_token")
    
    def test_middleware_skips_public_paths(self, app):
        """Test middleware skips authentication for public paths."""
        with patch('middleware.current_user.auth_handler') as mock_auth:
            client = TestClient(app)
            
            @app.get("/health")
            async def health():
                return {"status": "ok"}
            
            response = client.get("/health")
            
            assert response.status_code == 200
            # Should not attempt to verify token for public endpoints
            mock_auth.verify_jwt_token.assert_not_called()


class TestGetRecentJobs:
    """Test get_recent_jobs function."""
    
    @pytest.mark.asyncio
    async def test_get_recent_jobs_with_database(self):
        """Test getting recent jobs from database."""
        with patch('core.db.DATABASE_URL', 'postgresql://test'), \
             patch('core.db.get_db_session') as mock_session:
            
            # Mock database session and results
            mock_session_obj = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_obj
            
            # Mock user query
            mock_user_result = MagicMock()
            mock_user_result.scalar_one_or_none.return_value = MagicMock(id="user123")
            mock_session_obj.execute.return_value = mock_user_result
            
            # Mock jobs query
            mock_job = MagicMock()
            mock_job.id = "job123"
            mock_job.spec_name = "Test Spec"
            mock_job.csv_filename = "test.csv"
            mock_job.result_pass = True
            mock_job.pdf_url = "/cert.pdf"
            mock_job.evidence_url = "/evidence.zip"
            mock_job.status = "completed"
            mock_job.created_at = datetime.now(timezone.utc)
            mock_job.completed_at = datetime.now(timezone.utc)
            mock_job.error_message = None
            mock_job.metadata = {}
            
            mock_jobs_result = MagicMock()
            mock_jobs_result.scalars.return_value.all.return_value = [mock_job]
            
            # Return user result first, then jobs result
            mock_session_obj.execute.side_effect = [mock_user_result, mock_jobs_result]
            
            jobs = await get_recent_jobs("test@example.com", limit=5)
            
            assert len(jobs) == 1
            assert jobs[0]["id"] == "job123"
            assert jobs[0]["pass_bool"] is True
    
    @pytest.mark.asyncio
    async def test_get_recent_jobs_fallback_to_files(self):
        """Test fallback to file-based storage when database fails."""
        with patch('core.db.DATABASE_URL', ''), \
             patch('core.db._get_recent_jobs_from_files') as mock_file_jobs:
            
            mock_file_jobs.return_value = [
                {
                    "id": "file_job_123",
                    "spec_name": "File Spec",
                    "pass_bool": False,
                    "created_at": "2025-08-06T10:00:00Z"
                }
            ]
            
            jobs = await get_recent_jobs("test@example.com", limit=5)
            
            assert len(jobs) == 1
            assert jobs[0]["id"] == "file_job_123"
            assert jobs[0]["pass_bool"] is False
            mock_file_jobs.assert_called_once_with("test@example.com", 5)


if __name__ == "__main__":
    pytest.main([__file__])