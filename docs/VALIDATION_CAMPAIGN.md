# ProofKit Validation Campaign - Safety Mode Implementation

## Executive Summary

ProofKit has been enhanced with comprehensive safety gates to ensure no incorrect PASS results leave the system. This document describes the validation campaign, acceptance criteria, and quality gates implemented across all six supported industries.

## Safety Mode Configuration

### Production Flags (Active Now)

```bash
SAFE_MODE=1                      # Master safety switch
REQUIRE_REQUIRED_SIGNALS=1       # Enforce spec.parameter_requirements
FAIL_ON_PARSER_WARNINGS=1        # Parser warnings → INDETERMINATE
ALLOW_ONLY_V2_SPECS=0           # Keep legacy support during migration
ENFORCE_PDF_A3=1                # Block non-compliant PDFs
BLOCK_IF_NO_TSA=1               # Require RFC3161 timestamps
HUMAN_QA_REQUIRED_FOR_PASS=1    # QA approval for all PASS results
REQUIRE_DIFF_AGREEMENT=1        # Shadow verification required
```

## Acceptance Gates by Industry

### Common Gates (All Industries)
- ✅ Required signals present per `spec.parameter_requirements`
- ✅ Timezone normalized; sampling ≥ spec.min_samples
- ✅ No duplicate timestamps; gaps ≤ allowed_gaps_s
- ✅ Unit consistency (°F/°C, kPa/psi, %RH) verified
- ✅ Engine result ≡ independent calculator within tolerance
- ✅ Evidence bundle root hash matches
- ✅ PDF/A-3 + RFC3161 timestamp verified
- ✅ Any warning → INDETERMINATE (in SAFE_MODE)

### Industry-Specific Gates

#### Powder Coating
- **Continuous hold**: ≥ spec.hold_s
- **Ramp rate**: ≤ spec.max_ramp_C_per_min
- **QI tolerance**: Δthreshold ≤ ±1°C
- **Shadow tolerances**: hold ±1s, ramp ±5%

#### Autoclave (Steam)
- **F0 value**: F0(121.1°C) ≥ 12
- **Pressure profile**: Consistent with saturated steam
- **Shadow tolerances**: F0 ±0.1, pressure ±2%

#### Sterile (EtO)
- **Required signals**: Humidity + gas concentration
- **Phase windows**: All phases within spec
- **Shadow tolerances**: Phase times ±60s

#### HACCP
- **Cooling phases**: 135→70°F ≤ 2h AND 135→41°F ≤ 6h
- **Interpolation**: Monotone decreasing
- **Shadow tolerances**: Phase times ±30s

#### Concrete (ASTM C31)
- **First 24h**: 16-27°C AND RH ≥95%
- **Shadow tolerances**: Compliance ±1%

#### Cold Chain (USP 797/659)
- **Temperature range**: 2-8°C ≥95% of samples/day
- **Excursion counting**: Accurate per USP
- **Shadow tolerances**: Compliance ±0.5%

## Implementation Status

### ✅ PR-A: Required Signals Enforcement
- **Files**: `core/errors.py`, `core/metrics_*.py`, `tests/acceptance/test_required_signals.py`
- **Status**: COMPLETE
- **Behavior**: Missing required signals → INDETERMINATE with explicit reason

### ✅ PR-B: Differential Verification
- **Files**: `core/shadow_compare.py`, `app.py`, `validation/independent/*`
- **Status**: COMPLETE
- **Behavior**: Shadow runs compare engine vs independent calc with tolerances

### ✅ PR-C: Parser Hardening
- **Files**: `core/columns_map.py`, `core/normalize.py`, `tests/normalize/test_locale_and_headers.py`
- **Status**: COMPLETE
- **Features**: Vendor headers, locale support, Excel timestamps, warning system

### ✅ PR-D: Evidence & PDF Verification
- **Files**: `core/pack.py`, `core/render_pdf.py`, `scripts/verify_bundle.py`
- **Status**: COMPLETE
- **Features**: Bundle verification, PDF blocking, INDETERMINATE watermarks

