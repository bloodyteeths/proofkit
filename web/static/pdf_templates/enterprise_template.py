"""
Enterprise Tier PDF Template Configuration

This module defines the template configuration for enterprise tier certificates,
including white-label options and full customization capabilities.

Example usage:
    from web.static.pdf_templates.enterprise_template import ENTERPRISE_TEMPLATE_CONFIG
    white_label = ENTERPRISE_TEMPLATE_CONFIG['features']['white_label']
"""

from reportlab.lib import colors

ENTERPRISE_TEMPLATE_CONFIG = {
    'name': 'Enterprise',
    'tier': 'enterprise',
    'watermark': None,  # No watermark for enterprise
    'header': {
        'show_logo': True,
        'logo_max_width': 3.0,  # inches - larger for enterprise
        'logo_max_height': 1.5,  # inches
        'show_plan_name': False,
        'header_strip': True,
        'custom_header_strip': True  # Enterprise can customize header strip
    },
    'branding': {
        'show_powered_by': False,  # White-label option
        'show_website': False,
        'footer_text': None,  # Completely customizable
        'removable_branding': True
    },
    'features': {
        'custom_colors': True,
        'remove_watermark': True,
        'white_label': True,
        'logo_upload': True,
        'custom_fonts': True,  # Future feature
        'api_access': True
    },
    'logo': {
        'allowed_formats': ['PNG', 'JPG', 'JPEG', 'GIF', 'SVG'],
        'max_file_size': 10 * 1024 * 1024,  # 10MB for enterprise
        'recommended_size': '400x200px',
        'position': 'configurable',
        'multiple_logos': True  # Future: multiple logo support
    },
    'customization': {
        'custom_color_scheme': True,
        'custom_footer_text': True,
        'remove_all_branding': True,
        'custom_certificate_title': True,
        'api_integration': True
    },
    'certificate_text': {
        'enterprise_notice': 'Enterprise-grade certificate with full customization.',
        'validity': 'Unlimited production use with API access and custom branding.'
    }
}


def is_white_label_enabled() -> bool:
    """
    Check if enterprise tier has white-label features enabled.
    
    Returns:
        True for enterprise tier (full white-label support)
        
    Example:
        >>> if is_white_label_enabled():
        ...     remove_proofkit_branding()
    """
    return ENTERPRISE_TEMPLATE_CONFIG['features']['white_label']


def get_customization_options() -> dict:
    """
    Get available customization options for enterprise tier.
    
    Returns:
        Dictionary with customization capabilities
        
    Example:
        >>> options = get_customization_options()
        >>> if options['custom_color_scheme']:
        ...     show_color_picker()
    """
    return ENTERPRISE_TEMPLATE_CONFIG['customization']


def get_template_features() -> list:
    """
    Get list of features available in enterprise tier.
    
    Returns:
        List of feature strings
        
    Example:
        >>> features = get_template_features()
        >>> for feature in features:
        ...     print(f"★ {feature}")
    """
    return [
        'Complete white-label customization',
        'Remove all ProofKit branding',
        'Unlimited certificates',
        'Custom logo and color schemes',
        'API access for automation',
        'Dedicated account management',
        'Custom certificate titles',
        'Priority phone support',
        'SLA guarantees'
    ]


def create_custom_branding(
    company_name: str,
    logo_path: str = None,
    color_scheme: dict = None,
    custom_footer: str = None
) -> dict:
    """
    Create custom branding configuration for enterprise client.
    
    Args:
        company_name: Client company name
        logo_path: Optional path to company logo
        color_scheme: Optional custom colors
        custom_footer: Optional custom footer text
        
    Returns:
        Custom branding configuration
        
    Example:
        >>> branding = create_custom_branding(
        ...     'Acme Corp',
        ...     logo_path='/logos/acme.png',
        ...     custom_footer='Acme Corp Quality Assurance Division'
        ... )
    """
    return {
        'company_name': company_name,
        'logo_path': logo_path,
        'color_scheme': color_scheme or {
            'primary': '#1a365d',
            'secondary': '#2d3748',
            'accent': '#3182ce'
        },
        'footer_text': custom_footer or f'{company_name} Certificate Validation',
        'header_strip': f'{company_name} Quality Management System',
        'show_proofkit_branding': False,
        'certificate_title_prefix': f'{company_name}',
        'white_label': True
    }


def validate_enterprise_config(config: dict) -> tuple:
    """
    Validate enterprise customization configuration.
    
    Args:
        config: Enterprise configuration dictionary
        
    Returns:
        Tuple of (is_valid, error_messages)
        
    Example:
        >>> config = {'company_name': 'Test Corp'}
        >>> valid, errors = validate_enterprise_config(config)
        >>> if not valid:
        ...     for error in errors:
        ...         print(f"Config error: {error}")
    """
    errors = []
    
    # Required fields
    required_fields = ['company_name']
    for field in required_fields:
        if not config.get(field):
            errors.append(f"Missing required field: {field}")
    
    # Validate company name
    company_name = config.get('company_name', '')
    if len(company_name) < 2:
        errors.append("Company name must be at least 2 characters")
    if len(company_name) > 100:
        errors.append("Company name must be less than 100 characters")
    
    # Validate logo if provided
    logo_path = config.get('logo_path')
    if logo_path:
        import os
        if not os.path.exists(logo_path):
            errors.append(f"Logo file not found: {logo_path}")
    
    # Validate color scheme if provided
    color_scheme = config.get('color_scheme')
    if color_scheme:
        required_colors = ['primary', 'secondary', 'accent']
        for color in required_colors:
            if color not in color_scheme:
                errors.append(f"Missing color in scheme: {color}")
    
    return len(errors) == 0, errors