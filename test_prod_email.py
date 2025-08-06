#!/usr/bin/env python3
"""Test production email sending directly."""

import urllib.request
import urllib.parse
import time

print("🔐 Testing ProofKit Production Email Flow")
print("=" * 50)

# Test email
test_email = f"test_{int(time.time())}@example.com"
print(f"Testing with email: {test_email}")
print()

# Send magic link request
url = "https://www.proofkit.net/auth/magic-link"
data = urllib.parse.urlencode({"email": test_email}).encode()

try:
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    
    with urllib.request.urlopen(req) as response:
        response_body = response.read().decode('utf-8')
        
        # Check what we got back
        if "Check Your Email" in response_body:
            print("✅ Magic link page displayed")
            
            # Check for dev mode indicators
            if "Development Mode" in response_body or "dev-link-container" in response_body:
                print("⚠️ WARNING: Still in development mode!")
                print("   The page is showing development mode content")
                
                # Extract dev link if present
                import re
                link_match = re.search(r'href="(/auth/verify\?token=[^"]+)"', response_body)
                if link_match:
                    print(f"   Dev link found: https://www.proofkit.net{link_match.group(1)}")
            else:
                print("✅ Production mode - no dev content visible")
                print("📧 Email should have been sent via Postmark")
        else:
            print("❌ Unexpected response")
            
except Exception as e:
    print(f"❌ Error: {e}")

print()
print("=" * 50)
print("Check your Postmark dashboard to see if email was sent to:")
print(f"  {test_email}")
print()
print("Also check Fly.io logs with:")
print(f"  flyctl logs --app proofkit-prod | grep '{test_email}'")