### ✅ PR-E: Acceptance Suite
- **Files**: `tests/acceptance/*`, `.github/workflows/acceptance.yml`, `web/templates/campaign.html`
- **Status**: COMPLETE
- **Features**: Comprehensive tests, CI gates, strict mode campaign analysis

## Validation Protocol

### 1. Production Validation (via CI/CD Pipeline)
```bash
# Validation is now automated via the single release pipeline
# Trigger validation campaign via GitHub Actions
gh workflow run release.yml \
  --ref main \
  --field validation_mode=full

# Or run locally for development
python -m cli.validate_campaign --all --strict

# Check confusion matrix (must be diagonal) after deployment
curl https://proofkit.net/campaign?strict=true
```

### 2. Manual Industry Verification
```bash
# Run on each industry
for industry in powder autoclave sterile haccp concrete coldchain; do
  python scripts/verify_industry.py --industry $industry --strict
done

# Download and verify bundles
python scripts/verify_bundle.py /path/to/evidence.zip
```

### 3. QA Checklist

Before approving any PASS result:

- [ ] All required signals present
- [ ] Shadow calculator agrees within tolerance
- [ ] No parser warnings
- [ ] Evidence bundle hash matches
- [ ] PDF/A-3 compliant
- [ ] RFC3161 timestamp valid
- [ ] Hold times meet spec
- [ ] Temperature tolerances met
- [ ] No data quality issues

## Monitoring & Alerts

### Automated Checks
- **Nightly CI**: Full acceptance suite at 2 AM UTC
- **Shadow verification**: Every upload runs dual calculation
- **Bundle integrity**: SHA-256 verification on all downloads
- **Performance**: Processing time/memory limits enforced

### Manual Reviews
- **Weekly**: Review INDETERMINATE cases
- **Monthly**: Audit PASS approvals
- **Quarterly**: Update acceptance criteria

## Release Policy

### Phase 1: Safety Mode (Current)
- HUMAN_QA_REQUIRED_FOR_PASS=1 for 2 weeks
- Pre-decision PDFs with watermarks
- Shadow verification on all uploads

### Phase 2: Gradual Release
- Remove QA requirement for low-risk industries
- Continue shadow verification
- Monitor accuracy metrics

### Phase 3: Full Production
- Remove QA requirement
- Keep shadow verification for audit
- Quarterly validation campaigns

## Customer Communication

### Safety Notice (Live on /trust)
"ProofKit runs shadow calculators and independent verification on all uploads. We will not issue a PASS when readings are incomplete or ambiguous. During safety mode, all PASS results require QA approval."

### INDETERMINATE Explanations
- Missing required signals: "Temperature and pressure both required for autoclave validation"
- Parser warnings: "Data quality issues detected - manual review required"
- Shadow disagreement: "Verification calculations outside tolerance - escalated to QA"

## Rollback Procedure

If issues detected:
```bash
# Immediate rollback
fly -a proofkit-prod secrets set \
  SAFE_MODE=0 \
  HUMAN_QA_REQUIRED_FOR_PASS=0 \
  REQUIRE_DIFF_AGREEMENT=0
```

## Success Metrics

### Target Accuracy
- False positive rate: 0% (no incorrect PASS)
- False negative rate: <5% (acceptable INDETERMINATE)
- Shadow agreement: >99.5%
- Bundle verification: 100%

### Current Status
- ✅ All safety flags active
- ✅ Shadow verification running
- ✅ Acceptance tests passing
- ✅ QA approval required
- ✅ Customer notice published

## Next Steps

1. **Week 1-2**: Monitor all INDETERMINATE cases
2. **Week 3-4**: Review shadow verification accuracy
3. **Month 2**: Begin gradual QA removal
4. **Month 3**: Full production with audit mode

---

*Last Updated: 2025-08-09*
*Safety Mode: ACTIVE*
*QA Required: YES*