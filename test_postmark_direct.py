#!/usr/bin/env python3
"""
Direct test of Postmark API to verify credentials and sending.

Usage:
    python3 test_postmark_direct.py your-email@example.com
"""

import sys
import httpx
import json

def test_postmark_directly(recipient_email):
    """Test Postmark API directly with your credentials."""
    
    # Your Postmark configuration
    POSTMARK_TOKEN = "pm-b67ff836-753c-418b-8b2e-43f54b3664e2"
    FROM_EMAIL = "no-reply@proofkit.net"
    REPLY_TO_EMAIL = "support@proofkit.net"
    
    print(f"🚀 Testing Postmark API Directly")
    print("=" * 50)
    print(f"Token: {POSTMARK_TOKEN[:15]}...")
    print(f"From: {FROM_EMAIL}")
    print(f"To: {recipient_email}")
    print()
    
    # Email content
    html_body = """
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>🧪 Postmark Test Email</h1>
        <p>This is a direct test of the Postmark API.</p>
        <p>If you receive this email, your Postmark configuration is working correctly!</p>
        <hr>
        <p><small>Sent from ProofKit test script</small></p>
    </body>
    </html>
    """
    
    text_body = """
    🧪 Postmark Test Email
    
    This is a direct test of the Postmark API.
    If you receive this email, your Postmark configuration is working correctly!
    
    ---
    Sent from ProofKit test script
    """
    
    # Prepare API request
    url = "https://api.postmarkapp.com/email"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_TOKEN
    }
    
    data = {
        "From": FROM_EMAIL,
        "To": recipient_email,
        "ReplyTo": REPLY_TO_EMAIL,
        "Subject": "🧪 ProofKit Postmark Test",
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": "outbound"
    }
    
    print("📡 Sending request to Postmark API...")
    print(f"   URL: {url}")
    print(f"   Headers: {json.dumps({k: v[:20] + '...' if k == 'X-Postmark-Server-Token' else v for k, v in headers.items()}, indent=4)}")
    print()
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=data)
        
        print(f"📨 Response Status: {response.status_code}")
        print(f"   Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS! Email sent via Postmark")
            print(f"   Message ID: {result.get('MessageID', 'Unknown')}")
            print(f"   Submitted At: {result.get('SubmittedAt', 'Unknown')}")
            print(f"   To: {result.get('To', 'Unknown')}")
            print()
            print("📧 Check your inbox for the test email!")
            return True
        else:
            print(f"❌ FAILED! Postmark returned error")
            print(f"   Response: {response.text}")
            
            try:
                error_data = response.json()
                print(f"   Error Code: {error_data.get('ErrorCode', 'Unknown')}")
                print(f"   Message: {error_data.get('Message', 'Unknown')}")
            except:
                pass
            
            return False
            
    except Exception as e:
        print(f"❌ Exception occurred: {e}")
        return False


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 test_postmark_direct.py <your-email@example.com>")
        sys.exit(1)
    
    recipient = sys.argv[1]
    
    print("🔬 Direct Postmark API Test")
    print("=" * 50)
    print()
    
    success = test_postmark_directly(recipient)
    
    print()
    print("=" * 50)
    if success:
        print("🎉 Test PASSED - Postmark is working!")
        print("   Your API token and sender domain are correctly configured.")
        print()
        print("📝 Next steps:")
        print("   1. Try the magic link flow at https://www.proofkit.net/auth/get-started")
        print("   2. Check Fly.io logs: flyctl logs")
        print("   3. Look for 'Email config' and 'Postmark API' log entries")
    else:
        print("❌ Test FAILED - Check the error above")
        print()
        print("Common issues:")
        print("   1. Sender signature not verified for no-reply@proofkit.net")
        print("   2. API token is incorrect or inactive")
        print("   3. Domain not properly configured in Postmark")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()