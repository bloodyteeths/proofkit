# Go/No-Go Launch Checklist

## Pre-Launch Verification ✓

### 1. Code Review
- [ ] All 6 PRs merged to main
- [ ] No merge conflicts
- [ ] CI/CD pipeline green

### 2. Local Testing
```bash
# Run acceptance tests
pytest tests/acceptance/ -v

# Run example compilation
python tests/examples/test_examples_compile.py

# Verify policy defaults
python -c "from core.policy import *; print(f'Safe Mode: {is_safe_mode()}')"
# Should print: Safe Mode: False
```

### 3. API Contract Tests
```bash
# Test v1 format
curl -X POST http://localhost:8080/api/compile/json \
  -F "csv_file=@examples/powder_pass_fixed.csv" \
  -F 'spec_json={"spec":{"test_criteria":{"parameters":{"target_temp":180}}}}'

# Test v2 format
curl -X POST http://localhost:8080/api/compile/json \
  -F "csv_file=@examples/powder_pass_fixed.csv" \
  -F 'spec_json={"industry":"powder","parameters":{"target_temp":180}}'
```

## Launch Execution ✓

### 4. Production Deployment
```bash
# Remove Safe Mode
fly -a proofkit-prod secrets unset SAFE_MODE HUMAN_QA_REQUIRED_FOR_PASS

# Deploy latest code
fly deploy --app proofkit-prod

# Wait for health check
fly status --app proofkit-prod
```

### 5. Live Verification (REQUIRED)
```bash
# Industry pages (all must return 200)
for page in powder-coating autoclave cold-chain haccp concrete sterile; do
  echo -n "$page: "
  curl -s -o /dev/null -w "%{http_code}\n" https://proofkit.net/industries/$page
done

# Examples compilation (12 total: 6 PASS + 6 FAIL)
python -m tests.smoke.test_live_smoke --base-url https://proofkit.net
```

### 6. Visual Checks
- [ ] Visit https://proofkit.net - NO orange banner
- [ ] Visit https://proofkit.net/examples - All examples listed
- [ ] Download one PDF - NO "PENDING QA" watermark

## Go/No-Go Decision

### GO Criteria (ALL must be true)
- ✅ All 6 industry pages return HTTP 200
- ✅ 12 examples compile successfully
- ✅ No Safe Mode banner visible
- ✅ PDFs generate without QA watermarks
- ✅ API accepts both v1 and v2 formats

### NO-GO Criteria (ANY triggers rollback)
- ❌ Any industry page returns 500/404
- ❌ Examples fail to compile
- ❌ Orange safety banner still visible
- ❌ PDFs show PENDING QA watermarks
- ❌ API rejects valid requests

## Post-Launch Monitoring (First 24 Hours)

### 7. Success Metrics
```bash
# Check error rate (should be < 1%)
fly logs -a proofkit-prod | grep ERROR | wc -l

# Monitor response times
curl -w "@curl-format.txt" -o /dev/null -s https://proofkit.net/health

# Verify bundle integrity
python scripts/verify_bundle.py [downloaded_bundle.zip]
```

### 8. Staging Cleanup
```bash
# After confirming production stability:
fly apps destroy proofkit-staging  # Manual confirmation required
```

---

## Quick Reference

**Expected Results:**
- 6 Industry pages: ALL return 200
- 12 Examples: 6 PASS, 6 FAIL
- API: Accepts v1 and v2
- PDFs: No watermarks
- UI: No orange banners

**Emergency Contact:**
- Rollback: See BACKOUT.md
- Issues: Create GitHub issue
- Monitoring: fly logs -a proofkit-prod

**Sign-off:**
- [ ] Engineering Lead
- [ ] QA Lead
- [ ] Product Owner

Date: ___________
Time: ___________