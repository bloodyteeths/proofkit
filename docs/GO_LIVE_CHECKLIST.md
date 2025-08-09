# Go-Live Checklist v0.6-validated

## Pre-Deploy Gates (ALL must be green)

- [ ] CI green on main branch
- [ ] Campaign accuracy ≥95% (`python -m cli.validate_campaign --report`)
- [ ] No DIFF > tolerance violations
- [ ] Coverage ≥92% for core modules
- [ ] Golden Pack builds successfully (`python -m scripts.make_golden_pack`)
- [ ] `/debug/compile` is auth-gated

## Deployment Steps

### 1. Tag & Changelog
```bash
git tag v0.6-validated
git push --tags
```

### 2. Set Production Secrets (Fly.io)
```bash
# Core settings
fly secrets set BASE_URL=https://proofkit.net

# Email (Postmark)
fly secrets set POSTMARK_TOKEN=<your-token>
fly secrets set FROM_EMAIL=no-reply@proofkit.net
fly secrets set REPLY_TO_EMAIL=support@proofkit.net
fly secrets set SUPPORT_INBOX=support@proofkit.net

# Payments (Stripe)
fly secrets set STRIPE_SECRET_KEY=<your-key>
fly secrets set STRIPE_WEBHOOK_SECRET=<your-secret>
fly secrets set STRIPE_PRICE_SINGLE_CERT=<price-id>
fly secrets set STRIPE_PRICE_STARTER=<price-id>

# AWS (if using)
fly secrets set AWS_ACCESS_KEY_ID=<your-key>
fly secrets set AWS_SECRET_ACCESS_KEY=<your-secret>
fly secrets set AWS_DEFAULT_REGION=eu-central-1
fly secrets set S3_BUCKET=proofkit-prod
fly secrets set DDB_TABLE=proofkit-jobs
```

### 3. Deploy Canary
```bash
# Scale down to single instance
fly scale count 1

# Deploy
fly deploy

# Check deployment
fly status
```

### 4. Configure Domain
```bash
# Create certificate
fly certs create proofkit.net

# Verify DNS
fly certs show proofkit.net

# Add www redirect
fly certs create www.proofkit.net
```

### 5. Smoke Tests
```bash
# Run automated smoke tests
python scripts/post_deploy_smoke.py https://proofkit.net

# Manual checks:
# - [ ] /health returns 200
# - [ ] Upload 1 dataset per industry
# - [ ] PDF generates correctly
# - [ ] QR verify page loads
# - [ ] Stripe test purchase works
# - [ ] Receipt email arrives (Postmark)
```

### 6. Scale Production
```bash
# Scale to 2 instances
fly scale count 2

# Increase memory if needed
fly scale memory 512

# Verify
fly status
```

## Post-Deploy Monitoring (24-48h)

### Metrics to Watch
- [ ] Error rate <0.5%
- [ ] p95 compile time <3s
- [ ] Campaign nightly job succeeds
- [ ] Backup cron runs successfully
- [ ] No memory leaks (steady state)

### Logs to Check
```bash
# Stream logs
fly logs

# Check for errors
fly logs | grep ERROR

# Monitor campaign runs
fly logs | grep campaign
```

### Manual Validation
1. Download Golden Pack from /campaign
2. Pick 2 random datasets
3. Run through public UI
4. Compare decision.json with pack
5. Must match exactly

## Rollback Plan

If critical issues:
```bash
# Immediate rollback
fly deploy -i <previous-image-id>

# Or redeploy previous tag
git checkout v0.5-stable
fly deploy
```

## Optional Enhancements

### Soft Launch (48h gate)
- Add invite-only CTA on homepage
- Monitor early user feedback
- Gradual rollout

### Security Hardening
- [ ] Add /security.txt
- [ ] Update robots.txt
- [ ] Enable rate limiting
- [ ] Add CSP headers

### Legal/Trust
- [ ] Publish privacy policy
- [ ] Add /trust page
- [ ] GDPR compliance check

## Sign-off

- [ ] All gates green
- [ ] Canary stable for 30min
- [ ] Smoke tests pass
- [ ] Team notified
- [ ] Monitoring dashboard ready

**Deploy authorized by**: _______________  
**Date/Time**: _______________  
**Version**: v0.6-validated