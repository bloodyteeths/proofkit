#!/usr/bin/env python3
"""
Create mock OTF font files for testing.
In production, you must provide the actual font files specified.
"""

import os
from pathlib import Path

def create_mock_fonts():
    """Create mock OTF files by copying existing TTF fonts."""
    font_mappings = [
        ("fonts/CormorantGaramond-Bold.ttf", "fonts/CormorantGaramondSC-ExtraBold.otf"),
        ("fonts/GreatVibes-Regular.ttf", "fonts/GreatVibes-Regular.otf"),
    ]
    
    # For Inter, we'll need to create mock files
    for source, target in font_mappings:
        if Path(source).exists():
            # Copy TTF as OTF (won't work properly but allows testing)
            Path(target).write_bytes(Path(source).read_bytes())
            print(f"✓ Created mock: {target}")
    
    # Create minimal mock OTF files for Inter fonts
    # These are NOT real fonts - just placeholders for testing
    mock_otf_header = b"OTTO\x00\x00\x00\x00" + b"\x00" * 100  # Minimal OTF header
    
    Path("fonts/Inter-Regular.otf").write_bytes(mock_otf_header)
    print("✓ Created mock: fonts/Inter-Regular.otf")
    
    Path("fonts/Inter-Medium.otf").write_bytes(mock_otf_header)
    print("✓ Created mock: fonts/Inter-Medium.otf")
    
    print("\n⚠️  WARNING: These are mock font files for testing only!")
    print("For production, you MUST provide the actual OTF font files.")

if __name__ == "__main__":
    create_mock_fonts()