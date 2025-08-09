# DMARC Implementation Ramp Plan

## Current Status
- **DMARC Policy**: `p=none` (monitoring mode)
- **Current TXT Record**: Confirmed active at DNS level
- **SPF**: Already configured and aligned
- **DKIM**: Already configured and aligned

## DMARC Ramp Schedule

### Week 1: Baseline Monitoring (Current State)
**Status**: ✅ **ACTIVE**
```
v=DMARC1; p=none; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc-failures@proofkit.net; sp=none; pct=100
```

**Actions**:
- [x] Monitor daily reports for authentication alignment
- [x] Identify any failing senders
- [x] Establish baseline pass rate (target: >95%)

### Week 2: Gradual Quarantine (Starts: 2025-08-16)
**Status**: 📅 **SCHEDULED**
```
v=DMARC1; p=quarantine; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc-failures@proofkit.net; sp=quarantine; pct=50
```

**Actions**:
- [ ] Update DNS TXT record to `p=quarantine` with `pct=50`
- [ ] Monitor for increased bounce rates or delivery issues
- [ ] Verify legitimate emails still deliver normally
- [ ] Check recipient spam folder placement for quarantined emails

**Rollback Plan**: If delivery issues > 5%, revert to `p=none` immediately

### Week 3: Full Quarantine (Starts: 2025-08-23)
**Status**: 📅 **SCHEDULED**
```
v=DMARC1; p=quarantine; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc-failures@proofkit.net; sp=quarantine; pct=100
```

**Actions**:
- [ ] Update `pct=100` for full quarantine
- [ ] Monitor aggregate reports for any authentication failures
- [ ] Verify email deliverability remains stable
- [ ] Document any edge cases requiring SPF/DKIM updates

### Week 4: Final Enforcement (Starts: 2025-08-30)
**Status**: 📅 **SCHEDULED**
```
v=DMARC1; p=reject; rua=mailto:dmarc@proofkit.net; ruf=mailto:dmarc-failures@proofkit.net; sp=reject; pct=100
```

**Actions**:
- [ ] Update to `p=reject` for maximum protection
- [ ] Monitor bounce rates closely for first 48 hours
- [ ] Establish final monitoring cadence (weekly reviews)
- [ ] Update security documentation with final configuration

## Monitoring & Alerts

### Daily Monitoring (Weeks 1-4)
- Review DMARC aggregate reports via `dmarc@proofkit.net`
- Check failure reports at `dmarc-failures@proofkit.net`
- Monitor email delivery success rates
- Track any customer complaints about missing emails

### Key Metrics
- **Authentication Pass Rate**: Target >98%
- **Policy Alignment**: Both SPF and DKIM should align
- **Volume Changes**: No significant drops in legitimate email delivery

### Alert Conditions
- Authentication failures >2% of total volume
- Customer reports of missing emails
- Bounce rate increases >10% from baseline

## Emergency Rollback Procedure

If any issues occur during ramp:
1. **Immediate**: Change DNS TXT record back to `p=none`
2. **Within 30 min**: Verify DNS propagation globally
3. **Within 2 hours**: Confirm normal email delivery resumed
4. **Within 24 hours**: Analyze root cause and plan fixes

## DNS Management

### Current DNS Provider
- **Provider**: Cloudflare DNS
- **TTL**: 300 seconds (5 minutes)
- **Record Name**: `_dmarc.proofkit.net`

### Verification Commands
```bash
# Check current DMARC policy
dig TXT _dmarc.proofkit.net

# Verify SPF record
dig TXT proofkit.net | grep spf

# Verify DKIM selector
dig TXT default._domainkey.proofkit.net
```

## Automated GitHub Issue Creation

This document serves as a reminder to create the following GitHub issues:

### Issue 1: DMARC Week 2 Ramp
```markdown
**Title**: DMARC Ramp to Quarantine 50% (Week 2)
**Due Date**: 2025-08-16
**Labels**: security, email, dmarc

**Description**:
Update DMARC policy to quarantine mode at 50% according to EMAIL_DMARCRAMP.md schedule.

**Tasks**:
- [ ] Update DNS TXT record to `p=quarantine; pct=50`
- [ ] Monitor delivery rates for 7 days
- [ ] Document any issues in EMAIL_DMARCRAMP.md
- [ ] Create Week 3 issue if no problems
```

### Issue 2: DMARC Week 3 Full Quarantine
```markdown
**Title**: DMARC Full Quarantine (Week 3)
**Due Date**: 2025-08-23
**Labels**: security, email, dmarc

**Description**:
Move to 100% quarantine policy according to EMAIL_DMARCRAMP.md schedule.

**Tasks**:
- [ ] Update DNS to `pct=100`
- [ ] Monitor for authentication failures
- [ ] Verify legitimate email delivery
- [ ] Create Week 4 reject policy issue
```

### Issue 3: DMARC Final Reject Policy
```markdown
**Title**: DMARC Final Reject Policy (Week 4)
**Due Date**: 2025-08-30
**Labels**: security, email, dmarc

**Description**:
Implement final reject policy for maximum email security.

**Tasks**:
- [ ] Update DNS to `p=reject`
- [ ] Monitor closely for 48 hours
- [ ] Document final configuration
- [ ] Update security documentation
```

## Contact Information

**DMARC Manager**: DevOps Team  
**DNS Manager**: Infrastructure Team  
**Escalation**: CTO for policy rollbacks  
**Email Reports**: `dmarc@proofkit.net` and `dmarc-failures@proofkit.net`

## Reference Links

- [DMARC Specification (RFC 7489)](https://tools.ietf.org/rfc/rfc7489.txt)
- [DMARC Policy Discovery](https://dmarcian.com/dmarc-inspector/)
- [Cloudflare DMARC Documentation](https://developers.cloudflare.com/email-security/dmarc/)

---
**Document Version**: 1.0  
**Last Updated**: 2025-08-09  
**Next Review**: 2025-08-16 (Week 2 ramp start)