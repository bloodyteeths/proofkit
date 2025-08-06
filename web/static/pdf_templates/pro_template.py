"""
Pro Tier PDF Template Configuration

This module defines the template configuration for pro tier certificates,
including custom logo support and enhanced branding options.

Example usage:
    from web.static.pdf_templates.pro_template import PRO_TEMPLATE_CONFIG
    logo_support = PRO_TEMPLATE_CONFIG['header']['show_logo']
"""

from reportlab.lib import colors

PRO_TEMPLATE_CONFIG = {
    'name': 'Professional',
    'tier': 'pro', 
    'watermark': None,  # No watermark for pro tier
    'header': {
        'show_logo': True,
        'logo_max_width': 2.0,  # inches
        'logo_max_height': 1.0,  # inches
        'show_plan_name': False,  # Don't show "Pro" in header
        'header_strip': False
    },
    'branding': {
        'show_powered_by': True,
        'show_website': True,
        'footer_text': 'Generated with ProofKit Professional • Secure Certificate Validation'
    },
    'features': {
        'custom_colors': False,  # Future feature
        'remove_watermark': True,
        'white_label': False,
        'logo_upload': True
    },
    'logo': {
        'allowed_formats': ['PNG', 'JPG', 'JPEG', 'GIF'],
        'max_file_size': 2 * 1024 * 1024,  # 2MB
        'recommended_size': '200x100px',
        'position': 'top-left'
    },
    'certificate_text': {
        'professional_notice': 'This professional certificate includes custom branding.',
        'validity': 'Suitable for production and compliance use.'
    }
}


def supports_custom_logo() -> bool:
    """
    Check if pro tier supports custom logo.
    
    Returns:
        True for pro tier (supports custom logos)
        
    Example:
        >>> if supports_custom_logo():
        ...     show_logo_upload_option()
    """
    return PRO_TEMPLATE_CONFIG['features']['logo_upload']


def get_logo_requirements() -> dict:
    """
    Get logo upload requirements for pro tier.
    
    Returns:
        Dictionary with logo requirements
        
    Example:
        >>> requirements = get_logo_requirements()
        >>> print(f"Max size: {requirements['max_file_size']} bytes")
    """
    return PRO_TEMPLATE_CONFIG['logo']


def get_template_features() -> list:
    """
    Get list of features available in pro tier.
    
    Returns:
        List of feature strings
        
    Example:
        >>> features = get_template_features()
        >>> for feature in features:
        ...     print(f"✓ {feature}")
    """
    return [
        'Custom logo in certificate header',
        'No watermarks or trial limitations',
        '75 certificates per month included',
        'Professional certificate appearance',
        'Suitable for production use',
        'Priority email support'
    ]


def validate_logo_file(file_path: str, file_size: int) -> tuple:
    """
    Validate uploaded logo file for pro tier.
    
    Args:
        file_path: Path to uploaded logo file
        file_size: Size of file in bytes
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_logo_file('logo.png', 1500000)
        >>> if not valid:
        ...     print(f"Logo error: {error}")
    """
    import os
    from pathlib import Path
    
    # Check file exists
    if not os.path.exists(file_path):
        return False, "Logo file not found"
    
    # Check file size
    max_size = PRO_TEMPLATE_CONFIG['logo']['max_file_size']
    if file_size > max_size:
        return False, f"Logo file too large. Maximum size: {max_size // 1024 // 1024}MB"
    
    # Check file format
    extension = Path(file_path).suffix.upper().lstrip('.')
    allowed_formats = PRO_TEMPLATE_CONFIG['logo']['allowed_formats']
    if extension not in allowed_formats:
        return False, f"Invalid logo format. Allowed: {', '.join(allowed_formats)}"
    
    return True, "Logo file is valid"