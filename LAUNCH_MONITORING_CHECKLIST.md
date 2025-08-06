# 🚀 ProofKit Launch Day Monitoring Checklist

## First 24 Hours Critical Monitoring

### ✅ BetterUptime Dashboard
- [ ] Keep BetterUptime open in browser tab
- [ ] Monitor for any environment variable errors
- [ ] Watch for 5xx responses or timeouts
- [ ] Check all probe status (Health, API, Performance)

### ✅ S3 Backup Monitoring
- [ ] Watch S3 bucket size after tonight's backup at 2 AM UTC
- [ ] Confirm backup creates `backup-YYYYMMDD-HHMMSS.tar.gz` files
- [ ] Verify retention lifecycle rule removes old backups after 14 days
- [ ] Check backup integrity with SHA-256 verification

### ✅ Grafana Alerts
- [ ] Monitor alert history for false positives
- [ ] Tune thresholds if needed:
   - High error rate: currently 5%+ for 2+ minutes
   - Response time: 95th percentile > 5 seconds for 3+ minutes
   - Memory usage: > 400MB for 5+ minutes

### ✅ Application Health Checks
- [ ] `/health` endpoint responding with 200 status
- [ ] API endpoints `/api/presets` functioning
- [ ] Static assets loading correctly
- [ ] Security headers present (HSTS, CSP, X-Frame-Options)

### ✅ Error Monitoring
- [ ] Watch for unusual error patterns
- [ ] Monitor rate limiting triggers
- [ ] Check file upload error rates
- [ ] Verify cleanup process runs successfully

### ✅ Performance Baselines
- [ ] Response times under 2 seconds for /health
- [ ] API compile times under 10 seconds
- [ ] Memory usage stable under 400MB
- [ ] CPU usage appropriate for traffic load

## Hour-by-Hour Checkpoints

### Hours 0-2 (Launch)
- [ ] All systems green in BetterUptime
- [ ] First API calls successful
- [ ] No critical alerts triggered

### Hours 2-6 (First Backup)
- [ ] 2 AM UTC backup completes successfully
- [ ] Cleanup process removes old artifacts
- [ ] No storage space alerts

### Hours 6-12 (Early Traffic)
- [ ] Response times remain stable
- [ ] Error rates below 1%
- [ ] Memory usage stable

### Hours 12-24 (Full Cycle)
- [ ] All scheduled processes completed
- [ ] No degradation in performance
- [ ] Backup retention working correctly

## Emergency Contacts

**Technical Lead**: [Update with actual contact]
**DevOps Team**: [Update with actual contact]  
**Security Team**: [Update with actual contact]

## Critical Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Response Time (95th) | >3s | >5s |
| Error Rate | >2% | >5% |
| Memory Usage | >350MB | >400MB |
| Disk Usage | >80% | >90% |
| Backup Success | <100% | Failed |

## Quick Commands

```bash
# Check Fly.io logs
fly logs --app proofkit-prod

# Check specific processes
fly logs -i backup
fly logs -i cleanup

# Scale if needed
fly scale count 2 --app proofkit-prod

# Restart if issues
fly restart --app proofkit-prod
```

## Success Criteria

✅ **Green Status**: All monitors green for 24+ hours  
✅ **Backup Success**: First backup completes successfully  
✅ **Performance**: Response times <2s average  
✅ **Zero Incidents**: No P0/P1 incidents triggered  
✅ **Cleanup Success**: Retention policy working correctly  

---
**Launch Date**: August 6, 2025  
**Monitoring Lead**: [Update with actual name]  
**Review Date**: August 7, 2025  