#!/usr/bin/env python3
"""
ProofKit Test Runner

Simple test runner script to validate the pytest test suite.
Use this to run all tests or specific test modules.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py test_normalize     # Run normalize tests only
    python run_tests.py -v                 # Run with verbose output
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run pytest with appropriate arguments."""
    # Change to project directory
    project_dir = Path(__file__).parent
    
    # Build pytest command
    cmd = ["python3", "-m", "pytest"]
    
    # Add command line arguments
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])
    else:
        # Default: run all tests with some verbosity
        cmd.extend(["-v", "tests/"])
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {project_dir}")
    print("-" * 50)
    
    # Run pytest
    try:
        result = subprocess.run(cmd, cwd=project_dir)
        return result.returncode
    except FileNotFoundError:
        print("Error: pytest not found. Please install pytest:")
        print("  pip install pytest")
        return 1
    except KeyboardInterrupt:
        print("\nTest run interrupted by user")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)