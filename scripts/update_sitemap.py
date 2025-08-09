#!/usr/bin/env python3
"""
Sitemap Update Script

This script updates the sitemap.xml with current timestamps and can be used
to submit the sitemap to Google Search Console.

Usage:
    python scripts/update_sitemap.py [--submit]
    
Example:
    python scripts/update_sitemap.py --submit
"""

import sys
import os
import re
from datetime import datetime
from pathlib import Path
import requests
from typing import Optional

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def update_sitemap_timestamps(sitemap_path: Path, date_str: Optional[str] = None) -> bool:
    """
    Update all lastmod timestamps in the sitemap to today's date.
    
    Args:
        sitemap_path: Path to the sitemap.xml file
        date_str: Optional date string to use (format: YYYY-MM-DD)
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        update_sitemap_timestamps(Path("web/static/sitemap.xml"))
    """
    if not sitemap_path.exists():
        print(f"❌ Sitemap not found: {sitemap_path}")
        return False
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Read the sitemap
        with open(sitemap_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update all lastmod dates
        pattern = r'<lastmod>\d{4}-\d{2}-\d{2}</lastmod>'
        replacement = f'<lastmod>{date_str}</lastmod>'
        updated_content = re.sub(pattern, replacement, content)
        
        # Write back to file
        with open(sitemap_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        # Count updates
        matches = len(re.findall(pattern, content))
        print(f"✅ Updated {matches} lastmod entries to {date_str}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update sitemap: {e}")
        return False

def submit_to_google_search_console(sitemap_url: str) -> bool:
    """
    Submit sitemap to Google Search Console via ping endpoint.
    
    Args:
        sitemap_url: Full URL to the sitemap
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        submit_to_google_search_console("https://www.proofkit.net/sitemap.xml")
    """
    try:
        ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
        response = requests.get(ping_url, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Successfully submitted sitemap to Google Search Console")
            print(f"   Ping URL: {ping_url}")
            return True
        else:
            print(f"❌ Failed to submit sitemap. Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to submit sitemap: {e}")
        return False

def validate_sitemap_xml(sitemap_path: Path) -> bool:
    """
    Basic validation of sitemap XML format.
    
    Args:
        sitemap_path: Path to the sitemap.xml file
        
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        with open(sitemap_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Basic checks
        checks = [
            ('<?xml version="1.0"' in content, "XML declaration"),
            ('<urlset' in content, "URL set element"),
            ('</urlset>' in content, "Closing URL set"),
            (content.count('<url>') == content.count('</url>'), "Matching URL tags"),
            (content.count('<loc>') == content.count('</loc>'), "Matching loc tags"),
        ]
        
        passed = 0
        for check, description in checks:
            if check:
                print(f"✅ {description}")
                passed += 1
            else:
                print(f"❌ {description}")
        
        url_count = content.count('<url>')
        print(f"📊 Found {url_count} URLs in sitemap")
        
        return passed == len(checks)
        
    except Exception as e:
        print(f"❌ Failed to validate sitemap: {e}")
        return False

def main():
    """Main function to handle command line arguments and run the script."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update and submit sitemap')
    parser.add_argument('--submit', action='store_true', 
                       help='Submit sitemap to Google Search Console after updating')
    parser.add_argument('--date', type=str, 
                       help='Date to use for lastmod (YYYY-MM-DD format)')
    parser.add_argument('--validate', action='store_true',
                       help='Validate sitemap XML format')
    args = parser.parse_args()
    
    # Determine paths
    project_root = Path(__file__).parent.parent
    sitemap_path = project_root / "web" / "static" / "sitemap.xml"
    sitemap_url = "https://www.proofkit.net/sitemap.xml"
    
    print("🔄 ProofKit Sitemap Update Script")
    print("=" * 40)
    
    # Validate if requested
    if args.validate:
        print("\n📋 Validating sitemap...")
        if not validate_sitemap_xml(sitemap_path):
            print("❌ Sitemap validation failed")
            sys.exit(1)
        print("✅ Sitemap validation passed")
    
    # Update timestamps
    print(f"\n📅 Updating sitemap timestamps...")
    if not update_sitemap_timestamps(sitemap_path, args.date):
        print("❌ Failed to update sitemap")
        sys.exit(1)
    
    # Submit if requested
    if args.submit:
        print(f"\n🚀 Submitting to Google Search Console...")
        if not submit_to_google_search_console(sitemap_url):
            print("❌ Failed to submit sitemap")
            sys.exit(1)
    
    print("\n✅ Sitemap update completed successfully!")
    print(f"   Local path: {sitemap_path}")
    print(f"   Public URL: {sitemap_url}")
    
    if not args.submit:
        print("\n💡 Tip: Use --submit flag to automatically submit to Google Search Console")

if __name__ == "__main__":
    main()