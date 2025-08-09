# ProofKit Operations Checklist

## 24/7 Emergency Contacts

### Primary On-Call
- **Email:** support@proofkit.net
- **Response Time:** < 1 hour for critical issues

### Escalation Path
1. Check Better Uptime status: https://proofkit.betteruptime.com
2. Review Fly.io status: https://status.fly.io
3. Contact Fly support if infrastructure issue

## Monitoring & Health Checks

### Real-time Monitoring
```bash
# Check service health
curl https://proofkit-prod.fly.dev/health

# View application logs
fly logs -a proofkit-prod --tail

# Check metrics status
python scripts/emit_metrics.py --status
```

### Key Metrics to Monitor
- **P95 Compile Time:** Alert if >5s for 10min
- **5xx Error Rate:** Alert if >1% for 5min  
- **Bundle Verify Errors:** Alert if >0.5% for 10min
- **Memory Usage:** Alert if >400MB for 5min

## Common Operations

### Verify Bundle Integrity
```bash
# Download any evidence bundle and verify
python scripts/verify_bundle.py /path/to/evidence.zip
```

### Check Recent Deployments
```bash
# List recent releases
fly releases -a proofkit-prod

# View deployment details
fly status -a proofkit-prod
```

### Scale Resources
```bash
# Scale up for high load
fly scale count 3 -a proofkit-prod

# Scale back down
fly scale count 2 -a proofkit-prod
```

### Database Operations
```bash
# Connection string in DATABASE_URL
# RDS PostgreSQL in eu-central-1
# Automated backups enabled
```

## Emergency Procedures

### 1. Service Down
```bash
# Check health endpoint
curl -I https://proofkit-prod.fly.dev/health

# Restart machines if needed
fly machine restart -a proofkit-prod

# Check for deployment issues
fly status -a proofkit-prod --watch
```

### 2. High Error Rate
```bash
# Check recent errors
fly logs -a proofkit-prod | grep ERROR | tail -50

# Review specific industry
fly logs -a proofkit-prod | grep "industry=powder" | tail -20

# Check bundle verification
python scripts/verify_bundle.py [recent_bundle.zip]
```

### 3. Performance Degradation
```bash
# Check compile times
python scripts/emit_metrics.py --status

# Review memory usage
fly status -a proofkit-prod

# Scale if needed
fly scale memory 512 -a proofkit-prod
```

### 4. Rollback Procedure
```bash
# Get previous version
fly releases -a proofkit-prod

# Deploy specific version
fly deploy --image registry.fly.io/proofkit-prod:[VERSION]

# Verify rollback
curl https://proofkit-prod.fly.dev/health
```

## Scheduled Maintenance

### Weekly Tasks
- Review INDETERMINATE cases
- Check disk usage: `fly ssh console -a proofkit-prod -C "df -h"`
- Verify backup integrity

### Monthly Tasks
- Audit PASS approvals
- Review billing and quotas
- Update monitoring thresholds
- Security patch review

### Quarterly Tasks
- Update acceptance criteria
- Full validation campaign run
- Performance baseline review
- Disaster recovery test

## Integration Points

### External Services
- **Stripe:** Billing and payments
- **Postmark:** Transactional email
- **AWS S3:** Evidence backup storage
- **Better Uptime:** Status page monitoring
- **Google Analytics:** Usage tracking

### API Endpoints
- Health: `GET /health`
- Compile: `POST /api/compile/json`
- Verify: `GET /verify/{job_id}`
- Examples: `GET /examples`
- Trust: `GET /trust`

## Security Procedures

### Incident Response
1. Isolate affected component
2. Review recent changes
3. Check for data integrity issues
4. Document in incident log
5. Post-mortem within 48 hours

### Access Control
- Fly.io dashboard requires 2FA
- AWS console requires MFA
- Stripe webhooks use signed payloads
- Database access via SSL only

## Backup & Recovery

### Data Locations
- **Primary:** Fly.io volumes in Frankfurt
- **Backup:** AWS S3 in eu-central-1
- **Database:** RDS with automated snapshots

### Recovery Procedures
```bash
# Restore from S3 backup
aws s3 sync s3://proofkit-backups-0e180e85/[date]/ ./restore/

# Verify bundle integrity
find ./restore -name "*.zip" -exec python scripts/verify_bundle.py {} \;
```

## Contact Information

### Service Providers
- **Fly.io Support:** https://fly.io/docs/about/support/
- **Stripe Support:** https://support.stripe.com/
- **Postmark Support:** https://postmarkapp.com/support
- **AWS Support:** AWS Console → Support Center

### Internal Resources
- GitHub Issues: https://github.com/proofkit/proofkit
- Documentation: https://proofkit.net/docs
- Status Page: https://proofkit.betteruptime.com

---

*Last Updated: 2025-08-09*  
*Version: 0.6.0*  
*Next Review: 2025-09-09*