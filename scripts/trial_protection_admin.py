#!/usr/bin/env python3
"""
Trial Protection Admin Utility

Commands:
  stats    - Show trial usage statistics
  clean    - Clean up old trial data (older than cooldown period)
  reset    - Reset trial data for specific IP or email
  list     - List all tracked IPs and emails
  check    - Check if IP or email would be blocked
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def load_trial_data():
    """Load trial tracking data."""
    trial_path = Path("storage/trial_tracking/trial_data.json")
    if trial_path.exists():
        with open(trial_path, 'r') as f:
            return json.load(f)
    return {"ip_trials": {}, "fingerprint_trials": {}, "email_ips": {}}

def save_trial_data(data):
    """Save trial tracking data."""
    trial_path = Path("storage/trial_tracking/trial_data.json")
    trial_path.parent.mkdir(parents=True, exist_ok=True)
    with open(trial_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def show_stats():
    """Display trial usage statistics."""
    data = load_trial_data()
    
    print("=== Trial Protection Statistics ===")
    print(f"Total tracked IPs: {len(data.get('ip_trials', {}))}")
    print(f"Total tracked fingerprints: {len(data.get('fingerprint_trials', {}))}")
    print(f"Total tracked emails: {len(data.get('email_ips', {}))}")
    print()
    
    # Show suspicious IPs
    max_trials_per_ip = 2  # Could read from env
    suspicious_ips = []
    
    for ip, trials in data.get("ip_trials", {}).items():
        if len(trials) >= max_trials_per_ip:
            suspicious_ips.append((ip, trials))
    
    if suspicious_ips:
        print("🚨 Suspicious IPs (at or above limit):")
        for ip, trials in suspicious_ips:
            emails = [t.get("email", "unknown") for t in trials]
            print(f"  {ip}: {len(trials)} trials - {', '.join(emails)}")
    else:
        print("✅ No suspicious IPs detected")
    
    print()

def list_all():
    """List all tracked data."""
    data = load_trial_data()
    
    print("=== All Tracked IPs ===")
    for ip, trials in data.get("ip_trials", {}).items():
        print(f"{ip}:")
        for trial in trials:
            timestamp = trial.get("timestamp", 0)
            dt = datetime.fromtimestamp(timestamp) if timestamp else "unknown"
            print(f"  - {trial.get('email', 'unknown')} at {dt}")
    
    print("\n=== All Tracked Emails ===")
    for email, ips in data.get("email_ips", {}).items():
        print(f"{email}: {', '.join(ips)}")

def clean_old_data(days=30):
    """Clean up old trial data."""
    data = load_trial_data()
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    
    cleaned_ips = 0
    cleaned_fingerprints = 0
    
    # Clean IP trials
    for ip in list(data.get("ip_trials", {}).keys()):
        trials = data["ip_trials"][ip]
        recent_trials = [t for t in trials if t.get("timestamp", 0) > cutoff_time]
        
        if recent_trials:
            data["ip_trials"][ip] = recent_trials
        else:
            del data["ip_trials"][ip]
            cleaned_ips += 1
    
    # Clean fingerprint trials
    for fp in list(data.get("fingerprint_trials", {}).keys()):
        trials = data["fingerprint_trials"][fp]
        recent_trials = [t for t in trials if t.get("timestamp", 0) > cutoff_time]
        
        if recent_trials:
            data["fingerprint_trials"][fp] = recent_trials
        else:
            del data["fingerprint_trials"][fp]
            cleaned_fingerprints += 1
    
    save_trial_data(data)
    
    print(f"🧹 Cleaned up data older than {days} days")
    print(f"  - Removed {cleaned_ips} old IP records")
    print(f"  - Removed {cleaned_fingerprints} old fingerprint records")

def reset_ip(ip):
    """Reset trial data for a specific IP."""
    data = load_trial_data()
    
    if ip in data.get("ip_trials", {}):
        trials = data["ip_trials"][ip]
        emails = [t.get("email", "unknown") for t in trials]
        del data["ip_trials"][ip]
        
        # Also clean up email mappings
        for email in emails:
            if email in data.get("email_ips", {}):
                if ip in data["email_ips"][email]:
                    data["email_ips"][email].remove(ip)
                if not data["email_ips"][email]:
                    del data["email_ips"][email]
        
        save_trial_data(data)
        print(f"✅ Reset trial data for IP {ip} ({len(trials)} trials removed)")
    else:
        print(f"❌ No trial data found for IP {ip}")

def check_ip(ip):
    """Check if an IP would be blocked."""
    data = load_trial_data()
    max_trials_per_ip = 2
    cooldown_days = 30
    
    ip_trials = data.get("ip_trials", {}).get(ip, [])
    cutoff_time = time.time() - (cooldown_days * 24 * 60 * 60)
    
    recent_trials = [t for t in ip_trials if t.get("timestamp", 0) > cutoff_time]
    
    print(f"=== Check Results for IP {ip} ===")
    print(f"Total trials: {len(ip_trials)}")
    print(f"Recent trials (within {cooldown_days} days): {len(recent_trials)}")
    print(f"Limit: {max_trials_per_ip}")
    
    if len(recent_trials) >= max_trials_per_ip:
        print("❌ WOULD BE BLOCKED - Trial limit reached")
    else:
        remaining = max_trials_per_ip - len(recent_trials)
        print(f"✅ WOULD BE ALLOWED - {remaining} trials remaining")
    
    if recent_trials:
        print("Recent trials:")
        for trial in recent_trials:
            timestamp = trial.get("timestamp", 0)
            dt = datetime.fromtimestamp(timestamp)
            print(f"  - {trial.get('email', 'unknown')} at {dt}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    
    command = sys.argv[1]
    
    try:
        if command == "stats":
            show_stats()
        
        elif command == "list":
            list_all()
        
        elif command == "clean":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            clean_old_data(days)
        
        elif command == "reset":
            if len(sys.argv) < 3:
                print("Usage: trial_protection_admin.py reset <ip_address>")
                return 1
            reset_ip(sys.argv[2])
        
        elif command == "check":
            if len(sys.argv) < 3:
                print("Usage: trial_protection_admin.py check <ip_address>")
                return 1
            check_ip(sys.argv[2])
        
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())