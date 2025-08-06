#!/usr/bin/env python3
"""
Simple Postmark API test using only built-in modules.

Usage:
    python3 test_postmark_simple.py recipient@email.com
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

def test_postmark(recipient_email):
    """Test Postmark API with your credentials."""
    
    # Your Postmark configuration
    POSTMARK_TOKEN = "b67ff836-753c-418b-8b2e-43f54b3664e2"  # Try without pm- prefix
    FROM_EMAIL = "no-reply@proofkit.net"
    REPLY_TO_EMAIL = "support@proofkit.net"
    
    print(f"🚀 Testing Postmark API")
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
        <p><small>Sent from ProofKit test script at """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</small></p>
    </body>
    </html>
    """
    
    text_body = """
    🧪 Postmark Test Email
    
    This is a direct test of the Postmark API.
    If you receive this email, your Postmark configuration is working correctly!
    
    ---
    Sent from ProofKit test script at """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Prepare API request
    url = "https://api.postmarkapp.com/email"
    
    data = {
        "From": FROM_EMAIL,
        "To": recipient_email,
        "ReplyTo": REPLY_TO_EMAIL,
        "Subject": "🧪 ProofKit Postmark Test",
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": "outbound"
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_TOKEN
    }
    
    print("📡 Sending request to Postmark API...")
    
    try:
        # Create request
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers
        )
        
        # Send request
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode('utf-8')
            result = json.loads(response_data)
            
            print(f"📨 Response Status: {response.status}")
            print()
            print("✅ SUCCESS! Email sent via Postmark")
            print(f"   Message ID: {result.get('MessageID', 'Unknown')}")
            print(f"   Submitted At: {result.get('SubmittedAt', 'Unknown')}")
            print(f"   To: {result.get('To', 'Unknown')}")
            print()
            print("📧 Check your inbox for the test email!")
            return True
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ FAILED! Postmark returned error")
        print(f"   Status Code: {e.code}")
        print(f"   Response: {error_body}")
        
        try:
            error_data = json.loads(error_body)
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
        print("Usage: python3 test_postmark_simple.py <your-email@example.com>")
        sys.exit(1)
    
    recipient = sys.argv[1]
    
    print("🔬 Direct Postmark API Test")
    print("=" * 50)
    print()
    
    success = test_postmark(recipient)
    
    print()
    print("=" * 50)
    if success:
        print("🎉 Test PASSED - Postmark is working!")
        print("   Your API token and sender domain are correctly configured.")
        print()
        print("📝 Next steps:")
        print("   1. Deploy this configuration to production")
        print("   2. Try the magic link flow at https://www.proofkit.net/auth/get-started")
        print("   3. Check Fly.io logs: flyctl logs")
    else:
        print("❌ Test FAILED - Check the error above")
        print()
        print("Common issues:")
        print("   1. Invalid API token")
        print("   2. Sender signature not verified for no-reply@proofkit.net")
        print("   3. Account suspended or inactive")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()