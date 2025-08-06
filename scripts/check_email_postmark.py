#!/usr/bin/env python3
"""
Simple Postmark email test script for ProofKit.

Usage:
    python3 scripts/check_email_postmark.py recipient@email.com https://www.proofkit.net/magic/test123
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone

def send_postmark_email(recipient: str, magic_link: str) -> bool:
    """Send test email via Postmark API."""
    
    # Get configuration from environment
    postmark_token = os.getenv('POSTMARK_TOKEN', os.getenv('POSTMARK_API_TOKEN'))
    from_email = os.getenv('FROM_EMAIL', 'no-reply@proofkit.net')
    reply_to = os.getenv('REPLY_TO_EMAIL', 'support@proofkit.net')
    
    if not postmark_token:
        print("❌ POSTMARK_TOKEN or POSTMARK_API_TOKEN not set")
        return False
    
    # Check if it's a test token
    if postmark_token.startswith('POSTMARK_API_TEST'):
        print("🧪 Using Postmark TEST token - emails won't be delivered")
        print("   Test mode only validates API calls without sending")
    elif postmark_token.startswith('pm-'):
        print("📬 Using Postmark production token")
    
    # Email content
    subject = "🔐 ProofKit Magic Link (TEST)"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>ProofKit Magic Link</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
            <h1 style="color: white; margin: 0 0 20px 0; text-align: center;">
                🔐 ProofKit Authentication
            </h1>
            
            <div style="background: white; padding: 30px; border-radius: 8px;">
                <p style="color: #dc2626; font-weight: bold; text-align: center; margin-bottom: 20px;">
                    ⚠️ TEST EMAIL - Testing Email Delivery
                </p>
                
                <p style="font-size: 16px; color: #374151; margin: 20px 0;">
                    Click the button below to access ProofKit:
                </p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{magic_link}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                        🔓 Access ProofKit
                    </a>
                </div>
                
                <p style="font-size: 14px; color: #6b7280; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                    This is a test email sent at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                    Magic link: <code style="background: #f3f4f6; padding: 2px 4px; border-radius: 3px;">{magic_link}</code>
                </p>
            </div>
            
            <p style="font-size: 12px; color: rgba(255,255,255,0.8); text-align: center; margin-top: 20px;">
                ProofKit - Industrial Temperature Validation<br>
                This is an automated test message.
            </p>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    🔐 ProofKit Magic Link Authentication
    ⚠️ TEST EMAIL - Testing Email Delivery
    
    Click this link to access ProofKit:
    {magic_link}
    
    This is a test email sent at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
    
    ---
    ProofKit - Industrial Temperature Validation
    This is an automated test message.
    """
    
    # Send via Postmark API
    try:
        url = "https://api.postmarkapp.com/email"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": postmark_token
        }
        
        data = {
            "From": from_email,
            "To": recipient,
            "ReplyTo": reply_to,
            "Subject": subject,
            "HtmlBody": html_content,
            "TextBody": text_content,
            "MessageStream": "outbound"
        }
        
        print(f"📧 Sending test email to {recipient}...")
        print(f"   From: {from_email}")
        print(f"   Reply-To: {reply_to}")
        print(f"   Magic Link: {magic_link}")
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ Email sent successfully!")
            print(f"   Message ID: {result.get('MessageID', 'Unknown')}")
            print(f"   Submitted At: {result.get('SubmittedAt', 'Unknown')}")
            print(f"   To: {result.get('To', recipient)}")
            return True
        else:
            print(f"\n❌ Postmark API error: {response.status_code}")
            print(f"   Response: {response.text}")
            
            # Parse error details if available
            try:
                error_data = response.json()
                print(f"   Error Code: {error_data.get('ErrorCode', 'Unknown')}")
                print(f"   Message: {error_data.get('Message', 'Unknown')}")
            except:
                pass
            
            return False
            
    except Exception as e:
        print(f"\n❌ Failed to send email: {e}")
        return False


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/check_email_postmark.py <recipient_email> <magic_link_url>")
        print("Example: python3 scripts/check_email_postmark.py user@example.com https://www.proofkit.net/magic/test123")
        sys.exit(1)
    
    recipient = sys.argv[1]
    magic_link = sys.argv[2]
    
    print("🚀 ProofKit Postmark Email Test")
    print("=" * 50)
    
    # Check environment variables
    if not os.getenv('POSTMARK_TOKEN') and not os.getenv('POSTMARK_API_TOKEN'):
        print("\n⚠️  Warning: POSTMARK_TOKEN or POSTMARK_API_TOKEN not set")
        print("   Set it with: export POSTMARK_TOKEN=your-token-here")
    
    # Send the email
    success = send_postmark_email(recipient, magic_link)
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Test completed successfully!")
        print(f"   Check {recipient} for the test email")
    else:
        print("❌ Test failed - see error details above")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()