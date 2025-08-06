#!/usr/bin/env python3
"""
Test script to verify Postmark integration for magic links.

Usage:
    python3 test_magic_link_postmark.py your-email@example.com
"""

import os
import sys
import httpx
from datetime import datetime

def test_signup(email: str):
    """Test the signup flow with Postmark email."""
    
    # Use production URL
    base_url = "https://www.proofkit.net"
    
    print(f"🚀 Testing Magic Link Signup Flow")
    print("=" * 50)
    print(f"Email: {email}")
    print(f"URL: {base_url}/auth/signup")
    print()
    
    # Test signup endpoint
    try:
        print("📝 Submitting signup form...")
        
        # Submit signup form
        response = httpx.post(
            f"{base_url}/auth/signup",
            data={
                "email": email,
                "company": "Test Company",
                "industry": "powder-coating",
                "terms": "on",
                "marketing": "on"
            },
            follow_redirects=True
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            # Check if we got the magic link sent page
            if "Check Your Email" in response.text or "magic link" in response.text.lower():
                print("✅ Signup successful! Magic link page displayed.")
                print()
                print("📧 Please check your email for the magic link.")
                print("   - From: no-reply@proofkit.net")
                print("   - Subject: ProofKit Login - OP Access")
                print()
                
                # Check if dev link is shown (for testing)
                if "dev-link" in response.text or "Development Mode" in response.text:
                    print("🔧 Development mode detected - link may be shown on page")
                    
                return True
            else:
                print("⚠️ Unexpected response content")
                print("   Page title or content doesn't match expected magic link page")
                return False
        else:
            print(f"❌ Signup failed with status code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error during signup test: {e}")
        return False


def test_api_signup(email: str):
    """Test the API signup endpoint directly."""
    
    base_url = "https://www.proofkit.net"
    
    print()
    print("🔌 Testing API Signup Endpoint")
    print("=" * 50)
    
    try:
        print("📡 Calling /api/signup endpoint...")
        
        response = httpx.post(
            f"{base_url}/api/signup",
            json={
                "email": email,
                "plan": "free",
                "role": "op"
            }
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ API signup successful!")
            print(f"   Message: {data.get('message', 'No message')}")
            print(f"   Expires in: {data.get('expires_in', 'Unknown')} seconds")
            
            if "dev_link" in data:
                print(f"   Dev Link: {data['dev_link']}")
                
            return True
        else:
            print(f"❌ API signup failed")
            if response.text:
                try:
                    error = response.json()
                    print(f"   Error: {error.get('detail', 'Unknown error')}")
                except:
                    print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Error during API test: {e}")
        return False


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 test_magic_link_postmark.py <your-email@example.com>")
        sys.exit(1)
    
    email = sys.argv[1]
    
    print("🔐 ProofKit Magic Link Test (Postmark Integration)")
    print("=" * 50)
    print(f"Testing with email: {email}")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    # Test form-based signup
    form_success = test_signup(email)
    
    # Test API signup
    api_success = test_api_signup(email)
    
    print()
    print("=" * 50)
    print("📊 Test Results:")
    print(f"   Form Signup: {'✅ PASS' if form_success else '❌ FAIL'}")
    print(f"   API Signup: {'✅ PASS' if api_success else '❌ FAIL'}")
    print()
    
    if form_success or api_success:
        print("🎉 At least one signup method worked!")
        print("📧 Check your email for the magic link from ProofKit")
        print()
        print("Expected email details:")
        print("  From: no-reply@proofkit.net")
        print("  Subject: ProofKit Login - OP Access")
        print("  Contains: Magic link button to access ProofKit")
    else:
        print("❌ Both signup methods failed - check logs for details")
    
    sys.exit(0 if (form_success or api_success) else 1)


if __name__ == '__main__':
    main()