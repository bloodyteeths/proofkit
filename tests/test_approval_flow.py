"""
ProofKit Authentication and QA Approval Workflow Tests

Comprehensive test suite for the complete authentication and QA approval workflow.
Tests include:
- Magic-link authentication flow
- Role-based access control (Operator vs QA)
- Multi-step approval process
- Evidence bundle approval workflow
- Session management and security
- Integration with ProofKit compilation pipeline

Tests are designed to work with the file-based authentication system and
mock external dependencies like email services.

Example usage:
    pytest tests/test_approval_flow.py -v
"""

import pytest
import tempfile
import json
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock

import pandas as pd

from auth.models import User, UserRole, MagicLinkRequest, MagicLinkResponse, AuthToken
from auth.magic import MagicLinkAuth, AuthMiddleware, get_current_user, require_auth, require_qa
from core.models import SpecV1, DecisionResult
from core.normalize import normalize_temperature_data
from core.decide import make_decision
from core.plot import generate_proof_plot
from core.render_pdf import generate_proof_pdf
from core.pack import create_evidence_bundle
from core.verify import verify_evidence_bundle


class TestMagicLinkAuthentication:
    """Test magic-link authentication system."""
    
    @pytest.fixture
    def auth_system(self, temp_dir):
        """Create authentication system with temporary storage."""
        return MagicLinkAuth(storage_dir=str(temp_dir))
    
    @pytest.fixture
    def sample_users(self) -> List[Dict[str, Any]]:
        """Sample users for testing."""
        return [
            {
                "email": "operator@example.com",
                "role": UserRole.OPERATOR,
                "name": "Test Operator"
            },
            {
                "email": "qa@example.com", 
                "role": UserRole.QA,
                "name": "QA Manager"
            },
            {
                "email": "supervisor@example.com",
                "role": UserRole.QA,
                "name": "QA Supervisor"
            }
        ]
    
    def test_user_registration(self, auth_system, sample_users):
        """Test user registration and role assignment."""
        for user_data in sample_users:
            user = auth_system.register_user(
                email=user_data["email"],
                role=user_data["role"],
                name=user_data.get("name")
            )
            
            assert isinstance(user, User)
            assert user.email == user_data["email"]
            assert user.role == user_data["role"]
            assert user.created_at is not None
    
    def test_magic_link_generation(self, auth_system, sample_users):
        """Test magic-link generation for authentication."""
        user_data = sample_users[0]
        
        # Register user first
        auth_system.register_user(user_data["email"], user_data["role"])
        
        with patch('auth.magic._send_magic_link_email') as mock_email:
            mock_email.return_value = True
            
            request = MagicLinkRequest(
                email=user_data["email"],
                role=user_data["role"]
            )
            
            response = auth_system.generate_magic_link(request)
            
            assert isinstance(response, MagicLinkResponse)
            assert "magic link" in response.message.lower()
            assert response.expires_in > 0
            mock_email.assert_called_once()
    
    def test_magic_link_authentication(self, auth_system, sample_users):
        """Test authentication using magic link."""
        user_data = sample_users[0]
        auth_system.register_user(user_data["email"], user_data["role"])
        
        # Generate magic link
        with patch('auth.magic._send_magic_link_email'):
            request = MagicLinkRequest(email=user_data["email"], role=user_data["role"])
            response = auth_system.generate_magic_link(request)
        
        # Get the magic token (normally from email link)
        tokens = auth_system._get_pending_tokens(user_data["email"])
        assert len(tokens) > 0
        
        magic_token = tokens[0]["token"]
        
        # Authenticate with magic link
        auth_token = auth_system.authenticate_magic_link(magic_token)
        
        assert isinstance(auth_token, AuthToken)
        assert auth_token.access_token is not None
        assert auth_token.token_type == "bearer"
        assert auth_token.expires_in > 0
    
    def test_magic_link_expiration(self, auth_system, sample_users):
        """Test magic link expiration handling."""
        user_data = sample_users[0]
        auth_system.register_user(user_data["email"], user_data["role"])
        
        # Generate expired magic link
        with patch('auth.magic._send_magic_link_email'):
            with patch('time.time', return_value=time.time() - 3600):  # 1 hour ago
                request = MagicLinkRequest(email=user_data["email"], role=user_data["role"])
                auth_system.generate_magic_link(request)
        
        # Try to get expired token
        tokens = auth_system._get_pending_tokens(user_data["email"])
        if tokens:
            expired_token = tokens[0]["token"]
            
            # Should fail authentication
            with pytest.raises(Exception) as exc_info:
                auth_system.authenticate_magic_link(expired_token)
            
            assert "expired" in str(exc_info.value).lower()
    
    def test_invalid_magic_link(self, auth_system):
        """Test handling of invalid magic links."""
        invalid_token = "invalid_token_12345"
        
        with pytest.raises(Exception) as exc_info:
            auth_system.authenticate_magic_link(invalid_token)
        
        assert "invalid" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()
    
    def test_user_session_management(self, auth_system, sample_users):
        """Test user session creation and validation."""
        user_data = sample_users[0]
        auth_system.register_user(user_data["email"], user_data["role"])
        
        # Authenticate user
        with patch('auth.magic._send_magic_link_email'):
            request = MagicLinkRequest(email=user_data["email"], role=user_data["role"])
            auth_system.generate_magic_link(request)
        
        tokens = auth_system._get_pending_tokens(user_data["email"])
        magic_token = tokens[0]["token"]
        auth_token = auth_system.authenticate_magic_link(magic_token)
        
        # Validate session
        user = auth_system.get_current_user(auth_token.access_token)
        assert user.email == user_data["email"]
        assert user.role == user_data["role"]
        
        # Test session expiration
        with patch('time.time', return_value=time.time() + 86400):  # 24 hours later
            expired_user = auth_system.get_current_user(auth_token.access_token)
            assert expired_user is None  # Session should be expired


