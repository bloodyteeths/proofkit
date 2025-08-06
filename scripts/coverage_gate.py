#!/usr/bin/env python3
"""
Coverage Gate Script

Parses coverage.xml and enforces coverage thresholds:
- Total coverage >= 92%
- core/decide.py >= 92%
- cleanup/logging modules >= 90%

Prints a table with file coverage stats and fails if thresholds are not met.

Usage:
    python scripts/coverage_gate.py [--coverage-file coverage.xml]

Example:
    # Basic usage
    python scripts/coverage_gate.py
    
    # Custom coverage file
    python scripts/coverage_gate.py --coverage-file path/to/coverage.xml
"""

import sys
import argparse
import xml.etree.ElementTree as ET
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import re


@dataclass
class FileCoverage:
    """Coverage information for a single file"""
    filename: str
    line_rate: float
    lines_covered: int
    lines_valid: int
    branch_rate: float = 0.0
    branches_covered: int = 0
    branches_valid: int = 0
    
    @property
    def coverage_percentage(self) -> float:
        """Get coverage as percentage"""
        return self.line_rate * 100.0
    
    @property
    def lines_missed(self) -> int:
        """Get number of lines missed"""
        return self.lines_valid - self.lines_covered


@dataclass
class CoverageThreshold:
    """Coverage threshold definition"""
    pattern: str
    min_coverage: float
    description: str


