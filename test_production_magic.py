#!/usr/bin/env python3
"""
Test the production magic link flow on ProofKit.
"""

import urllib.request
import urllib.parse
import json

def test_magic_link(email):
    """Test magic link generation in production."""
    
    print(f"🔐 Testing Magic Link Flow for {email}")
    print("=" * 50)
    
    # Test the /auth/magic-link endpoint
    url = "https://www.proofkit.net/auth/magic-link"
    data = urllib.parse.urlencode({"email": email}).encode()
    
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        with urllib.request.urlopen(req) as response:
            # Check if redirect happened (should redirect to magic-link-sent page)
            final_url = response.geturl()
            response_body = response.read().decode('utf-8')
            
            if "Check Your Email" in response_body or "magic link" in response_body.lower():
                print("✅ Magic link request successful!")
                print("   Page shows: 'Check Your Email' message")
                print(f"   Final URL: {final_url}")
                
                # Check for dev link in response
                if "dev-link" in response_body or "Development Mode" in response_body:
                    print("   ⚠️ Development mode detected (link shown on page)")
                else:
                    print("   📧 Production mode - email should be sent")
                
                return True
            else:
                print("❌ Unexpected response")
                print(f"   Status: {response.status}")
                print(f"   URL: {final_url}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_api_endpoint(email):
    """Test the API endpoint directly."""
    
    print()
    print("🔌 Testing API Endpoint")
    print("-" * 30)
    
    url = "https://www.proofkit.net/api/signup"
    data = json.dumps({
        "email": email,
        "plan": "free",
        "role": "op"
    }).encode('utf-8')
    
    try:
        req = urllib.request.Request(url, data=data)
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            print("✅ API call successful!")
            print(f"   Message: {result.get('message', 'No message')}")
            print(f"   Expires in: {result.get('expires_in', 'Unknown')} seconds")
            
            if "dev_link" in result:
                print(f"   ⚠️ Dev Link provided: {result['dev_link']}")
            
            return True
            
    except Exception as e:
        print(f"❌ API Error: {e}")
        return False


def main():
    email = "ramoetsy@gmail.com"
    
    print("🚀 ProofKit Production Magic Link Test")
    print("=" * 50)
    print()
    
    # Test form-based flow
    form_success = test_magic_link(email)
    
    # Test API flow
    api_success = test_api_endpoint(email)
    
    print()
    print("=" * 50)
    print("📊 Test Results:")
    print(f"   Form-based flow: {'✅ PASS' if form_success else '❌ FAIL'}")
    print(f"   API endpoint: {'✅ PASS' if api_success else '❌ FAIL'}")
    
    if form_success or api_success:
        print()
        print("🎉 Magic link system is working!")
        print(f"📧 Check {email} for the magic link email")
        print()
        print("Expected email:")
        print("  From: no-reply@proofkit.net")
        print("  Subject: ProofKit Login - OP Access")
    else:
        print()
        print("❌ Both methods failed - check server logs")


if __name__ == '__main__':
    main()