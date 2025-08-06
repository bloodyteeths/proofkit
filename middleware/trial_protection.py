"""
Trial Abuse Protection Middleware

Prevents users from creating multiple trial accounts using different email addresses
by tracking IP addresses, device fingerprints, and behavioral patterns.

Example usage:
    from middleware.trial_protection import check_trial_abuse
    
    is_abuser, reason = check_trial_abuse(request, email)
    if is_abuser:
        return error_response(f"Trial limit reached: {reason}")
"""

import json
import hashlib
import time
import os
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import Request
import logging

logger = logging.getLogger(__name__)

# Storage for trial tracking using persistent storage directory
TRIAL_DATA_PATH = Path("storage/trial_tracking/trial_data.json")

# Configuration from environment variables (with defaults)
MAX_TRIALS_PER_IP = int(os.environ.get("MAX_TRIALS_PER_IP", "2"))
MAX_TRIALS_PER_FINGERPRINT = int(os.environ.get("MAX_TRIALS_PER_FINGERPRINT", "3"))
COOLDOWN_DAYS = int(os.environ.get("TRIAL_COOLDOWN_DAYS", "30"))


def load_trial_data() -> Dict[str, Any]:
    """Load trial tracking data from storage."""
    if TRIAL_DATA_PATH.exists():
        try:
            with open(TRIAL_DATA_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load trial data: {e}")
    
    return {
        "ip_trials": {},  # IP -> list of emails and timestamps
        "fingerprint_trials": {},  # Fingerprint -> list of emails and timestamps
        "email_ips": {},  # Email -> list of IPs used
        "suspicious_patterns": []  # List of suspicious behavior patterns
    }


def save_trial_data(data: Dict[str, Any]) -> None:
    """Save trial tracking data to storage."""
    try:
        TRIAL_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRIAL_DATA_PATH, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to save trial data: {e}")


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, handling Fly.io proxies and other common setups."""
    # Check for Fly.io's primary client IP header (most reliable on Fly.io)
    fly_client_ip = request.headers.get("Fly-Client-IP")
    if fly_client_ip:
        logger.debug(f"Using Fly-Client-IP: {fly_client_ip}")
        return fly_client_ip.strip()
    
    # Check for X-Forwarded-For (used when there are multiple proxies)
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        # Take the leftmost IP (original client) but be careful about spoofing
        client_ip = x_forwarded.split(",")[0].strip()
        logger.debug(f"Using X-Forwarded-For (first): {client_ip} from full header: {x_forwarded}")
        return client_ip
    
    # Check for X-Real-IP header
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        logger.debug(f"Using X-Real-IP: {x_real_ip}")
        return x_real_ip.strip()
    
    # Fallback to direct client IP
    direct_ip = request.client.host if request.client else "unknown"
    logger.debug(f"Using direct client IP: {direct_ip}")
    
    # Log all headers for debugging in development
    if logger.isEnabledFor(logging.DEBUG):
        relevant_headers = {
            "Fly-Client-IP": request.headers.get("Fly-Client-IP"),
            "X-Forwarded-For": request.headers.get("X-Forwarded-For"),
            "X-Real-IP": request.headers.get("X-Real-IP"),
            "CF-Connecting-IP": request.headers.get("CF-Connecting-IP"),  # Cloudflare
            "True-Client-IP": request.headers.get("True-Client-IP"),      # Cloudflare Enterprise
        }
        logger.debug(f"All IP-related headers: {relevant_headers}")
    
    return direct_ip


def generate_device_fingerprint(request: Request) -> str:
    """
    Generate a device fingerprint based on browser characteristics.
    
    In production, this should use client-side JavaScript to collect:
    - Screen resolution
    - Timezone
    - Installed plugins
    - Canvas fingerprint
    - WebGL fingerprint
    """
    components = []
    
    # User agent
    user_agent = request.headers.get("User-Agent", "")
    components.append(user_agent)
    
    # Accept headers (browser capabilities)
    accept = request.headers.get("Accept", "")
    components.append(accept)
    
    # Accept-Language (user's language preferences)
    accept_lang = request.headers.get("Accept-Language", "")
    components.append(accept_lang)
    
    # Accept-Encoding (compression support)
    accept_enc = request.headers.get("Accept-Encoding", "")
    components.append(accept_enc)
    
    # DNT (Do Not Track) preference
    dnt = request.headers.get("DNT", "")
    components.append(dnt)
    
    # Create hash of components
    fingerprint_str = "|".join(components)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]


def check_trial_abuse(request: Request, email: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a signup attempt is likely trial abuse.
    
    Args:
        request: FastAPI request object
        email: Email address attempting to sign up
        
    Returns:
        Tuple of (is_abuse, reason) where is_abuse is True if abuse detected
    """
    # Get client identifiers
    client_ip = get_client_ip(request)
    device_fingerprint = generate_device_fingerprint(request)
    
    # Log the identifiers for debugging
    logger.info(f"Checking trial abuse for {email} from IP: {client_ip}, fingerprint: {device_fingerprint[:8]}...")
    
    # Load tracking data
    data = load_trial_data()
    
    # Check IP-based limits
    ip_trials = data.get("ip_trials", {}).get(client_ip, [])
    recent_ip_trials = []
    cutoff_time = time.time() - (COOLDOWN_DAYS * 24 * 60 * 60)
    
    for trial in ip_trials:
        if trial.get("timestamp", 0) > cutoff_time:
            recent_ip_trials.append(trial)
    
    if len(recent_ip_trials) >= MAX_TRIALS_PER_IP:
        logger.warning(f"Trial abuse detected - IP limit reached: {client_ip} -> {email}")
        return True, f"Maximum trial accounts reached from this network. Please upgrade existing account."
    
    # Check device fingerprint limits
    fp_trials = data.get("fingerprint_trials", {}).get(device_fingerprint, [])
    if len(fp_trials) >= MAX_TRIALS_PER_FINGERPRINT:
        logger.warning(f"Trial abuse detected - Device limit reached: {device_fingerprint} -> {email}")
        return True, f"Maximum trial accounts reached from this device. Please upgrade existing account."
    
    # Check for suspicious patterns
    email_domain = email.split("@")[1].lower()
    
    # Common temporary email domains
    temp_domains = [
        "tempmail.com", "guerrillamail.com", "mailinator.com", 
        "10minutemail.com", "throwaway.email", "yopmail.com",
        "temp-mail.org", "fakeinbox.com", "trashmail.com"
    ]
    
    if email_domain in temp_domains:
        logger.warning(f"Trial abuse detected - Temporary email: {email}")
        return True, f"Temporary email addresses are not allowed for trials. Please use a permanent email."
    
    # Check for rapid successive signups from same IP
    if recent_ip_trials:
        last_signup = max(trial.get("timestamp", 0) for trial in recent_ip_trials)
        if time.time() - last_signup < 300:  # 5 minutes
            logger.warning(f"Trial abuse detected - Rapid signups: {client_ip} -> {email}")
            return True, f"Please wait before creating another account."
    
    # Check for email pattern abuse (numbered emails like user1@, user2@, etc.)
    email_prefix = email.split("@")[0]
    for trial in ip_trials:
        existing_email = trial.get("email", "")
        existing_prefix = existing_email.split("@")[0]
        
        # Check for sequential numbering
        if email_prefix[:-1] == existing_prefix[:-1] and \
           email_prefix[-1].isdigit() and existing_prefix[-1].isdigit():
            logger.warning(f"Trial abuse detected - Sequential emails: {email}")
            return True, f"Multiple trial accounts detected. Please use your existing account."
    
    return False, None


def record_trial_signup(request: Request, email: str) -> None:
    """
    Record a new trial signup for tracking.
    
    Args:
        request: FastAPI request object  
        email: Email address that signed up
    """
    client_ip = get_client_ip(request)
    device_fingerprint = generate_device_fingerprint(request)
    
    logger.info(f"Recording trial signup for {email} from IP: {client_ip}, fingerprint: {device_fingerprint[:8]}...")
    
    data = load_trial_data()
    
    # Record IP trial
    if client_ip not in data["ip_trials"]:
        data["ip_trials"][client_ip] = []
    
    data["ip_trials"][client_ip].append({
        "email": email,
        "timestamp": time.time(),
        "fingerprint": device_fingerprint
    })
    
    # Record device fingerprint trial
    if device_fingerprint not in data["fingerprint_trials"]:
        data["fingerprint_trials"][device_fingerprint] = []
    
    data["fingerprint_trials"][device_fingerprint].append({
        "email": email,
        "timestamp": time.time(),
        "ip": client_ip
    })
    
    # Record email -> IP mapping
    if email not in data["email_ips"]:
        data["email_ips"][email] = []
    
    if client_ip not in data["email_ips"][email]:
        data["email_ips"][email].append(client_ip)
    
    # Save updated data
    save_trial_data(data)
    
    logger.info(f"Recorded trial signup: {email} from {client_ip}")


def get_trial_statistics() -> Dict[str, Any]:
    """
    Get statistics about trial usage and potential abuse.
    
    Returns:
        Dictionary with trial statistics
    """
    data = load_trial_data()
    
    stats = {
        "total_ips": len(data.get("ip_trials", {})),
        "total_fingerprints": len(data.get("fingerprint_trials", {})),
        "total_emails": len(data.get("email_ips", {})),
        "suspicious_ips": [],
        "suspicious_fingerprints": []
    }
    
    # Find IPs with multiple trials
    for ip, trials in data.get("ip_trials", {}).items():
        if len(trials) >= MAX_TRIALS_PER_IP:
            stats["suspicious_ips"].append({
                "ip": ip,
                "trial_count": len(trials),
                "emails": [t["email"] for t in trials]
            })
    
    # Find fingerprints with multiple trials  
    for fp, trials in data.get("fingerprint_trials", {}).items():
        if len(trials) >= MAX_TRIALS_PER_FINGERPRINT:
            stats["suspicious_fingerprints"].append({
                "fingerprint": fp,
                "trial_count": len(trials),
                "emails": [t["email"] for t in trials]
            })
    
    return stats


def cleanup_old_trial_data(days: int = 90) -> None:
    """
    Remove trial tracking data older than specified days.
    
    Args:
        days: Number of days to keep data
    """
    data = load_trial_data()
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    
    # Clean IP trials
    for ip in list(data.get("ip_trials", {}).keys()):
        trials = data["ip_trials"][ip]
        recent_trials = [t for t in trials if t.get("timestamp", 0) > cutoff_time]
        
        if recent_trials:
            data["ip_trials"][ip] = recent_trials
        else:
            del data["ip_trials"][ip]
    
    # Clean fingerprint trials
    for fp in list(data.get("fingerprint_trials", {}).keys()):
        trials = data["fingerprint_trials"][fp]
        recent_trials = [t for t in trials if t.get("timestamp", 0) > cutoff_time]
        
        if recent_trials:
            data["fingerprint_trials"][fp] = recent_trials
        else:
            del data["fingerprint_trials"][fp]
    
    save_trial_data(data)
    logger.info(f"Cleaned up trial data older than {days} days")