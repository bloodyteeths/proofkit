"""
ProofKit Core Module

This module contains the core business logic for ProofKit including:
- Data normalization and validation
- Decision algorithms for pass/fail determination
- PDF rendering and plot generation
- Evidence bundle creation and verification

The core module is designed to be framework-agnostic and can be used
independently of the web interface or CLI.

Example usage:
    from core.normalize import normalize_csv_data
    from core.decide import make_decision
    from core.render_pdf import generate_proof_pdf
"""

__version__ = "0.1.0"
__all__ = [
    # Will be populated as modules are added
]