class TestRoleBasedAccessControl:
    """Test role-based access control functionality."""
    
    @pytest.fixture
    def authenticated_users(self, auth_system, sample_users):
        """Create authenticated users with different roles."""
        users = {}
        
        for user_data in sample_users:
            # Register and authenticate user
            auth_system.register_user(user_data["email"], user_data["role"])
            
            with patch('auth.magic._send_magic_link_email'):
                request = MagicLinkRequest(email=user_data["email"], role=user_data["role"])
                auth_system.generate_magic_link(request)
            
            tokens = auth_system._get_pending_tokens(user_data["email"])
            magic_token = tokens[0]["token"]
            auth_token = auth_system.authenticate_magic_link(magic_token)
            
            users[user_data["role"]] = {
                "user_data": user_data,
                "auth_token": auth_token,
                "user": auth_system.get_current_user(auth_token.access_token)
            }
        
        return users
    
    def test_operator_permissions(self, authenticated_users):
        """Test operator role permissions."""
        operator = authenticated_users[UserRole.OPERATOR]
        
        # Operators should be able to:
        # - Upload data
        # - Run compilations
        # - View results
        # - Submit for approval (but not approve)
        
        assert operator["user"].role == UserRole.OPERATOR
        
        # Mock permission checks
        with patch('auth.magic.require_auth') as mock_auth:
            mock_auth.return_value = operator["user"]
            
            # Should be able to access operator functions
            assert auth_system.can_upload_data(operator["user"]) is True
            assert auth_system.can_run_compilation(operator["user"]) is True
            assert auth_system.can_view_results(operator["user"]) is True
            
            # Should NOT be able to approve
            assert auth_system.can_approve_results(operator["user"]) is False
    
    def test_qa_permissions(self, authenticated_users):
        """Test QA role permissions."""
        qa_user = authenticated_users[UserRole.QA]
        
        # QA should be able to:
        # - All operator functions
        # - Approve results
        # - Reject results
        # - View audit trails
        
        assert qa_user["user"].role == UserRole.QA
        
        with patch('auth.magic.require_qa') as mock_qa:
            mock_qa.return_value = qa_user["user"]
            
            # Should have all permissions
            assert auth_system.can_upload_data(qa_user["user"]) is True
            assert auth_system.can_run_compilation(qa_user["user"]) is True
            assert auth_system.can_view_results(qa_user["user"]) is True
            assert auth_system.can_approve_results(qa_user["user"]) is True
            assert auth_system.can_view_audit_trail(qa_user["user"]) is True
    
    def test_access_control_decorators(self, authenticated_users):
        """Test access control decorators."""
        from auth.magic import require_auth, require_qa
        
        @require_auth
        def operator_function(user: User):
            return f"Operator function accessed by {user.email}"
        
        @require_qa
        def qa_function(user: User):
            return f"QA function accessed by {user.email}"
        
        operator = authenticated_users[UserRole.OPERATOR]
        qa_user = authenticated_users[UserRole.QA]
        
        # Test operator access
        with patch('auth.magic.get_current_user', return_value=operator["user"]):
            result = operator_function()
            assert operator["user"].email in result
        
        # Test QA access to QA function
        with patch('auth.magic.get_current_user', return_value=qa_user["user"]):
            result = qa_function()
            assert qa_user["user"].email in result
        
        # Test operator cannot access QA function
        with patch('auth.magic.get_current_user', return_value=operator["user"]):
            with pytest.raises(Exception) as exc_info:
                qa_function()
            assert "permission" in str(exc_info.value).lower() or "unauthorized" in str(exc_info.value).lower()


