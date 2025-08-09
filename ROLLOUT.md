# Production Rollout Instructions

## Environment Flags to Set/Unset

### 1. Remove Safe Mode Restrictions (IMMEDIATE)
```bash
fly -a proofkit-prod secrets unset \
  SAFE_MODE \
  HUMAN_QA_REQUIRED_FOR_PASS \
  FAIL_ON_PARSER_WARNINGS \
  BLOCK_IF_NO_TSA
```

### 2. Enable API v2 as Default (KEEP EXISTING)
```bash
# These should already be set from previous deployment:
fly -a proofkit-prod secrets set \
  API_V2_ENABLED=1 \
  ACCEPT_LEGACY_SPEC=1 \
  EXAMPLES_V2_ENABLED=1
```

### 3. Optional Performance Flags
```bash
# Only if needed for performance tuning:
fly -a proofkit-prod secrets set \
  REQUIRE_DIFF_AGREEMENT=0 \
  ENFORCE_PDF_A3=1 \
  ALLOW_ONLY_V2_SPECS=0
```

## Deployment Sequence

1. **Unset Safe Mode flags** (removes all restrictions)
2. **Deploy latest code** with all PR changes merged
3. **Run live smoke tests** to verify all industries
4. **Monitor logs** for any issues

## Verification Commands

```bash
# Test all industry pages
for industry in powder-coating autoclave cold-chain haccp concrete sterile; do
  curl -s -o /dev/null -w "%{http_code}" https://proofkit.net/industries/$industry
done

# Run live smoke tests
python -m tests.smoke.test_live_smoke --base-url https://proofkit.net

# Verify API v2 is default
curl -X POST https://proofkit.net/api/compile/json \
  -F "csv_file=@test.csv" \
  -F 'spec_json={"industry":"powder","parameters":{"target_temp":180}}'
```

## Success Criteria

- ✅ All 6 industry pages return HTTP 200
- ✅ No orange safety banners visible
- ✅ PDFs generate without "PENDING QA" watermarks
- ✅ API accepts both v1 and v2 formats
- ✅ Examples compile to valid PDFs