# 🌐 ProofKit DNS & DMARC Configuration

## DNS Setup Status

### ✅ Current Configuration
- **Apex Domain**: Redirects to www (already live)
- **WWW Domain**: Points to Fly.io app `proofkit-prod.fly.dev`
- **Status**: DNS is production-ready

### 📧 DMARC Progressive Rollout Plan

**IMPORTANT**: DMARC should be implemented gradually to avoid email delivery issues.

#### Phase 1: Monday (August 11, 2025) - Monitoring
```dns
v=DMARC1; p=none; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc@proofkit.net; fo=1
```
**Impact**: Monitor only, no enforcement

#### Phase 2: Monday + 1 Week (August 18, 2025) - Quarantine  
```dns
v=DMARC1; p=quarantine; pct=10; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc@proofkit.net; fo=1
```
**Impact**: Quarantine 10% of failing emails

#### Phase 3: Monday + 2 Weeks (August 25, 2025) - Full Quarantine
```dns
v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc@proofkit.net; fo=1
```
**Impact**: Quarantine all failing emails

#### Phase 4: Monday + 4 Weeks (September 8, 2025) - Reject
```dns
v=DMARC1; p=reject; pct=100; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc@proofkit.net; fo=1
```
**Impact**: Reject all failing emails (full protection)

## Required DNS Records

### 1. SPF Record (Add if not present)
```dns
TXT @ "v=spf1 include:_spf.google.com include:spf.postmarkapp.com ~all"
```

### 2. DKIM Records  
**Note**: Get these from your email provider (Postmark/Google Workspace)

### 3. Current DMARC (Week 1)
```dns
TXT _dmarc "v=DMARC1; p=none; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc@proofkit.net; fo=1"
```

## Verification Commands

```bash
# Check DNS propagation
dig TXT _dmarc.proofkit.net
dig TXT proofkit.net
dig A proofkit.net

# Test email authentication
echo "test" | mail -s "DMARC Test" dmarc@proofkit.net
```

## Monitoring Setup

### DMARC Report Analysis
- Set up `dmarc@proofkit.net` mailbox
- Monitor daily DMARC reports
- Use tools like DMARC Analyzer or PostmarkApp's DMARC monitoring

### Key Metrics to Watch
- **Authentication Pass Rate**: Should be >95%
- **Policy Alignment**: SPF and DKIM aligned
- **Failure Sources**: Identify unauthorized senders

## Emergency Rollback

If email delivery issues occur:

```bash
# Immediate rollback to monitoring only
dig TXT _dmarc.proofkit.net 
# Change to: v=DMARC1; p=none; ...

# Or temporary disable
# Delete DMARC record entirely for 24h
```

## Implementation Checklist

### Week 1 (August 11, 2025)
- [ ] Set DMARC to `p=none` (monitoring only)
- [ ] Verify SPF and DKIM records are correct
- [ ] Set up `dmarc@proofkit.net` monitoring mailbox
- [ ] Send test emails to verify delivery

### Week 2 (August 18, 2025)  
- [ ] Review DMARC reports from week 1
- [ ] Fix any authentication issues found
- [ ] Set DMARC to `p=quarantine; pct=10`
- [ ] Monitor for delivery issues

### Week 3 (August 25, 2025)
- [ ] Increase to `p=quarantine; pct=100`
- [ ] Monitor email delivery metrics
- [ ] Address any remaining issues

### Week 4+ (September 8, 2025)
- [ ] Final step: `p=reject; pct=100`
- [ ] Full email authentication enforcement
- [ ] Ongoing monitoring and maintenance

## Support Contacts

**DNS Management**: Update with your DNS provider support  
**Email Provider**: Postmark support or Google Workspace admin  
**Emergency Contact**: [Update with technical lead]  

---
**Created**: August 6, 2025  
**Next Review**: August 11, 2025 (DMARC Phase 1)  