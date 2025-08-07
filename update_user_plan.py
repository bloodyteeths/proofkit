#!/usr/bin/env python3
"""
Script to update a user's plan in the quota system.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from middleware.quota import load_user_quota_data, save_user_quota_data

def update_user_plan(email: str, new_plan: str):
    """Update a user's plan."""
    print(f"Loading quota data for {email}...")
    
    # Load current data
    data = load_user_quota_data(email)
    
    print(f"Current plan: {data.get('plan', 'free')}")
    
    # Update plan
    data['plan'] = new_plan
    data['last_updated'] = datetime.now(timezone.utc).isoformat()
    
    # Save updated data
    success = save_user_quota_data(email, data)
    
    if success:
        print(f"✅ Successfully updated {email} to {new_plan} plan")
        
        # Verify the update
        updated_data = load_user_quota_data(email)
        print(f"Verified plan: {updated_data.get('plan')}")
    else:
        print(f"❌ Failed to update plan")

if __name__ == "__main__":
    # Update the specific user to starter plan
    update_user_plan("atanrikulu@e-listele.com", "starter")