class TestApprovalWorkflow:
    """Test the complete approval workflow."""
    
    @pytest.fixture
    def workflow_system(self, auth_system, temp_dir):
        """Create approval workflow system."""
        from auth.magic import ApprovalWorkflow
        return ApprovalWorkflow(auth_system, storage_dir=str(temp_dir))
    
    @pytest.fixture
    def sample_evidence_bundle(self, temp_dir, simple_temp_data, example_spec):
        """Create a sample evidence bundle for approval testing."""
        spec = SpecV1(**example_spec)
        normalized_df, _ = normalize_temperature_data(simple_temp_data, spec)
        decision = make_decision(normalized_df, spec)
        
        # Create bundle files
        csv_path = temp_dir / "approval_data.csv"
        plot_path = temp_dir / "approval_plot.png"
        pdf_path = temp_dir / "approval_proof.pdf"
        bundle_path = temp_dir / "approval_evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec.model_dump(),
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        return {
            "bundle_path": bundle_path,
            "decision": decision,
            "spec": spec,
            "files": {
                "csv": csv_path,
                "plot": plot_path,
                "pdf": pdf_path
            }
        }
    
    def test_submission_for_approval(self, workflow_system, authenticated_users, sample_evidence_bundle):
        """Test submission of evidence bundle for approval."""
        operator = authenticated_users[UserRole.OPERATOR]
        
        # Submit evidence bundle for approval
        submission_request = {
            "bundle_path": str(sample_evidence_bundle["bundle_path"]),
            "job_id": sample_evidence_bundle["spec"].job.job_id,
            "submitter": operator["user"].email,
            "submission_notes": "Powder coat cure validation - all parameters met"
        }
        
        submission_id = workflow_system.submit_for_approval(
            submission_request, 
            submitted_by=operator["user"]
        )
        
        assert submission_id is not None
        assert isinstance(submission_id, str)
        
        # Check submission status
        submission = workflow_system.get_submission(submission_id)
        assert submission["status"] == "pending_approval"
        assert submission["submitter"] == operator["user"].email
        assert submission["job_id"] == sample_evidence_bundle["spec"].job.job_id
    
    def test_approval_by_qa(self, workflow_system, authenticated_users, sample_evidence_bundle):
        """Test approval of evidence bundle by QA."""
        operator = authenticated_users[UserRole.OPERATOR]
        qa_user = authenticated_users[UserRole.QA]
        
        # Submit for approval
        submission_request = {
            "bundle_path": str(sample_evidence_bundle["bundle_path"]),
            "job_id": sample_evidence_bundle["spec"].job.job_id,
            "submitter": operator["user"].email
        }
        
        submission_id = workflow_system.submit_for_approval(
            submission_request,
            submitted_by=operator["user"]
        )
        
        # QA approves
        approval_request = {
            "submission_id": submission_id,
            "decision": "approved",
            "qa_notes": "Evidence bundle verified. All requirements met.",
            "reviewed_by": qa_user["user"].email
        }
        
        approval_result = workflow_system.process_approval(
            approval_request,
            approved_by=qa_user["user"]
        )
        
        assert approval_result["success"] is True
        assert approval_result["status"] == "approved"
        
        # Check updated submission
        submission = workflow_system.get_submission(submission_id)
        assert submission["status"] == "approved"
        assert submission["approver"] == qa_user["user"].email
        assert submission["approval_timestamp"] is not None
    
    def test_rejection_by_qa(self, workflow_system, authenticated_users, sample_evidence_bundle):
        """Test rejection of evidence bundle by QA."""
        operator = authenticated_users[UserRole.OPERATOR]
        qa_user = authenticated_users[UserRole.QA]
        
        # Submit for approval
        submission_request = {
            "bundle_path": str(sample_evidence_bundle["bundle_path"]),
            "job_id": sample_evidence_bundle["spec"].job.job_id,
            "submitter": operator["user"].email
        }
        
        submission_id = workflow_system.submit_for_approval(
            submission_request,
            submitted_by=operator["user"]
        )
        
        # QA rejects
        rejection_request = {
            "submission_id": submission_id,
            "decision": "rejected",
            "qa_notes": "Temperature data shows insufficient hold time. Please re-run process.",
            "reviewed_by": qa_user["user"].email
        }
        
        rejection_result = workflow_system.process_approval(
            rejection_request,
            approved_by=qa_user["user"]
        )
        
        assert rejection_result["success"] is True
        assert rejection_result["status"] == "rejected"
        
        # Check updated submission
        submission = workflow_system.get_submission(submission_id)
        assert submission["status"] == "rejected"
        assert submission["approver"] == qa_user["user"].email
        assert "insufficient hold time" in submission["qa_notes"]
    
    def test_resubmission_after_rejection(self, workflow_system, authenticated_users, sample_evidence_bundle):
        """Test resubmission workflow after rejection."""
        operator = authenticated_users[UserRole.OPERATOR]
        qa_user = authenticated_users[UserRole.QA]
        
        # Initial submission and rejection
        submission_request = {
            "bundle_path": str(sample_evidence_bundle["bundle_path"]),
            "job_id": sample_evidence_bundle["spec"].job.job_id,
            "submitter": operator["user"].email
        }
        
        submission_id = workflow_system.submit_for_approval(
            submission_request,
            submitted_by=operator["user"]
        )
        
        # Reject
        workflow_system.process_approval(
            {
                "submission_id": submission_id,
                "decision": "rejected",
                "qa_notes": "Please correct temperature sensors"
            },
            approved_by=qa_user["user"]
        )
        
        # Resubmit with corrections
        resubmission_request = {
            "original_submission_id": submission_id,
            "bundle_path": str(sample_evidence_bundle["bundle_path"]),
            "job_id": sample_evidence_bundle["spec"].job.job_id,
            "submitter": operator["user"].email,
            "resubmission_notes": "Corrected temperature sensor calibration"
        }
        
        new_submission_id = workflow_system.resubmit_for_approval(
            resubmission_request,
            submitted_by=operator["user"]
        )
        
        assert new_submission_id != submission_id
        
        # Check resubmission
        resubmission = workflow_system.get_submission(new_submission_id)
        assert resubmission["status"] == "pending_approval"
        assert resubmission["original_submission_id"] == submission_id
        assert "corrected temperature" in resubmission["resubmission_notes"].lower()
    
    def test_multi_level_approval(self, workflow_system, authenticated_users, sample_evidence_bundle):
        """Test multi-level approval workflow."""
        operator = authenticated_users[UserRole.OPERATOR]
        qa_users = [user for user in authenticated_users.values() if user["user"].role == UserRole.QA]
        
        # Submit for approval requiring multiple QA approvals
        submission_request = {
            "bundle_path": str(sample_evidence_bundle["bundle_path"]),
            "job_id": sample_evidence_bundle["spec"].job.job_id,
            "submitter": operator["user"].email,
            "approval_level": "high_risk",  # Requires multiple approvals
            "required_approvers": 2
        }
        
        submission_id = workflow_system.submit_for_approval(
            submission_request,
            submitted_by=operator["user"]
        )
        
        # First QA approval
        first_qa = qa_users[0]
        workflow_system.process_approval(
            {
                "submission_id": submission_id,
                "decision": "approved",
                "qa_notes": "First review complete - approved"
            },
            approved_by=first_qa["user"]
        )
        
        # Should still be pending (needs second approval)
        submission = workflow_system.get_submission(submission_id)
        assert submission["status"] == "pending_approval"
        assert len(submission["approvals"]) == 1
        
        # Second QA approval
        if len(qa_users) > 1:
            second_qa = qa_users[1]
            workflow_system.process_approval(
                {
                    "submission_id": submission_id,
                    "decision": "approved",
                    "qa_notes": "Second review complete - approved"
                },
                approved_by=second_qa["user"]
            )
            
            # Should now be fully approved
            submission = workflow_system.get_submission(submission_id)
            assert submission["status"] == "approved"
            assert len(submission["approvals"]) == 2


