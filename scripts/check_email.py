#!/usr/bin/env python3
"""
ProofKit Email Delivery Test Script

Tests magic-link email delivery using configured SMTP settings.
Reads credentials from environment variables and sends test emails.

Usage:
    python scripts/check_email.py --email test@example.com --test
    python scripts/check_email.py --email user@domain.com --magic-link
    python scripts/check_email.py --validate-dns
"""

import os
import sys
import smtplib
import subprocess
import argparse
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, Tuple
import json

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    requests = None

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False


class EmailTester:
    """Test email delivery and configuration."""
    
    def __init__(self):
        self.email_backend = os.getenv('EMAIL_BACKEND', 'ses')
        self.email_from = os.getenv('EMAIL_FROM', 'ProofKit <noreply@proofkit.com>')
        self.base_url = os.getenv('BASE_URL', 'https://proofkit-prod.fly.dev')
        
        # SES Configuration
        self.ses_host = os.getenv('SES_SMTP_HOST', 'email-smtp.us-east-1.amazonaws.com')
        self.ses_port = int(os.getenv('SES_SMTP_PORT', '587'))
        self.ses_username = os.getenv('SES_SMTP_USERNAME')
        self.ses_password = os.getenv('SES_SMTP_PASSWORD')
        
        # Postmark Configuration
        self.postmark_token = os.getenv('POSTMARK_API_TOKEN')
        
        print(f"🔧 Configured for {self.email_backend.upper()} backend")
        
    def validate_configuration(self) -> bool:
        """Validate email configuration."""
        print("🔍 Validating email configuration...")
        
        if not self.email_from:
            print("❌ EMAIL_FROM not configured")
            return False
            
        if self.email_backend == 'ses':
            if not all([self.ses_username, self.ses_password]):
                print("❌ SES credentials not configured (SES_SMTP_USERNAME, SES_SMTP_PASSWORD)")
                return False
            print("✅ SES configuration looks good")
            
        elif self.email_backend == 'postmark':
            if not self.postmark_token:
                print("❌ Postmark API token not configured (POSTMARK_API_TOKEN)")
                return False
            print("✅ Postmark configuration looks good")
            
        else:
            print(f"❌ Unknown email backend: {self.email_backend}")
            return False
            
        return True
    
    def test_smtp_connection(self) -> bool:
        """Test SMTP connection for SES."""
        if self.email_backend != 'ses':
            print("⏭️  SMTP test only applicable for SES backend")
            return True
            
        print(f"🔌 Testing SMTP connection to {self.ses_host}:{self.ses_port}...")
        
        try:
            server = smtplib.SMTP(self.ses_host, self.ses_port)
            server.set_debuglevel(0)  # Set to 1 for verbose debugging
            server.starttls()
            server.login(self.ses_username, self.ses_password)
            server.quit()
            print("✅ SMTP connection successful")
            return True
        except Exception as e:
            print(f"❌ SMTP connection failed: {e}")
            return False
    
    def validate_dns_records(self) -> Dict[str, bool]:
        """Validate DNS records for email authentication."""
        print("🌐 Validating DNS records...")
        
        if not DNS_AVAILABLE:
            print("⚠️  DNS validation skipped (dnspython not installed)")
            return {}
            
        domain = self.email_from.split('@')[-1].strip('>')
        results = {}
        
        # Check SPF record
        try:
            spf_records = dns.resolver.resolve(domain, 'TXT')
            spf_found = False
            for record in spf_records:
                if 'v=spf1' in str(record):
                    print(f"✅ SPF record found: {record}")
                    spf_found = True
                    break
            if not spf_found:
                print("❌ No SPF record found")
            results['spf'] = spf_found
        except Exception as e:
            print(f"❌ SPF check failed: {e}")
            results['spf'] = False
        
        # Check DMARC record
        try:
            dmarc_records = dns.resolver.resolve(f'_dmarc.{domain}', 'TXT')
            dmarc_found = False
            for record in dmarc_records:
                if 'v=DMARC1' in str(record):
                    print(f"✅ DMARC record found: {record}")
                    dmarc_found = True
                    break
            if not dmarc_found:
                print("❌ No DMARC record found")
            results['dmarc'] = dmarc_found
        except Exception as e:
            print(f"❌ DMARC check failed: {e}")
            results['dmarc'] = False
        
        # Check DKIM (basic check for SES)
        if self.email_backend == 'ses':
            try:
                # This is a simplified check - actual DKIM records are dynamic
                print("⚠️  DKIM validation requires manual verification in SES console")
                results['dkim'] = None
            except Exception:
                results['dkim'] = False
        
        return results
    
    def create_magic_link_email(self, recipient: str, is_test: bool = False) -> Tuple[str, str]:
        """Create magic link email content."""
        # Generate test magic link
        token = str(uuid.uuid4())
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        magic_url = f"{self.base_url}/auth/verify?token={token}"
        
        subject = "🔐 ProofKit Magic Link" + (" (TEST)" if is_test else "")
        
        # HTML version
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>ProofKit Magic Link</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                <h1 style="color: #2563eb; margin-bottom: 10px;">🔐 ProofKit Authentication</h1>
                {'<p style="color: #dc2626; font-weight: bold;">⚠️ TEST EMAIL - DO NOT USE IN PRODUCTION</p>' if is_test else ''}
                
                <p style="font-size: 16px; color: #374151; margin: 20px 0;">
                    Click the button below to securely access your ProofKit account:
                </p>
                
                <a href="{magic_url}" style="display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 20px 0;">
                    🔓 Access ProofKit
                </a>
                
                <p style="font-size: 14px; color: #6b7280; margin-top: 20px;">
                    This link expires at <strong>{expires.strftime('%Y-%m-%d %H:%M:%S UTC')}</strong><br>
                    If you didn't request this, you can safely ignore this email.
                </p>
                
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                
                <p style="font-size: 12px; color: #9ca3af;">
                    ProofKit - Industrial Temperature Validation<br>
                    This is an automated message. Please do not reply.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
        🔐 ProofKit Magic Link Authentication
        {'⚠️ TEST EMAIL - DO NOT USE IN PRODUCTION' if is_test else ''}
        
        Click this link to securely access your ProofKit account:
        {magic_url}
        
        This link expires at {expires.strftime('%Y-%m-%d %H:%M:%S UTC')}
        
        If you didn't request this, you can safely ignore this email.
        
        ---
        ProofKit - Industrial Temperature Validation
        This is an automated message. Please do not reply.
        """
        
        return subject, html_content, text_content
    
    def send_ses_email(self, recipient: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via SES SMTP."""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_from
            msg['To'] = recipient
            msg['Subject'] = subject
            
            # Add text and HTML parts
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send via SMTP
            server = smtplib.SMTP(self.ses_host, self.ses_port)
            server.starttls()
            server.login(self.ses_username, self.ses_password)
            server.send_message(msg)
            server.quit()
            
            print(f"✅ Email sent successfully via SES to {recipient}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email via SES: {e}")
            return False
    
    def send_postmark_email(self, recipient: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via Postmark API."""
        if not requests:
            print("❌ requests library not available for Postmark API")
            return False
            
        try:
            url = "https://api.postmarkapp.com/email"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": self.postmark_token
            }
            
            data = {
                "From": self.email_from,
                "To": recipient,
                "Subject": subject,
                "HtmlBody": html_content,
                "TextBody": text_content,
                "MessageStream": "outbound"
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Email sent successfully via Postmark to {recipient}")
                print(f"   Message ID: {result.get('MessageID', 'Unknown')}")
                return True
            else:
                print(f"❌ Postmark API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to send email via Postmark: {e}")
            return False
    
    def send_test_email(self, recipient: str, is_test: bool = True) -> bool:
        """Send a test magic link email."""
        print(f"📧 Sending {'test ' if is_test else ''}email to {recipient}...")
        
        subject, html_content, text_content = self.create_magic_link_email(recipient, is_test)
        
        if self.email_backend == 'ses':
            return self.send_ses_email(recipient, subject, html_content, text_content)
        elif self.email_backend == 'postmark':
            return self.send_postmark_email(recipient, subject, html_content, text_content)
        else:
            print(f"❌ Unsupported email backend: {self.email_backend}")
            return False
    
    def run_full_test(self, test_email: str) -> bool:
        """Run comprehensive email system test."""
        print("🧪 Running comprehensive email system test...\n")
        
        all_passed = True
        
        # 1. Validate configuration
        if not self.validate_configuration():
            all_passed = False
        print()
        
        # 2. Test SMTP connection (SES only)
        if not self.test_smtp_connection():
            all_passed = False
        print()
        
        # 3. Validate DNS records
        dns_results = self.validate_dns_records()
        if dns_results and not all(v for v in dns_results.values() if v is not None):
            print("⚠️  Some DNS records may need attention")
        print()
        
        # 4. Send test email
        if not self.send_test_email(test_email, is_test=True):
            all_passed = False
        print()
        
        # Summary
        print("📊 Test Summary:")
        print(f"   Configuration: {'✅' if self.validate_configuration() else '❌'}")
        print(f"   SMTP Connection: {'✅' if self.test_smtp_connection() else '❌'}")
        print(f"   DNS Records: {'⚠️' if dns_results else '⏭️'}")
        print(f"   Email Delivery: {'✅' if all_passed else '❌'}")
        print(f"   Overall: {'✅ PASS' if all_passed else '❌ ISSUES FOUND'}")
        
        return all_passed


def main():
    parser = argparse.ArgumentParser(description='Test ProofKit email delivery system')
    parser.add_argument('--email', required=True, help='Test email address')
    parser.add_argument('--test', action='store_true', help='Send test email (safe for production)')
    parser.add_argument('--magic-link', action='store_true', help='Send realistic magic link email')
    parser.add_argument('--validate-dns', action='store_true', help='Only validate DNS records')
    parser.add_argument('--full-test', action='store_true', help='Run comprehensive test suite')
    
    args = parser.parse_args()
    
    tester = EmailTester()
    
    try:
        if args.validate_dns:
            tester.validate_dns_records()
        elif args.full_test or (not args.magic_link and not args.validate_dns):
            success = tester.run_full_test(args.email)
            sys.exit(0 if success else 1)
        else:
            is_test = args.test and not args.magic_link
            success = tester.send_test_email(args.email, is_test)
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\n⏸️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()