class CoverageGate:
    """Coverage gate checker that enforces thresholds"""
    
    def __init__(self, coverage_file: str = "coverage.xml"):
        self.coverage_file = Path(coverage_file)
        self.file_coverage: Dict[str, FileCoverage] = {}
        self.total_coverage = 0.0
        
        # Define thresholds as per requirements
        self.thresholds = [
            CoverageThreshold(r"^decide\.py$", 92.0, "core/decide.py"),
            CoverageThreshold(r"^cleanup\.py$", 90.0, "cleanup module"), 
            CoverageThreshold(r"^logging\.py$", 90.0, "logging module"),
        ]
        
        self.total_threshold = 92.0
    
    def load_coverage_data(self) -> None:
        """Load and parse coverage.xml file"""
        if not self.coverage_file.exists():
            raise FileNotFoundError(f"Coverage file not found: {self.coverage_file}")
        
        try:
            tree = ET.parse(self.coverage_file)
            root = tree.getroot()
            
            # Get total coverage from root element
            self.total_coverage = float(root.get('line-rate', 0)) * 100.0
            
            # Parse individual file coverage
            for package in root.findall('.//package'):
                package_name = package.get('name', '')
                
                for class_elem in package.findall('.//class'):
                    filename = class_elem.get('filename', '')
                    line_rate = float(class_elem.get('line-rate', 0))
                    branch_rate = float(class_elem.get('branch-rate', 0))
                    
                    # Count lines
                    lines = class_elem.findall('.//line')
                    lines_valid = len(lines)
                    lines_covered = sum(1 for line in lines if int(line.get('hits', 0)) > 0)
                    
                    # Count branches (if available)
                    branches_valid = 0
                    branches_covered = 0
                    for line in lines:
                        branch_attr = line.get('branch', 'false')
                        if branch_attr == 'true':
                            condition_coverage = line.get('condition-coverage', '')
                            if condition_coverage:
                                # Parse condition coverage like "50% (1/2)"
                                match = re.search(r'\((\d+)/(\d+)\)', condition_coverage)
                                if match:
                                    covered = int(match.group(1))
                                    total = int(match.group(2))
                                    branches_covered += covered
                                    branches_valid += total
                    
                    # Normalize filename (remove leading ./ if present)
                    if filename.startswith('./'):
                        filename = filename[2:]
                    
                    self.file_coverage[filename] = FileCoverage(
                        filename=filename,
                        line_rate=line_rate,
                        lines_covered=lines_covered,
                        lines_valid=lines_valid,
                        branch_rate=branch_rate,
                        branches_covered=branches_covered,
                        branches_valid=branches_valid
                    )
                    
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse coverage XML: {e}")
        except Exception as e:
            raise ValueError(f"Error processing coverage data: {e}")
    
    def check_thresholds(self) -> Tuple[bool, List[str]]:
        """Check all coverage thresholds and return results"""
        failures = []
        
        # Validate coverage data exists
        if not self.file_coverage:
            failures.append("No coverage data available - ensure tests have been run with coverage collection enabled")
            return False, failures
        
        # Check total coverage
        if self.total_coverage < self.total_threshold:
            failures.append(
                f"Total coverage {self.total_coverage:.1f}% below threshold {self.total_threshold}%"
            )
        
        # Check specific file thresholds
        for threshold in self.thresholds:
            matching_files = [
                filename for filename in self.file_coverage.keys()
                if re.match(threshold.pattern, filename)
            ]
            
            if not matching_files:
                # Check if pattern might need adjustment (common issue)
                similar_files = [f for f in self.file_coverage.keys() if threshold.pattern.replace(r'\.py$', '.py') in f or threshold.pattern.replace(r'^', '').replace(r'\.py$', '.py') in f]
                if similar_files:
                    failures.append(f"No files found matching pattern '{threshold.pattern}' for {threshold.description}. Similar files found: {', '.join(similar_files[:3])}")
                else:
                    failures.append(f"No files found matching pattern '{threshold.pattern}' for {threshold.description}")
                continue
            
            for filename in matching_files:
                file_cov = self.file_coverage[filename]
                if file_cov.coverage_percentage < threshold.min_coverage:
                    failures.append(
                        f"{filename} coverage {file_cov.coverage_percentage:.1f}% below threshold {threshold.min_coverage}% ({threshold.description})"
                    )
        
        return len(failures) == 0, failures
    
    def print_coverage_table(self) -> None:
        """Print a formatted table of coverage statistics"""
        if not self.file_coverage:
            print("No coverage data available")
            return
        
        # Sort files by coverage percentage (lowest first)
        sorted_files = sorted(
            self.file_coverage.values(),
            key=lambda x: x.coverage_percentage
        )
        
        # Print header
        print("\nCoverage Report:")
        print("=" * 80)
        print(f"{'File':<40} {'Coverage':<10} {'Lines':<12} {'Missing':<8} {'Status':<8}")
        print("-" * 80)
        
        # Print file details
        for file_cov in sorted_files:
            # Determine status based on thresholds
            status = "PASS"
            for threshold in self.thresholds:
                if re.match(threshold.pattern, file_cov.filename):
                    if file_cov.coverage_percentage < threshold.min_coverage:
                        status = "FAIL"
                    break
            
            # Truncate long filenames
            display_name = file_cov.filename
            if len(display_name) > 38:
                display_name = "..." + display_name[-35:]
            
            print(f"{display_name:<40} {file_cov.coverage_percentage:>6.1f}%   "
                  f"{file_cov.lines_covered:>3}/{file_cov.lines_valid:<3}    "
                  f"{file_cov.lines_missed:>4}     {status:<8}")
        
        # Print summary
        print("-" * 80)
        print(f"{'Total Coverage':<40} {self.total_coverage:>6.1f}%")
        print(f"{'Total Files':<40} {len(self.file_coverage):>8}")
        
        # Print threshold summary
        print("\nThreshold Requirements:")
        print(f"- Total coverage: >= {self.total_threshold}%")
        for threshold in self.thresholds:
            print(f"- {threshold.description}: >= {threshold.min_coverage}%")
        
        # Print coverage increment information if this is a PR with the label
        if os.getenv('GITHUB_EVENT_NAME') == 'pull_request':
            print("\n💡 Coverage Increment Mode:")
            print("   - If this PR has the 'coverage-increment' label, coverage gate failures")
            print("     will not block the PR merge (continue-on-error: true)")  
            print("   - This allows gradual coverage improvements while maintaining CI flow")
            print("   - Coverage gates remain strict on main branch pushes")
    
    def run(self) -> int:
        """Run coverage gate check and return exit code"""
        try:
            print(f"Loading coverage data from {self.coverage_file}")
            self.load_coverage_data()
            
            print(f"Checking coverage thresholds...")
            passed, failures = self.check_thresholds()
            
            self.print_coverage_table()
            
            # Check if we're on main branch - strict enforcement always applies
            current_branch = os.getenv('GITHUB_REF_NAME', os.getenv('GITHUB_HEAD_REF', ''))
            is_main_branch = current_branch == 'main'
            
            if passed:
                print(f"\n✅ All coverage thresholds met!")
                return 0
            else:
                print(f"\n❌ Coverage gate failed:")
                for failure in failures:
                    print(f"  - {failure}")
                
                # On main branch, always fail strictly regardless of labels
                if is_main_branch:
                    print(f"\n🔒 Main branch detected - strict enforcement enabled")
                    print(f"   Coverage gates cannot be bypassed on main branch")
                    return 1
                else:
                    print(f"\n💡 Non-main branch - coverage gates may be relaxed with 'coverage-increment' label")
                    return 1
                
        except FileNotFoundError:
            print(f"Error: Coverage file '{self.coverage_file}' not found.", file=sys.stderr)
            print("Run tests with coverage collection enabled first:", file=sys.stderr)
            print("  python3 -m pytest tests/ --cov=core --cov-report=xml", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Check coverage thresholds from coverage.xml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--coverage-file",
        default="coverage.xml",
        help="Path to coverage.xml file (default: coverage.xml)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output with detailed information"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        print(f"Coverage gate script starting...")
        print(f"Coverage file: {args.coverage_file}")
    
    gate = CoverageGate(args.coverage_file)
    exit_code = gate.run()
    
    if args.verbose:
        print(f"Coverage gate finished with exit code: {exit_code}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()