# Live QA Audit System

## Overview

The Live QA Audit system provides automated end-to-end validation of PDF generation and verification in production. It tests each industry with real examples, validates outputs, and identifies any broken example datasets.

## Components

### 1. Live PDF Audit Runner (`scripts/live_pdf_audit.py`)
- Submits compilation jobs to production for each industry
- Downloads PDF, evidence bundle, and verify page
- Respects rate limits (1 job/sec, max 30 jobs/run)
- Tags jobs with `LIVE-QA` for tracking

### 2. PDF Inspector (`scripts/inspect_pdf.py`)
- Extracts text and metadata from generated PDFs
- Validates PASS/FAIL/INDETERMINATE banners
- Checks for job IDs and SHA-256 hashes
- Verifies PDF/A compliance markers

### 3. Bundle Verifier (`scripts/verify_bundle.py`)
- Validates evidence.zip integrity
- Verifies manifest SHA-256 hashes
- Recomputes decision locally from normalized data
- Compares local vs production decisions

### 4. Example Truth Checker (`scripts/check_example_truth.py`)
- Validates that example CSVs meet their spec requirements
- Identifies mismatches between expected and actual outcomes
- Generates corrected datasets when needed
- Creates fix plan for broken examples

### 5. Live Audit Dashboard (`web/templates/live_audit.html`)
- Visual dashboard showing all validation results
- Industry-by-industry breakdown
- Links to artifacts and verify pages
- Summary statistics and match rates

## Environment Variables

```bash
# Required
BASE_URL=https://proofkit.net          # Target environment
LIVE_QA_EMAIL=tester@proofkit.net      # Test user email
LIVE_QA_TOKEN=<magic-link-token>       # Authentication token

# Optional
LIVE_QA_TAG=LIVE-QA                    # Job tracking tag (default: LIVE-QA)
```

## Running the Audit

### Local Execution

```bash
# Set environment
export BASE_URL=https://proofkit.net
export LIVE_QA_EMAIL=tester@proofkit.net
export LIVE_QA_TOKEN=<your-token>

# Run audit
python -m scripts.live_pdf_audit

# Inspect specific PDF
python -m scripts.inspect_pdf live_runs/*/powder/proof.pdf

# Verify specific bundle
python -m scripts.verify_bundle live_runs/*/powder/evidence.zip

# Check truth and generate fixes
python -m scripts.check_example_truth live_runs/20241208_143022/
```

### GitHub Actions

The audit can be triggered manually via GitHub Actions:

1. Go to Actions → Live QA Audit
2. Click "Run workflow"
3. Enter target URL and job tag
4. Review results in workflow summary

## Output Structure

```
live_runs/
├── 20241208_143022/           # Timestamp directory
│   ├── powder/
│   │   ├── api.json           # API response
│   │   ├── proof.pdf          # Generated PDF
│   │   ├── evidence.zip       # Evidence bundle
│   │   └── verify.html        # Verify page HTML
│   ├── autoclave/
│   │   └── ...
│   ├── summary.json           # Run summary
│   └── fixes_plan.json        # Proposed fixes
```

## Cleanup Policy

LIVE-QA tagged jobs receive special retention treatment:
- **Minimum retention**: 7 days (regardless of global settings)
- **Identification**: Jobs with `job_tag: LIVE-QA` in metadata
- **Cleanup**: Automatic via standard cleanup process

Regular jobs continue to use the standard `RETENTION_DAYS` setting.

## Interpreting Results

### Success Criteria
- ✅ **PDF Generated**: PDF file exists and contains expected content
- ✅ **Bundle Valid**: Evidence.zip with valid manifest and hashes
- ✅ **Decision Match**: API, PDF, and local recompute all agree
- ✅ **Example Valid**: CSV meets spec requirements for outcome

### Common Issues
- **Hash Mismatch**: Files modified after manifest creation
- **Decision Mismatch**: Engine inconsistency or spec interpretation
- **Example Invalid**: CSV doesn't actually meet spec requirements
- **Missing Artifacts**: Generation failure or cleanup race condition

## Fixing Broken Examples

When the truth checker identifies invalid examples:

1. Review the `fixes_plan.json` for details
2. Check generated fixes in `live_runs/*/fixes/`
3. Test fixes locally before applying
4. Update examples in repository
5. Re-run audit to confirm fixes

## Safety Measures

- **Rate limiting**: 1 second between requests
- **Job limits**: Maximum 30 jobs per run
- **Tagged jobs**: LIVE-QA tag prevents accidental cleanup
- **Dry run**: Bundle verifier supports dry-run mode
- **No mutations**: Read-only validation, creates only test jobs

## Troubleshooting

### Authentication Issues
- Ensure magic link token is valid and not expired
- Check user has appropriate permissions
- Verify BASE_URL is correct

### Missing Artifacts
- Check job completed successfully
- Verify cleanup hasn't removed files
- Ensure sufficient storage space

### Decision Mismatches
- Compare spec interpretations
- Check for timing/rounding differences
- Verify CSV normalization consistency

### Fix Generation Failures
- Review spec requirements carefully
- Check for edge cases in validators
- Manually create example if generator fails