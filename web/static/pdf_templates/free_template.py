"""
Free Tier PDF Template Configuration

This module defines the template configuration for free tier certificates,
including watermarks and limited branding options.

Example usage:
    from web.static.pdf_templates.free_template import FREE_TEMPLATE_CONFIG
    watermark = FREE_TEMPLATE_CONFIG['watermark']
"""

from reportlab.lib import colors

FREE_TEMPLATE_CONFIG = {
    'name': 'Free Trial',
    'tier': 'free',
    'watermark': {
        'text': 'NOT FOR PRODUCTION USE',
        'color': colors.Color(0.8, 0.8, 0.8, 0.3),
        'font_size': 14,
        'position': 'top'
    },
    'header': {
        'show_logo': False,
        'show_plan_name': True,
        'header_strip': False
    },
    'branding': {
        'show_powered_by': True,
        'show_website': True,
        'footer_text': 'Powered by ProofKit • www.proofkit.net • Secure Temperature Validation'
    },
    'features': {
        'custom_colors': False,
        'remove_watermark': False,
        'white_label': False
    },
    'certificate_text': {
        'trial_notice': 'This is a trial certificate. Upgrade to remove watermark and enable production use.',
        'validity': 'Trial certificates are for evaluation purposes only.'
    }
}


def get_free_watermark_text() -> str:
    """
    Get watermark text for free tier certificates.
    
    Returns:
        Watermark text string
        
    Example:
        >>> text = get_free_watermark_text()
        >>> print(text)
        NOT FOR PRODUCTION USE
    """
    return FREE_TEMPLATE_CONFIG['watermark']['text']


def should_show_upgrade_prompt() -> bool:
    """
    Check if free tier should show upgrade prompts.
    
    Returns:
        True for free tier (always show upgrade options)
        
    Example:
        >>> if should_show_upgrade_prompt():
        ...     display_upgrade_modal()
    """
    return True


def get_template_limitations() -> list:
    """
    Get list of limitations for free tier.
    
    Returns:
        List of limitation strings
        
    Example:
        >>> limitations = get_template_limitations()
        >>> for limit in limitations:
        ...     print(f"• {limit}")
    """
    return [
        'Watermarked certificates',
        'No custom logo support',
        'Limited to 2 certificates total',
        'ProofKit branding required',
        'Not suitable for production use'
    ]