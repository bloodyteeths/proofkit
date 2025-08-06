# Email Setup for ProofKit Magic Links

## Overview
ProofKit uses magic-link authentication requiring reliable email delivery. This guide covers setup for both AWS SES and Postmark email services.

## Option 1: AWS SES (Recommended for High Volume)

### Prerequisites
- AWS Account with SES access
- Domain verified in SES
- Production access requested (exit sandbox mode)

### 1. SES Domain Verification

#### Verify Your Domain
```bash
# Using AWS CLI
aws ses verify-domain-identity --domain proofkit.com
```

#### Add DNS Records (see DNS_SETUP.md for more records)
```
# Domain verification TXT record
Type: TXT
Name: _amazonses.proofkit.com
Value: [Verification token from SES console]
TTL: 300
```

### 2. DKIM Setup
```bash
# Generate DKIM tokens
aws ses put-identity-dkim-attributes --identity proofkit.com --dkim-enabled
```

Add these 3 CNAME records:
```
Type: CNAME
Name: [token1]._domainkey.proofkit.com
Value: [token1].dkim.amazonses.com
TTL: 300

Type: CNAME  
Name: [token2]._domainkey.proofkit.com
Value: [token2].dkim.amazonses.com
TTL: 300

Type: CNAME
Name: [token3]._domainkey.proofkit.com  
Value: [token3].dkim.amazonses.com
TTL: 300
```

### 3. SES Configuration

#### Create SMTP Credentials
1. Go to SES Console → SMTP Settings
2. Create SMTP Credentials
3. Note down username/password

#### Environment Variables
```bash
# Add to Fly.io secrets
fly secrets set EMAIL_BACKEND=ses
fly secrets set SES_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
fly secrets set SES_SMTP_PORT=587
fly secrets set SES_SMTP_USERNAME=[your-smtp-username]
fly secrets set SES_SMTP_PASSWORD=[your-smtp-password]
fly secrets set EMAIL_FROM="ProofKit <noreply@proofkit.com>"
```

### 4. Request Production Access
For new AWS accounts, SES starts in sandbox mode:
1. Go to SES Console → Sending Statistics
2. Click "Request a sending quota increase"
3. Provide use case: "Industrial temperature validation platform sending authentication magic links"

## Option 2: Postmark (Recommended for Simplicity)

### Prerequisites
- Postmark account
- Domain verified
- Sender signature configured

### 1. Domain Setup
1. Add domain in Postmark dashboard
2. Verify ownership with TXT record
3. Configure DKIM (Postmark provides records)

### 2. Environment Variables
```bash
# Add to Fly.io secrets
fly secrets set EMAIL_BACKEND=postmark
fly secrets set POSTMARK_API_TOKEN=[your-server-token]
fly secrets set EMAIL_FROM="ProofKit <noreply@proofkit.com>"
```

### 3. DKIM Records (Postmark provides)
```
Type: TXT
Name: [provided-by-postmark]
Value: [provided-by-postmark]
TTL: 300
```

## DNS Records for Email Authentication

### SPF Record
```
Type: TXT
Name: @
Value: v=spf1 include:amazonses.com ~all
TTL: 300

# For Postmark, use:
# v=spf1 include:spf.mtasv.net ~all
```

### DMARC Record
```
Type: TXT
Name: _dmarc
Value: v=DMARC1; p=none; rua=mailto:dmarc@proofkit.com; ruf=mailto:forensic@proofkit.com; fo=1
TTL: 300
```

### DKIM Records
See provider-specific sections above for DKIM CNAME records.

## Application Configuration

### Email Templates

Create `/web/templates/emails/` directory with:
- `magic_link.html` - HTML version
- `magic_link.txt` - Plain text version

### Environment Variables Required
```bash
EMAIL_BACKEND=ses|postmark
EMAIL_FROM=ProofKit <noreply@proofkit.com>
MAGIC_LINK_EXPIRE_MINUTES=15
BASE_URL=https://proofkit.com

# SES specific
SES_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SES_SMTP_PORT=587
SES_SMTP_USERNAME=
SES_SMTP_PASSWORD=

# Postmark specific  
POSTMARK_API_TOKEN=
```

## Testing Email Delivery

Use the test script to verify email setup:

```bash
# Test magic link email
python scripts/check_email.py --email your@email.com --test
```

## Monitoring & Analytics

### SES Monitoring
- Bounce rate < 5%
- Complaint rate < 0.1% 
- Monitor reputation dashboard

### Postmark Monitoring
- Delivery rate > 99%
- Monitor message streams
- Track opens/clicks if enabled

### Key Metrics to Track
- Magic link delivery time
- Email bounce rates
- Authentication success rates
- User conversion from email to login

## Troubleshooting

### Common Issues

**High Bounce Rate**
- Verify recipient addresses exist
- Check email formatting
- Review sender reputation

**Emails in Spam**
- Verify SPF, DKIM, DMARC records
- Check sender reputation
- Avoid spam trigger words
- Use dedicated IP (SES)

**Delivery Delays**
- Check service status pages
- Monitor sending quotas
- Review rate limiting

### Debugging Commands
```bash
# Check DNS records
dig TXT proofkit.com
dig TXT _dmarc.proofkit.com
nslookup -type=TXT _amazonses.proofkit.com

# Test SMTP connection (SES)
telnet email-smtp.us-east-1.amazonaws.com 587

# Verify DKIM
dig TXT [dkim-token]._domainkey.proofkit.com
```

## Security Best Practices

1. **Rate Limiting**: Limit magic link requests (5 per hour per email)
2. **Link Expiration**: Set short expiration (15 minutes)
3. **One-Time Use**: Invalidate links after successful auth
4. **Secure Storage**: Don't log magic link tokens
5. **HTTPS Only**: Always use HTTPS for magic link URLs

## Production Checklist

- [ ] Email service configured (SES or Postmark)
- [ ] Domain verified with email provider
- [ ] SPF record added: `dig TXT proofkit.com`
- [ ] DKIM records added and verified
- [ ] DMARC record configured
- [ ] Environment variables set in Fly.io
- [ ] Test email sent successfully
- [ ] Magic link authentication tested
- [ ] Bounce/complaint monitoring configured
- [ ] Production sending limits adequate

## Cost Estimation

### AWS SES
- First 62,000 emails/month: Free
- Additional emails: $0.10 per 1,000
- Dedicated IP: $24.95/month (optional)

### Postmark
- Developer plan: 100 emails/month free
- Starter: $15/month for 10,000 emails
- Growth: $85/month for 100,000 emails

Choose based on expected authentication volume and budget requirements.