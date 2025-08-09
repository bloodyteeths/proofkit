"""
Policy Configuration Module

Provides centralized policy flags for Safe Mode restrictions and gating.
All flags default to permissive settings - no human QA gating, minimal restrictions.

Key features:
- SAFE_MODE disabled by default
- HUMAN_QA_REQUIRED_FOR_PASS ignored
- Parser warnings log only, don't block processing
- TSA unavailability issues certificate with retry queue

Example usage:
    from core.policy import get_safe_mode_settings
    
    settings = get_safe_mode_settings()
    if settings['safe_mode']:
        # Apply conservative parsing
        pass
    else:
        # Use permissive parsing (default)
        pass
"""

import os
from typing import Dict, Any, Optional


# Default policy flags - all permissive
SAFE_MODE_DEFAULT = False
HUMAN_QA_REQUIRED_FOR_PASS_DEFAULT = False
FAIL_ON_PARSER_WARNINGS_DEFAULT = False
BLOCK_IF_NO_TSA_DEFAULT = False
ENFORCE_PDF_A3_DEFAULT = True  # Still enforce PDF/A-3 but fallback to regular PDF


def get_safe_mode_settings() -> Dict[str, Any]:
    """
    Get current Safe Mode policy settings.
    
    Returns:
        Dictionary containing all policy flags with current values
        
    Example:
        >>> settings = get_safe_mode_settings()
        >>> print(settings['safe_mode'])
        False
    """
    return {
        'safe_mode': os.environ.get('SAFE_MODE', str(SAFE_MODE_DEFAULT)).lower() == 'true',
        'human_qa_required': os.environ.get('HUMAN_QA_REQUIRED_FOR_PASS', str(HUMAN_QA_REQUIRED_FOR_PASS_DEFAULT)).lower() == 'true',
        'fail_on_parser_warnings': os.environ.get('FAIL_ON_PARSER_WARNINGS', str(FAIL_ON_PARSER_WARNINGS_DEFAULT)).lower() == 'true',
        'block_if_no_tsa': os.environ.get('BLOCK_IF_NO_TSA', str(BLOCK_IF_NO_TSA_DEFAULT)).lower() == 'true',
        'enforce_pdf_a3': os.environ.get('ENFORCE_PDF_A3', str(ENFORCE_PDF_A3_DEFAULT)).lower() == 'true',
    }


def is_safe_mode_enabled() -> bool:
    """
    Check if Safe Mode is enabled.
    
    Returns:
        True if Safe Mode is enabled, False otherwise (default)
    """
    return get_safe_mode_settings()['safe_mode']


def should_fail_on_parser_warnings() -> bool:
    """
    Check if parser warnings should cause validation failure.
    
    Returns:
        True if warnings should fail validation, False otherwise (default)
    """
    return get_safe_mode_settings()['fail_on_parser_warnings']


def is_human_qa_required() -> bool:
    """
    Check if human QA approval is required for PASS results.
    Note: This flag is ignored in the current implementation.
    
    Returns:
        True if human QA required, False otherwise (default)
    """
    return get_safe_mode_settings()['human_qa_required']


def should_block_if_no_tsa() -> bool:
    """
    Check if certificate generation should be blocked when TSA is unavailable.
    
    Returns:
        True if should block, False to issue certificate with TSA retry (default)
    """
    return get_safe_mode_settings()['block_if_no_tsa']


def should_enforce_pdf_a3() -> bool:
    """
    Check if PDF/A-3 compliance should be strictly enforced.
    
    Returns:
        True to enforce (default), False to fallback gracefully
    """
    return get_safe_mode_settings()['enforce_pdf_a3']


def get_policy_summary() -> str:
    """
    Get a human-readable summary of current policy settings.
    
    Returns:
        String summary of policy configuration
    """
    settings = get_safe_mode_settings()
    status = []
    
    if settings['safe_mode']:
        status.append("Safe Mode: ENABLED")
    else:
        status.append("Safe Mode: DISABLED (permissive)")
        
    if settings['human_qa_required']:
        status.append("Human QA: REQUIRED")
    else:
        status.append("Human QA: BYPASSED")
        
    if settings['fail_on_parser_warnings']:
        status.append("Parser Warnings: BLOCKING")
    else:
        status.append("Parser Warnings: LOG ONLY")
        
    if settings['block_if_no_tsa']:
        status.append("TSA Required: BLOCKING")
    else:
        status.append("TSA Required: RETRY QUEUE")
    
    return " | ".join(status)


# Legacy compatibility - provide the flags directly
SAFE_MODE = is_safe_mode_enabled()
FAIL_ON_PARSER_WARNINGS = should_fail_on_parser_warnings()
HUMAN_QA_REQUIRED_FOR_PASS = is_human_qa_required()
BLOCK_IF_NO_TSA = should_block_if_no_tsa()
ENFORCE_PDF_A3 = should_enforce_pdf_a3()