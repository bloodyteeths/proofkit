# Trial Protection System

The trial protection system prevents users from abusing the free trial by creating multiple accounts using different email addresses from the same IP address or device.

## How It Works

### IP-Based Tracking
- Tracks trial signups by IP address
- Uses persistent storage in `storage/trial_tracking/`
- Limits based on configurable thresholds
- Includes cooldown periods to prevent long-term blocking

### Device Fingerprinting
- Creates unique device fingerprints based on browser characteristics
- Uses User-Agent, Accept headers, language preferences, etc.
- Secondary defense against sophisticated abuse attempts

### Temporary Email Detection
- Blocks known temporary/disposable email domains
- Prevents users from using throwaway emails for trials

## Configuration

Set these environment variables in your `.env` file:

```bash
# Maximum trial accounts per IP address
MAX_TRIALS_PER_IP=2

# Maximum trial accounts per device fingerprint  
MAX_TRIALS_PER_FINGERPRINT=3

# Days before IP can create another trial account
TRIAL_COOLDOWN_DAYS=30
```

## IP Address Extraction

The system correctly handles Fly.io proxy headers:

1. **Fly-Client-IP** - Primary header used by Fly.io (most reliable)
2. **X-Forwarded-For** - Used when there are multiple proxies
3. **X-Real-IP** - Fallback for other reverse proxy setups
4. **Direct client IP** - Final fallback

## Storage

- Trial data is stored in `storage/trial_tracking/trial_data.json`
- Uses persistent storage (not `/tmp`) so data survives deployments
- Includes timestamps for all tracking data
- Automatically creates directory structure if needed

## Integration Points

The trial protection is integrated into these endpoints:

### `/auth/signup` (POST)
- Checks for abuse BEFORE creating magic link
- Records trial signup AFTER validation passes
- Shows user-friendly error messages for blocked attempts

### `/auth/request-link` (POST)  
- Only checks abuse for operator role ("op") - trial users
- QA role ("qa") bypasses trial protection
- Records trial signup for tracking

## Admin Tools

Use the admin script to manage trial protection:

```bash
# Show statistics
python3 scripts/trial_protection_admin.py stats

# List all tracked IPs and emails
python3 scripts/trial_protection_admin.py list

# Check if an IP would be blocked
python3 scripts/trial_protection_admin.py check 203.0.113.1

# Reset trial data for specific IP
python3 scripts/trial_protection_admin.py reset 203.0.113.1

# Clean up data older than 30 days
python3 scripts/trial_protection_admin.py clean 30
```

## Logging

The system logs important events:

- **INFO**: Trial signup attempts with IP and fingerprint
- **WARNING**: Blocked abuse attempts with reasons
- **DEBUG**: Detailed IP extraction and header information

## Error Messages

Users see helpful error messages when blocked:

- "Maximum trial accounts reached from this network. Please upgrade existing account."
- "Maximum trial accounts reached from this device. Please upgrade existing account."  
- "Temporary email addresses are not allowed for trials. Please use a permanent email."
- "Please wait before creating another account." (for rapid successive attempts)

## Security Considerations

### Header Spoofing Protection
- Prioritizes Fly.io's trusted headers over standard forwarded headers
- Logs all relevant headers for debugging
- Falls back gracefully through multiple header sources

### Data Privacy
- Only stores hashed device fingerprints (16 characters)
- Includes minimal necessary data for tracking
- Automatic cleanup of old data

### Performance
- Lightweight JSON file storage suitable for moderate traffic
- Efficient in-memory processing
- For high-traffic deployments, consider Redis backend

## Monitoring

Monitor trial protection effectiveness:

```bash
# Check current statistics
python3 scripts/trial_protection_admin.py stats

# Look for patterns in logs
grep "Trial abuse" logs/application.log

# Monitor storage size
ls -la storage/trial_tracking/
```

## Troubleshooting

### IP Extraction Issues
1. Enable DEBUG logging to see extracted IPs
2. Check relevant headers in request logs
3. Verify Fly.io configuration

### False Positives
1. Check if legitimate users share IPs (office networks, etc.)
2. Consider adjusting `MAX_TRIALS_PER_IP` limit
3. Use admin tools to reset specific IPs if needed

### Storage Issues  
1. Verify `storage/trial_tracking/` directory exists and is writable
2. Check for disk space issues
3. Monitor file permissions

## Future Enhancements

Possible improvements for high-scale deployments:

- Redis backend for better performance
- Machine learning-based abuse detection
- Integration with external fraud prevention services
- More sophisticated device fingerprinting
- Rate limiting integration