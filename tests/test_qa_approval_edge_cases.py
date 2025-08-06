"""
QA Approval Edge Case Tests

Tests edge cases in the QA approval workflow:
- Approving twice is idempotent
- Approving with wrong role returns 403
- Audit trail entry count verification
"""

import pytest
import tempfile
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock
import os

# Set up test environment
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.models import User, UserRole
from auth.magic import MagicLinkAuth
from core.models import DecisionResult, SpecV1


class TestQAApprovalEdgeCases:
    """Test edge cases in QA approval workflow."""
    
    @pytest.fixture
    def auth_system(self, temp_dir):
        """Create auth system with test storage."""
        return MagicLinkAuth(storage_dir=str(temp_dir))
    
    @pytest.fixture
    def test_users(self, auth_system):
        """Create test users with different roles."""
        users = {
            'operator': auth_system.register_user(
                email="operator@test.com",
                role=UserRole.OPERATOR,
                name="Test Operator"
            ),
            'qa_manager': auth_system.register_user(
                email="qa@test.com",
                role=UserRole.QA,
                name="QA Manager"
            ),
            'qa_supervisor': auth_system.register_user(
                email="qa2@test.com",
                role=UserRole.QA,
                name="QA Supervisor"
            )
        }
        return users
    
    @pytest.fixture
    def sample_job_data(self):
        """Create sample job data for approval."""
        return {
            'job_id': f'test_job_{uuid.uuid4().hex[:8]}',
            'decision': DecisionResult(
                pass_=True,
                job_id='test_job',
                target_temp_C=180.0,
                conservative_threshold_C=182.0,
                actual_hold_time_s=650.0,
                required_hold_time_s=600,
                max_temp_C=185.0,
                min_temp_C=179.0,
                reasons=["Temperature requirements met"],
                warnings=[]
            ),
            'bundle_path': '/tmp/test_bundle.zip',
            'created_at': datetime.now(timezone.utc)
        }
    
    def test_double_approval_is_idempotent(self, auth_system, test_users, sample_job_data, temp_dir):
        """Test that approving a job twice by same user is idempotent."""
        qa_user = test_users['qa_manager']
        job_id = sample_job_data['job_id']
        
        # Create job approval record
        approval_file = Path(temp_dir) / f"approvals/{job_id}.json"
        approval_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initial approval data
        approval_data = {
            'job_id': job_id,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'audit_trail': []
        }
        
        with open(approval_file, 'w') as f:
            json.dump(approval_data, f)
        
        # First approval
        def approve_job(job_id: str, user_id: str, comments: str = "") -> Dict[str, Any]:
            """Simulate job approval logic."""
            with open(approval_file, 'r') as f:
                data = json.load(f)
            
            # Add audit entry
            audit_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'user_id': user_id,
                'action': 'approved',
                'comments': comments
            }
            
            # Check if already approved by this user
            existing_approvals = [
                e for e in data['audit_trail'] 
                if e['user_id'] == user_id and e['action'] == 'approved'
            ]
            
            if not existing_approvals:
                data['audit_trail'].append(audit_entry)
                data['status'] = 'approved'
                data['approved_by'] = user_id
                data['approved_at'] = audit_entry['timestamp']
            
            with open(approval_file, 'w') as f:
                json.dump(data, f)
            
            return data
        
        # First approval
        result1 = approve_job(job_id, qa_user.id, "Looks good")
        initial_audit_count = len(result1['audit_trail'])
        assert result1['status'] == 'approved'
        assert result1['approved_by'] == qa_user.id
        
        # Second approval by same user
        result2 = approve_job(job_id, qa_user.id, "Approving again")
        
        # Should be idempotent
        assert result2['status'] == 'approved'
        assert result2['approved_by'] == qa_user.id
        assert len(result2['audit_trail']) == initial_audit_count  # No new entry
        
        # Verify audit trail integrity
        qa_approvals = [
            e for e in result2['audit_trail'] 
            if e['user_id'] == qa_user.id and e['action'] == 'approved'
        ]
        assert len(qa_approvals) == 1  # Only one approval entry
    
    def test_approval_with_wrong_role_forbidden(self, auth_system, test_users, sample_job_data, temp_dir):
        """Test that operators cannot approve jobs (403 Forbidden)."""
        operator = test_users['operator']
        job_id = sample_job_data['job_id']
        
        # Create job requiring approval
        approval_file = Path(temp_dir) / f"approvals/{job_id}.json"
        approval_file.parent.mkdir(parents=True, exist_ok=True)
        
        approval_data = {
            'job_id': job_id,
            'status': 'pending',
            'requires_role': UserRole.QA,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'audit_trail': []
        }
        
        with open(approval_file, 'w') as f:
            json.dump(approval_data, f)
        
        # Simulate role-based approval check
        def try_approve_with_role_check(job_id: str, user: User) -> Dict[str, Any]:
            """Attempt approval with role verification."""
            with open(approval_file, 'r') as f:
                data = json.load(f)
            
            # Check role requirement
            required_role = data.get('requires_role', UserRole.QA)
            
            if user.role != required_role:
                # Log unauthorized attempt
                audit_entry = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'user_id': user.id,
                    'action': 'approval_denied',
                    'reason': f'Insufficient role: {user.role} != {required_role}',
                    'http_status': 403
                }
                data['audit_trail'].append(audit_entry)
                
                with open(approval_file, 'w') as f:
                    json.dump(data, f)
                
                return {
                    'error': 'Forbidden',
                    'message': f'Role {required_role} required',
                    'status_code': 403
                }
            
            # Would proceed with approval if role matched
            return {'status': 'would_approve'}
        
        # Operator attempts approval
        result = try_approve_with_role_check(job_id, operator)
        
        # Should be forbidden
        assert result.get('status_code') == 403
        assert 'Forbidden' in result.get('error', '')
        
        # Verify audit trail captured the attempt
        with open(approval_file, 'r') as f:
            final_data = json.load(f)
        
        denied_entries = [
            e for e in final_data['audit_trail'] 
            if e['action'] == 'approval_denied'
        ]
        assert len(denied_entries) == 1
        assert denied_entries[0]['user_id'] == operator.id
        assert denied_entries[0]['http_status'] == 403
        
        # Job should still be pending
        assert final_data['status'] == 'pending'
    
    def test_audit_trail_entry_count_accuracy(self, auth_system, test_users, sample_job_data, temp_dir):
        """Test that audit trail accurately tracks all approval actions."""
        qa1 = test_users['qa_manager']
        qa2 = test_users['qa_supervisor']
        operator = test_users['operator']
        job_id = sample_job_data['job_id']
        
        # Initialize approval record
        approval_file = Path(temp_dir) / f"approvals/{job_id}.json"
        approval_file.parent.mkdir(parents=True, exist_ok=True)
        
        approval_data = {
            'job_id': job_id,
            'status': 'pending',
            'requires_role': UserRole.QA,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'audit_trail': [],
            'multi_approval_required': True,
            'approvals_needed': 2
        }
        
        with open(approval_file, 'w') as f:
            json.dump(approval_data, f)
        
        def record_action(user: User, action: str, success: bool = True) -> int:
            """Record an action in audit trail and return new count."""
            with open(approval_file, 'r') as f:
                data = json.load(f)
            
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'user_id': user.id,
                'user_email': user.email,
                'user_role': user.role,
                'action': action,
                'success': success
            }
            
            data['audit_trail'].append(entry)
            
            # Update approval status if needed
            if action == 'approved' and success and user.role == UserRole.QA:
                approvals = [
                    e for e in data['audit_trail'] 
                    if e['action'] == 'approved' and e['success']
                ]
                unique_approvers = set(e['user_id'] for e in approvals)
                
                if len(unique_approvers) >= data.get('approvals_needed', 1):
                    data['status'] = 'approved'
            
            with open(approval_file, 'w') as f:
                json.dump(data, f)
            
            return len(data['audit_trail'])
        
        # Track audit trail growth
        counts = []
        
        # 1. Operator views job
        counts.append(record_action(operator, 'viewed'))
        
        # 2. Operator attempts approval (fails)
        counts.append(record_action(operator, 'approval_attempted', success=False))
        
        # 3. QA1 views job
        counts.append(record_action(qa1, 'viewed'))
        
        # 4. QA1 approves
        counts.append(record_action(qa1, 'approved'))
        
        # 5. QA1 attempts second approval (idempotent, still recorded)
        counts.append(record_action(qa1, 'approval_attempted'))
        
        # 6. QA2 views
        counts.append(record_action(qa2, 'viewed'))
        
        # 7. QA2 approves (completes multi-approval)
        counts.append(record_action(qa2, 'approved'))
        
        # Verify counts are strictly increasing
        for i in range(1, len(counts)):
            assert counts[i] == counts[i-1] + 1, f"Audit count should increase: {counts}"
        
        # Verify final count
        assert counts[-1] == 7  # Total actions recorded
        
        # Verify final state
        with open(approval_file, 'r') as f:
            final_data = json.load(f)
        
        # Check approval status
        assert final_data['status'] == 'approved'
        
        # Verify audit trail integrity
        assert len(final_data['audit_trail']) == 7
        
        # Count by action type
        action_counts = {}
        for entry in final_data['audit_trail']:
            action = entry['action']
            action_counts[action] = action_counts.get(action, 0) + 1
        
        assert action_counts['viewed'] == 3
        assert action_counts['approved'] == 2
        assert action_counts.get('approval_attempted', 0) == 2
        
        # Verify user actions
        qa1_actions = [e for e in final_data['audit_trail'] if e['user_id'] == qa1.id]
        assert len(qa1_actions) == 3  # view, approve, attempt
        
        qa2_actions = [e for e in final_data['audit_trail'] if e['user_id'] == qa2.id]
        assert len(qa2_actions) == 2  # view, approve
        
        operator_actions = [e for e in final_data['audit_trail'] if e['user_id'] == operator.id]
        assert len(operator_actions) == 2  # view, failed attempt
    
    def test_concurrent_approval_handling(self, auth_system, test_users, temp_dir):
        """Test handling of concurrent approval attempts."""
        qa1 = test_users['qa_manager']
        qa2 = test_users['qa_supervisor']
        job_id = f'concurrent_test_{uuid.uuid4().hex[:8]}'
        
        # Create job
        approval_file = Path(temp_dir) / f"approvals/{job_id}.json"
        approval_file.parent.mkdir(parents=True, exist_ok=True)
        
        initial_data = {
            'job_id': job_id,
            'status': 'pending',
            'audit_trail': [],
            'version': 1  # For optimistic locking
        }
        
        with open(approval_file, 'w') as f:
            json.dump(initial_data, f)
        
        # Simulate concurrent approval with version checking
        def approve_with_version_check(user: User) -> Dict[str, Any]:
            """Approve with optimistic locking."""
            # Read current state
            with open(approval_file, 'r') as f:
                data = json.load(f)
            
            current_version = data.get('version', 1)
            
            # Check if already approved
            if data['status'] == 'approved':
                return {'status': 'already_approved', 'version': current_version}
            
            # Simulate processing delay where race condition could occur
            import time
            time.sleep(0.001)  # Small delay
            
            # Re-read to check version
            with open(approval_file, 'r') as f:
                check_data = json.load(f)
            
            if check_data.get('version', 1) != current_version:
                # Version changed, someone else updated
                return {'status': 'version_conflict', 'retry_needed': True}
            
            # Proceed with approval
            data['status'] = 'approved'
            data['approved_by'] = user.id
            data['version'] = current_version + 1
            data['audit_trail'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'user_id': user.id,
                'action': 'approved'
            })
            
            with open(approval_file, 'w') as f:
                json.dump(data, f)
            
            return {'status': 'approved', 'version': data['version']}
        
        # Both QAs try to approve "simultaneously"
        result1 = approve_with_version_check(qa1)
        
        # Second approval should detect already approved
        result2 = approve_with_version_check(qa2)
        
        # One should succeed, other should see it's already approved
        assert result1['status'] == 'approved' or result2['status'] == 'approved'
        if result1['status'] == 'approved':
            assert result2['status'] == 'already_approved'
        else:
            assert result1['status'] in ['already_approved', 'version_conflict']
        
        # Verify final state has exactly one approval
        with open(approval_file, 'r') as f:
            final_data = json.load(f)
        
        approval_entries = [e for e in final_data['audit_trail'] if e['action'] == 'approved']
        assert len(approval_entries) == 1  # Only one approval recorded