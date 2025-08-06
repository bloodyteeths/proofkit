#!/usr/bin/env python3
"""
Download premium fonts for certificate generation.
"""

import os
import urllib.request
from pathlib import Path

def download_fonts():
    """Download Google Fonts for certificate."""
    fonts_dir = Path("fonts")
    fonts_dir.mkdir(exist_ok=True)
    
    fonts = {
        # Cormorant Garamond Bold
        "CormorantGaramond-Bold.ttf": "https://github.com/CatharsisFonts/Cormorant/raw/master/fonts/ttf/CormorantGaramond-Bold.ttf",
        
        # Inter Regular and Medium  
        "Inter-Regular.ttf": "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Regular.ttf",
        "Inter-Medium.ttf": "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Medium.ttf",
        
        # Great Vibes for signatures
        "GreatVibes-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/greatvibes/GreatVibes-Regular.ttf",
    }
    
    for filename, url in fonts.items():
        filepath = fonts_dir / filename
        if not filepath.exists():
            print(f"Downloading {filename}...")
            try:
                urllib.request.urlretrieve(url, filepath)
                print(f"  ✓ Downloaded {filename}")
            except Exception as e:
                print(f"  ✗ Failed to download {filename}: {e}")
        else:
            print(f"  ✓ {filename} already exists")
    
    print("\n✅ Fonts ready in ./fonts/")

if __name__ == "__main__":
    download_fonts()