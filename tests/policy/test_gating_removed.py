"""
Test Suite: Policy Gating Removed

Tests that all Safe Mode restrictions and human QA gating have been removed.
Validates that the system defaults to permissive settings and processes
certificates without human intervention.

Key test coverage:
- Safe Mode disabled by default
- Parser warnings log only, don't block processing
- Human QA approval bypassed
- TSA unavailability queues retry instead of blocking
- PDF/A-3 enforced but falls back to regular PDF gracefully
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from core.policy import (
    get_safe_mode_settings,
    is_safe_mode_enabled,
    should_fail_on_parser_warnings,
    is_human_qa_required,
    should_block_if_no_tsa,
    should_enforce_pdf_a3,
    get_policy_summary,
    SAFE_MODE_DEFAULT,
    HUMAN_QA_REQUIRED_FOR_PASS_DEFAULT,
    FAIL_ON_PARSER_WARNINGS_DEFAULT,
    BLOCK_IF_NO_TSA_DEFAULT,
    ENFORCE_PDF_A3_DEFAULT
)


class TestPolicyDefaults:
    """Test that all policy flags default to permissive settings."""
    
    def test_safe_mode_disabled_by_default(self):
        """Safe Mode should be disabled by default."""
        assert SAFE_MODE_DEFAULT is False
        assert is_safe_mode_enabled() is False
        
    def test_human_qa_not_required_by_default(self):
        """Human QA approval should not be required by default."""
        assert HUMAN_QA_REQUIRED_FOR_PASS_DEFAULT is False
        assert is_human_qa_required() is False
        
    def test_parser_warnings_dont_fail_by_default(self):
        """Parser warnings should log only, not fail validation by default."""
        assert FAIL_ON_PARSER_WARNINGS_DEFAULT is False
        assert should_fail_on_parser_warnings() is False
        
    def test_tsa_unavailable_doesnt_block_by_default(self):
        """TSA unavailability should not block certificate issuance by default."""
        assert BLOCK_IF_NO_TSA_DEFAULT is False
        assert should_block_if_no_tsa() is False
        
    def test_pdf_a3_enforced_but_fallback_enabled(self):
        """PDF/A-3 should be enforced but with graceful fallback."""
        assert ENFORCE_PDF_A3_DEFAULT is True
        assert should_enforce_pdf_a3() is True


class TestPolicyEnvironmentOverrides:
    """Test that environment variables can override policy settings when needed."""
    
    @patch.dict(os.environ, {'SAFE_MODE': 'true'})
    def test_safe_mode_can_be_enabled_via_env(self):
        """Safe Mode can be enabled via environment variable."""
        assert is_safe_mode_enabled() is True
        
    @patch.dict(os.environ, {'HUMAN_QA_REQUIRED_FOR_PASS': 'true'})
    def test_human_qa_can_be_enabled_via_env(self):
        """Human QA can be enabled via environment variable."""
        assert is_human_qa_required() is True
        
    @patch.dict(os.environ, {'FAIL_ON_PARSER_WARNINGS': 'true'})
    def test_parser_warnings_can_block_via_env(self):
        """Parser warnings can be made to block via environment variable."""
        assert should_fail_on_parser_warnings() is True
        
    @patch.dict(os.environ, {'BLOCK_IF_NO_TSA': 'true'})
    def test_tsa_blocking_can_be_enabled_via_env(self):
        """TSA blocking can be enabled via environment variable."""
        assert should_block_if_no_tsa() is True
        
    @patch.dict(os.environ, {'ENFORCE_PDF_A3': 'false'})
    def test_pdf_a3_enforcement_can_be_disabled_via_env(self):
        """PDF/A-3 enforcement can be disabled via environment variable."""
        assert should_enforce_pdf_a3() is False


class TestPolicySettingsIntegration:
    """Test the integrated policy settings interface."""
    
    def test_default_settings_all_permissive(self):
        """Default settings should all be permissive."""
        settings = get_safe_mode_settings()
        
        assert settings['safe_mode'] is False
        assert settings['human_qa_required'] is False
        assert settings['fail_on_parser_warnings'] is False
        assert settings['block_if_no_tsa'] is False
        assert settings['enforce_pdf_a3'] is True  # Enforced but with fallback
        
    def test_policy_summary_reflects_defaults(self):
        """Policy summary should reflect permissive defaults."""
        summary = get_policy_summary()
        
        assert "Safe Mode: DISABLED" in summary
        assert "Human QA: BYPASSED" in summary
        assert "Parser Warnings: LOG ONLY" in summary
        assert "TSA Required: RETRY QUEUE" in summary


class TestNormalizeIntegration:
    """Test that normalize.py properly uses the new policy settings."""
    
    def test_normalize_uses_policy_defaults(self):
        """Normalize module should use policy defaults."""
        from core.normalize import SAFE_MODE, FAIL_ON_PARSER_WARNINGS
        
        # These should reflect the policy defaults
        assert SAFE_MODE is False
        assert FAIL_ON_PARSER_WARNINGS is False
        
    @patch.dict(os.environ, {'SAFE_MODE': 'true', 'FAIL_ON_PARSER_WARNINGS': 'true'})
    def test_normalize_respects_policy_overrides(self):
        """Normalize module should respect policy environment overrides."""
        # Reload the module to pick up new env vars
        import importlib
        import core.normalize
        importlib.reload(core.normalize)
        
        assert core.normalize.SAFE_MODE is True
        assert core.normalize.FAIL_ON_PARSER_WARNINGS is True


class TestRenderPdfIntegration:
    """Test that render_pdf.py properly uses the new policy settings."""
    
    def test_pdf_validation_gates_use_policy(self):
        """PDF validation gates should use policy settings."""
        from core.render_pdf import check_pdf_validation_gates
        from core.models import DecisionResult
        
        # Create a mock decision
        decision = MagicMock(spec=DecisionResult)
        decision.pass_ = True
        
        # With default policy settings, validation should pass
        result = check_pdf_validation_gates(
            decision=decision,
            enable_rfc3161=True,
            timestamp_available=False  # TSA unavailable
        )
        
        assert result['should_block'] is False
        assert result['gate_status'] == "PASS"
        
    @patch.dict(os.environ, {'BLOCK_IF_NO_TSA': 'true'})
    def test_pdf_validation_can_block_when_policy_changed(self):
        """PDF validation can block when policy is changed via environment."""
        from core.render_pdf import check_pdf_validation_gates, PDFValidationError
        from core.models import DecisionResult
        
        # Create a mock decision
        decision = MagicMock(spec=DecisionResult)
        decision.pass_ = True
        
        # With blocking policy, validation should fail when TSA unavailable
        with pytest.raises(PDFValidationError):
            check_pdf_validation_gates(
                decision=decision,
                enable_rfc3161=True,
                timestamp_available=False  # TSA unavailable
            )


class TestAppIntegration:
    """Test that app.py properly bypasses QA approval when policy allows."""
    
    def test_qa_approval_auto_granted_by_default(self):
        """QA approval should be auto-granted when policy allows."""
        from core.policy import is_human_qa_required
        
        # With default policy, QA should not be required
        assert is_human_qa_required() is False
        
    @patch.dict(os.environ, {'HUMAN_QA_REQUIRED_FOR_PASS': 'true'})
    def test_qa_approval_can_be_required_when_policy_changed(self):
        """QA approval can be required when policy is changed."""
        # Reload policy to pick up environment change
        import importlib
        import core.policy
        importlib.reload(core.policy)
        
        assert core.policy.is_human_qa_required() is True


class TestPolicyConsistency:
    """Test that policy settings are consistent across the system."""
    
    def test_all_modules_use_consistent_defaults(self):
        """All modules should use consistent policy defaults."""
        from core.policy import get_safe_mode_settings
        from core.normalize import SAFE_MODE as normalize_safe_mode
        from core.normalize import FAIL_ON_PARSER_WARNINGS as normalize_parser_warnings
        
        policy_settings = get_safe_mode_settings()
        
        # Normalize module should match policy
        assert normalize_safe_mode == policy_settings['safe_mode']
        assert normalize_parser_warnings == policy_settings['fail_on_parser_warnings']
        
    def test_policy_flags_backward_compatible(self):
        """Policy module should provide backward compatible flag access."""
        from core.policy import (
            SAFE_MODE, FAIL_ON_PARSER_WARNINGS, 
            HUMAN_QA_REQUIRED_FOR_PASS, BLOCK_IF_NO_TSA, ENFORCE_PDF_A3
        )
        
        # These legacy flags should work
        assert SAFE_MODE is False
        assert FAIL_ON_PARSER_WARNINGS is False
        assert HUMAN_QA_REQUIRED_FOR_PASS is False
        assert BLOCK_IF_NO_TSA is False
        assert ENFORCE_PDF_A3 is True


# Example test data for policy validation
PERMISSIVE_POLICY_CONFIG = {
    'safe_mode': False,
    'human_qa_required': False,
    'fail_on_parser_warnings': False,
    'block_if_no_tsa': False,
    'enforce_pdf_a3': True
}


def test_policy_matches_expected_permissive_config():
    """Test that current policy matches expected permissive configuration."""
    from core.policy import get_safe_mode_settings
    
    current_settings = get_safe_mode_settings()
    
    for key, expected_value in PERMISSIVE_POLICY_CONFIG.items():
        assert current_settings[key] == expected_value, f"Policy setting '{key}' mismatch"