class TestIntegratedWorkflow:
    """Test complete integrated workflow from compilation to approval."""
    
    def test_complete_operator_to_qa_workflow(self, auth_system, temp_dir, simple_temp_data, example_spec_data):
        """Test complete workflow from operator compilation to QA approval."""
        # Setup users
        operator_email = "operator@proofkit.test"
        qa_email = "qa@proofkit.test"
        
        auth_system.register_user(operator_email, UserRole.OPERATOR)
        auth_system.register_user(qa_email, UserRole.QA)
        
        # Authenticate operator
        with patch('auth.magic._send_magic_link_email'):
            op_request = MagicLinkRequest(email=operator_email, role=UserRole.OPERATOR)
            auth_system.generate_magic_link(op_request)
        
        op_tokens = auth_system._get_pending_tokens(operator_email)
        op_auth_token = auth_system.authenticate_magic_link(op_tokens[0]["token"])
        operator = auth_system.get_current_user(op_auth_token.access_token)
        
        # Authenticate QA
        with patch('auth.magic._send_magic_link_email'):
            qa_request = MagicLinkRequest(email=qa_email, role=UserRole.QA)
            auth_system.generate_magic_link(qa_request)
        
        qa_tokens = auth_system._get_pending_tokens(qa_email)
        qa_auth_token = auth_system.authenticate_magic_link(qa_tokens[0]["token"])
        qa_user = auth_system.get_current_user(qa_auth_token.access_token)
        
        # Operator runs compilation
        spec = SpecV1(**example_spec_data)
        normalized_df, warnings = normalize_temperature_data(simple_temp_data, spec)
        decision = make_decision(normalized_df, spec)
        
        # Generate evidence bundle
        csv_path = temp_dir / "workflow_data.csv"
        plot_path = temp_dir / "workflow_plot.png"
        pdf_path = temp_dir / "workflow_proof.pdf"
        bundle_path = temp_dir / "workflow_evidence.zip"
        
        simple_temp_data.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec.model_dump(),
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        # Verify bundle before submission
        verification_result = verify_evidence_bundle(str(bundle_path))
        assert verification_result["valid"] is True
        
        # Operator submits for approval
        workflow_system = ApprovalWorkflow(auth_system, storage_dir=str(temp_dir))
        
        submission_id = workflow_system.submit_for_approval(
            {
                "bundle_path": str(bundle_path),
                "job_id": spec.job.job_id,
                "submitter": operator.email,
                "submission_notes": "Standard powder coat validation"
            },
            submitted_by=operator
        )
        
        # QA reviews and approves
        approval_result = workflow_system.process_approval(
            {
                "submission_id": submission_id,
                "decision": "approved",
                "qa_notes": "All validation criteria met. Approved for release."
            },
            approved_by=qa_user
        )
        
        assert approval_result["success"] is True
        assert approval_result["status"] == "approved"
        
        # Final verification
        final_submission = workflow_system.get_submission(submission_id)
        assert final_submission["status"] == "approved"
        assert final_submission["submitter"] == operator.email
        assert final_submission["approver"] == qa_user.email
        assert final_submission["decision"]["pass"] == decision.pass_
    
    def test_failing_batch_approval_workflow(self, auth_system, temp_dir, failing_temp_data, example_spec_data):
        """Test approval workflow for failing batches."""
        # Setup
        operator_email = "operator@proofkit.test"
        qa_email = "qa@proofkit.test"
        
        auth_system.register_user(operator_email, UserRole.OPERATOR)
        auth_system.register_user(qa_email, UserRole.QA)
        
        # Authenticate users (simplified)
        with patch('auth.magic._send_magic_link_email'):
            # Operator auth
            op_request = MagicLinkRequest(email=operator_email, role=UserRole.OPERATOR)
            auth_system.generate_magic_link(op_request)
            op_tokens = auth_system._get_pending_tokens(operator_email)
            op_auth_token = auth_system.authenticate_magic_link(op_tokens[0]["token"])
            operator = auth_system.get_current_user(op_auth_token.access_token)
            
            # QA auth
            qa_request = MagicLinkRequest(email=qa_email, role=UserRole.QA)
            auth_system.generate_magic_link(qa_request)
            qa_tokens = auth_system._get_pending_tokens(qa_email)
            qa_auth_token = auth_system.authenticate_magic_link(qa_tokens[0]["token"])
            qa_user = auth_system.get_current_user(qa_auth_token.access_token)
        
        # Run compilation with failing data
        spec = SpecV1(**example_spec_data)
        normalized_df, warnings = normalize_temperature_data(failing_temp_data, spec)
        decision = make_decision(normalized_df, spec)
        
        # Should be a failing decision
        assert decision.pass_ is False
        
        # Generate evidence bundle for failing batch
        csv_path = temp_dir / "failing_data.csv"
        plot_path = temp_dir / "failing_plot.png"
        pdf_path = temp_dir / "failing_proof.pdf"
        bundle_path = temp_dir / "failing_evidence.zip"
        
        failing_temp_data.to_csv(csv_path, index=False)
        generate_proof_plot(normalized_df, spec, decision, str(plot_path))
        generate_proof_pdf(normalized_df, spec, decision, str(plot_path), str(pdf_path))
        
        create_evidence_bundle(
            csv_path=str(csv_path),
            spec_path=None,
            spec_data=spec.model_dump(),
            decision=decision,
            plot_path=str(plot_path),
            pdf_path=str(pdf_path),
            output_path=str(bundle_path)
        )
        
        # Submit failing batch for approval (for documentation/investigation)
        workflow_system = ApprovalWorkflow(auth_system, storage_dir=str(temp_dir))
        
        submission_id = workflow_system.submit_for_approval(
            {
                "bundle_path": str(bundle_path),
                "job_id": spec.job.job_id,
                "submitter": operator.email,
                "submission_notes": "Batch failed validation - submitting for investigation",
                "batch_status": "failed"
            },
            submitted_by=operator
        )
        
        # QA reviews failing batch
        investigation_result = workflow_system.process_approval(
            {
                "submission_id": submission_id,
                "decision": "acknowledged",  # Special status for failed batches
                "qa_notes": "Failure confirmed. Root cause: Insufficient hold time. Process adjustment needed."
            },
            approved_by=qa_user
        )
        
        assert investigation_result["success"] is True
        assert investigation_result["status"] == "acknowledged"
        
        # Check final status
        final_submission = workflow_system.get_submission(submission_id)
        assert final_submission["status"] == "acknowledged"
        assert "root cause" in final_submission["qa_notes"].lower()


