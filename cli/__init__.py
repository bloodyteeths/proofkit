"""
ProofKit CLI Module

This module contains the command-line interface for ProofKit using Typer.
The CLI provides granular control over the proof generation pipeline with
individual commands for each step.

Available commands:
- normalize: Process and validate CSV data
- decide: Apply decision algorithms to normalized data
- render: Generate proof PDF and plots
- pack: Create evidence bundle with manifest
- verify: Verify evidence bundle integrity

Example usage:
    from cli.main import app as cli_app
    
    # Or use directly from command line:
    # proofkit normalize --csv data.csv --spec spec.json
    # proofkit decide --csv normalized.csv --spec spec.json
"""

__version__ = "0.1.0"
__all__ = [
    # Will be populated as modules are added
]