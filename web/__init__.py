"""
ProofKit Web Module

This module contains the web interface components for ProofKit including:
- FastAPI route handlers
- Jinja2 templates for HTML rendering
- Static file serving
- File upload handling

The web module provides a simple single-page interface for uploading
CSV files and specifications, then returning proof PDFs and evidence bundles.

Example usage:
    from web.routes import setup_routes
    from web.templates import render_template
"""

__version__ = "0.1.0"
__all__ = [
    # Will be populated as modules are added
]