#!/usr/bin/env python3
"""Test the complete email flow with proper UserRole."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth.models import UserRole
from auth.magic import MagicLinkAuth

def test_email_generation():
    """Test that email generation works with UserRole."""
    
    # Set environment for testing
    os.environ['POSTMARK_TOKEN'] = 'b67ff836-753c-418b-8b2e-43f54b3664e2'
    os.environ['FROM_EMAIL'] = 'no-reply@proofkit.net'
    os.environ['REPLY_TO_EMAIL'] = 'support@proofkit.net'
    os.environ['EMAIL_DEV_MODE'] = 'false'
    os.environ['BASE_URL'] = 'https://www.proofkit.net'
    
    auth = MagicLinkAuth()
    
    # Test with proper UserRole
    email = "test@example.com"
    magic_token = "test_token_123"
    
    print("Testing with UserRole.OPERATOR...")
    try:
        result = auth.send_magic_link_email(email, magic_token, UserRole.OPERATOR)
        print(f"✅ Result: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\nTesting with string 'op' (should be converted)...")
    try:
        result = auth.send_magic_link_email(email, magic_token, "op")
        print(f"✅ Result: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_email_generation()