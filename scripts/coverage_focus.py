#!/usr/bin/env python3
"""
Coverage focus script - Parse coverage.xml and report missing lines for key modules.

Focuses on decide, cleanup, sterile, and coldchain modules to identify
uncovered lines that need testing attention.

Usage:
    python scripts/coverage_focus.py [coverage.xml]
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set


def parse_coverage_xml(xml_path: Path) -> Dict[str, Set[int]]:
    """
    Parse coverage.xml and extract missing lines for focus modules.
    
    Args:
        xml_path: Path to coverage.xml file
        
    Returns:
        Dict mapping module names to sets of missing line numbers
    """
    focus_modules = {"decide.py", "cleanup.py", "metrics_sterile.py", "metrics_coldchain.py"}
    missing_lines = {}
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Find all class elements (representing Python files)
        for class_elem in root.findall(".//class"):
            filename = class_elem.get("filename", "")
            
            if filename in focus_modules:
                module_missing = set()
                
                # Get all line elements
                for line_elem in class_elem.findall(".//line"):
                    line_num = int(line_elem.get("number"))
                    hits = int(line_elem.get("hits"))
                    
                    if hits == 0:
                        module_missing.add(line_num)
                
                if module_missing:
                    missing_lines[filename] = module_missing
                    
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        return {}
    except FileNotFoundError:
        print(f"Coverage file not found: {xml_path}", file=sys.stderr)
        return {}
    
    return missing_lines


def format_line_ranges(line_numbers: Set[int]) -> str:
    """
    Format line numbers into compact ranges (e.g., "1-3, 5, 7-9").
    
    Args:
        line_numbers: Set of line numbers
        
    Returns:
        Formatted string with line ranges
    """
    if not line_numbers:
        return ""
    
    sorted_lines = sorted(line_numbers)
    ranges = []
    start = sorted_lines[0]
    end = start
    
    for line in sorted_lines[1:]:
        if line == end + 1:
            end = line
        else:
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            start = end = line
    
    # Add the final range
    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{end}")
    
    return ", ".join(ranges)


def print_coverage_report(missing_lines: Dict[str, Set[int]]) -> None:
    """
    Print formatted coverage report for focus modules.
    
    Args:
        missing_lines: Dict mapping module names to missing line sets
    """
    if not missing_lines:
        print("✅ All focus modules have complete coverage!")
        return
    
    print("🎯 Coverage Focus Report")
    print("=" * 50)
    
    for module, lines in sorted(missing_lines.items()):
        line_count = len(lines)
        line_ranges = format_line_ranges(lines)
        
        print(f"\n📁 {module}")
        print(f"   Missing: {line_count} lines")
        print(f"   Lines:   {line_ranges}")
    
    total_missing = sum(len(lines) for lines in missing_lines.values())
    print(f"\n📊 Total missing lines: {total_missing}")
    print("\n💡 Focus testing efforts on these uncovered areas")


def main() -> None:
    """Main entry point for coverage focus script."""
    # Default to coverage.xml in current directory
    coverage_file = Path("coverage.xml")
    
    # Allow override via command line argument
    if len(sys.argv) > 1:
        coverage_file = Path(sys.argv[1])
    
    print(f"🔍 Analyzing coverage: {coverage_file}")
    
    missing_lines = parse_coverage_xml(coverage_file)
    print_coverage_report(missing_lines)


if __name__ == "__main__":
    main()