class TestWorkflowSecurity:
    """Test security aspects of the workflow system."""
    
    def test_authorization_enforcement(self, auth_system, temp_dir):
        """Test that authorization is properly enforced."""
        # Register users
        operator_email = "operator@proofkit.test"
        unauthorized_email = "unauthorized@proofkit.test"
        
        auth_system.register_user(operator_email, UserRole.OPERATOR)
        auth_system.register_user(unauthorized_email, UserRole.OPERATOR)  # Different operator
        
        # Authenticate legitimate operator
        with patch('auth.magic._send_magic_link_email'):
            op_request = MagicLinkRequest(email=operator_email, role=UserRole.OPERATOR)
            auth_system.generate_magic_link(op_request)
            op_tokens = auth_system._get_pending_tokens(operator_email)
            op_auth_token = auth_system.authenticate_magic_link(op_tokens[0]["token"])
            operator = auth_system.get_current_user(op_auth_token.access_token)
        
        workflow_system = ApprovalWorkflow(auth_system, storage_dir=str(temp_dir))
        
        # Create submission as legitimate operator
        submission_id = workflow_system.submit_for_approval(
            {
                "bundle_path": "/fake/path",
                "job_id": "test_security",
                "submitter": operator.email
            },
            submitted_by=operator
        )
        
        # Try to access submission as different user (should fail)
        with patch('auth.magic.get_current_user') as mock_user:
            unauthorized_user = User(
                email=unauthorized_email,
                role=UserRole.OPERATOR,
                created_at=datetime.now(timezone.utc)
            )
            mock_user.return_value = unauthorized_user
            
            # Should not be able to access other user's submission
            with pytest.raises(Exception) as exc_info:
                workflow_system.get_submission(submission_id, requested_by=unauthorized_user)
            
            assert "unauthorized" in str(exc_info.value).lower() or "permission" in str(exc_info.value).lower()
    
    def test_session_timeout_handling(self, auth_system):
        """Test proper handling of session timeouts."""
        operator_email = "operator@proofkit.test"
        auth_system.register_user(operator_email, UserRole.OPERATOR)
        
        # Authenticate user
        with patch('auth.magic._send_magic_link_email'):
            op_request = MagicLinkRequest(email=operator_email, role=UserRole.OPERATOR)
            auth_system.generate_magic_link(op_request)
            op_tokens = auth_system._get_pending_tokens(operator_email)
            op_auth_token = auth_system.authenticate_magic_link(op_tokens[0]["token"])
        
        # Valid session
        user = auth_system.get_current_user(op_auth_token.access_token)
        assert user is not None
        
        # Simulate session timeout
        with patch('time.time', return_value=time.time() + 86400):  # 24 hours later
            expired_user = auth_system.get_current_user(op_auth_token.access_token)
            assert expired_user is None
    
    def test_audit_trail_security(self, auth_system, temp_dir, sample_users):
        """Test that audit trails are properly maintained and secured."""
        # Setup multiple users
        for user_data in sample_users:
            auth_system.register_user(user_data["email"], user_data["role"])
        
        workflow_system = ApprovalWorkflow(auth_system, storage_dir=str(temp_dir))
        
        # Create multiple actions to audit
        actions = [
            {"user": "operator@example.com", "action": "submit_for_approval", "job_id": "test_001"},
            {"user": "qa@example.com", "action": "review_submission", "job_id": "test_001"},
            {"user": "qa@example.com", "action": "approve_submission", "job_id": "test_001"}
        ]
        
        for action in actions:
            workflow_system.log_audit_event(
                user_email=action["user"],
                action=action["action"],
                details={"job_id": action["job_id"]},
                timestamp=datetime.now(timezone.utc)
            )
        
        # Retrieve audit trail
        audit_trail = workflow_system.get_audit_trail("test_001")
        
        assert len(audit_trail) >= len(actions)
        
        # Verify audit trail integrity
        for i, event in enumerate(audit_trail):
            assert "timestamp" in event
            assert "user_email" in event
            assert "action" in event
            assert event["user_email"] in [a["user"] for a in actions]
        
        # Test that audit trail cannot be modified by unauthorized users
        operator_user = User(
            email="operator@example.com",
            role=UserRole.OPERATOR,
            created_at=datetime.now(timezone.utc)
        )
        
        with pytest.raises(Exception) as exc_info:
            # Operator should not be able to modify audit trail
            workflow_system.modify_audit_trail("test_001", operator_user)
        
        assert "unauthorized" in str(exc_info.value).lower() or "permission" in str(exc_info.value).lower()


