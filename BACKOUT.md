# Emergency Backout Procedures

## Immediate Rollback (< 2 minutes)

### 1. Re-enable Safe Mode (CRITICAL PATH)
```bash
fly -a proofkit-prod secrets set \
  SAFE_MODE=1 \
  HUMAN_QA_REQUIRED_FOR_PASS=1 \
  FAIL_ON_PARSER_WARNINGS=1 \
  BLOCK_IF_NO_TSA=1
```

### 2. Deploy Previous Version
```bash
# Get last known good deployment ID
fly releases -a proofkit-prod

# Rollback to specific version
fly deploy --image registry.fly.io/proofkit-prod:[PREVIOUS_VERSION]
```

## Partial Rollback Options

### Option A: Keep New Code, Enable Safety Only
```bash
fly -a proofkit-prod secrets set SAFE_MODE=1
# This re-enables orange banner and QA requirements
```

### Option B: Disable v2 API, Keep v1 Only
```bash
fly -a proofkit-prod secrets set \
  API_V2_ENABLED=0 \
  ALLOW_ONLY_V2_SPECS=0
```

### Option C: Block Specific Industries
```bash
# Add to app.py temporarily:
BLOCKED_INDUSTRIES = ['sterile', 'autoclave']  # As needed
```

## Monitoring During Rollback

```bash
# Watch logs
fly logs -a proofkit-prod

# Check health
curl https://proofkit.net/health

# Verify Safe Mode re-enabled
curl https://proofkit.net | grep "Safety Mode ON"
```

## Post-Rollback Actions

1. **Notify team** via Slack/email
2. **Document issue** in incident log
3. **Review failed examples** in /tmp/proofkit_errors/
4. **Check Sentry/logs** for root cause
5. **Create hotfix PR** if needed

## Recovery Timeline

- T+0: Issue detected
- T+30s: Safe Mode re-enabled
- T+2m: Previous version deployed (if needed)
- T+5m: Verification complete
- T+10m: Incident report started