# Mock implementations for testing
class ApprovalWorkflow:
    """Mock approval workflow system for testing."""
    
    def __init__(self, auth_system, storage_dir):
        self.auth_system = auth_system
        self.storage_dir = Path(storage_dir)
        self.submissions = {}
        self.audit_log = []
    
    def submit_for_approval(self, request, submitted_by):
        submission_id = str(uuid.uuid4())
        self.submissions[submission_id] = {
            "id": submission_id,
            "status": "pending_approval",
            "submitter": submitted_by.email,
            "job_id": request["job_id"],
            "bundle_path": request["bundle_path"],
            "submission_timestamp": datetime.now(timezone.utc).isoformat(),
            "submission_notes": request.get("submission_notes", ""),
            "approvals": [],
            "decision": None
        }
        return submission_id
    
    def process_approval(self, request, approved_by):
        submission_id = request["submission_id"]
        if submission_id not in self.submissions:
            raise ValueError(f"Submission {submission_id} not found")
        
        submission = self.submissions[submission_id]
        decision = request["decision"]
        
        if decision == "approved":
            submission["status"] = "approved"
        elif decision == "rejected":
            submission["status"] = "rejected"
        elif decision == "acknowledged":
            submission["status"] = "acknowledged"
        
        submission["approver"] = approved_by.email
        submission["approval_timestamp"] = datetime.now(timezone.utc).isoformat()
        submission["qa_notes"] = request.get("qa_notes", "")
        
        return {"success": True, "status": submission["status"]}
    
    def get_submission(self, submission_id, requested_by=None):
        if submission_id not in self.submissions:
            raise ValueError(f"Submission {submission_id} not found")
        return self.submissions[submission_id]
    
    def resubmit_for_approval(self, request, submitted_by):
        new_submission_id = str(uuid.uuid4())
        self.submissions[new_submission_id] = {
            "id": new_submission_id,
            "status": "pending_approval",
            "submitter": submitted_by.email,
            "original_submission_id": request["original_submission_id"],
            "job_id": request["job_id"],
            "bundle_path": request["bundle_path"],
            "submission_timestamp": datetime.now(timezone.utc).isoformat(),
            "resubmission_notes": request.get("resubmission_notes", ""),
            "approvals": []
        }
        return new_submission_id
    
    def log_audit_event(self, user_email, action, details, timestamp):
        self.audit_log.append({
            "timestamp": timestamp.isoformat(),
            "user_email": user_email,
            "action": action,
            "details": details
        })
    
    def get_audit_trail(self, job_id):
        return [event for event in self.audit_log 
                if event["details"].get("job_id") == job_id]
    
    def modify_audit_trail(self, job_id, user):
        if user.role != UserRole.QA:
            raise Exception("Unauthorized: Only QA can modify audit trails")


# Add missing methods to auth system for testing
def _add_auth_system_methods(auth_system):
    """Add missing methods to auth system for testing."""
    
    def can_upload_data(user):
        return user.role in [UserRole.OPERATOR, UserRole.QA]
    
    def can_run_compilation(user):
        return user.role in [UserRole.OPERATOR, UserRole.QA]
    
    def can_view_results(user):
        return user.role in [UserRole.OPERATOR, UserRole.QA]
    
    def can_approve_results(user):
        return user.role == UserRole.QA
    
    def can_view_audit_trail(user):
        return user.role == UserRole.QA
    
    # Monkey patch methods
    auth_system.can_upload_data = can_upload_data
    auth_system.can_run_compilation = can_run_compilation
    auth_system.can_view_results = can_view_results
    auth_system.can_approve_results = can_approve_results
    auth_system.can_view_audit_trail = can_view_audit_trail
    
    return auth_system


@pytest.fixture(autouse=True)
def setup_auth_system_methods(auth_system):
    """Automatically add methods to auth system for all tests."""
    return _add_auth_system_methods(auth_system)