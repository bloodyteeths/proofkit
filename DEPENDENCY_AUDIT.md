# ProofKit Dependency Audit for Fly.io Deployment

## Current Error Analysis
**Error:** `ImportError: failed to find libmagic. Check your installation`
**Root Cause:** python-magic requires libmagic1 system library

## System Dependencies Required

### 1. Already Added to Dockerfile:
- `fonts-dejavu` - For consistent PDF fonts (ReportLab)
- `tzdata` - Timezone data for Python datetime
- `curl` - Health check functionality

### 2. MISSING - Need to Add:
- `libmagic1` - Required by python-magic for MIME type detection
- `libmagic-dev` - Development headers (might be needed)

### 3. Python Libraries Analysis:

#### Graphics & PDF Generation:
- **matplotlib** - Requires: 
  - No additional system deps (using Agg backend)
  - Already set MPLBACKEND=Agg in Dockerfile
- **reportlab** - Requires:
  - Fonts (already have fonts-dejavu)
  - Pillow for image handling (included in qrcode[pil])
- **qrcode[pil]** - Requires:
  - Pillow (included)
  - No additional system deps

#### File Processing:
- **python-magic** - Requires:
  - `libmagic1` (MISSING - causing the error)
  - `libmagic-dev` (potentially needed)

#### Scientific Computing:
- **pandas/numpy** - No additional system deps needed
- **pytz** - Uses tzdata (already included)

## Dockerfile Updates Needed:

```dockerfile
# Current:
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Should be:
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    tzdata \
    curl \
    libmagic1 \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean
```

## Additional Considerations:

### 1. File Permissions:
- Storage directory mounting: ✅ Already handled
- User permissions: ✅ Already using non-root user

### 2. Environment Variables:
- MPLBACKEND=Agg: ✅ Set
- PYTHONUNBUFFERED: ✅ Set
- TZ=UTC: ✅ Set

### 3. Health Check Dependencies:
- curl: ✅ Already included

### 4. Python Path:
- PATH="/home/proofkit/.local/bin:$PATH": ✅ Set correctly

## Risk Assessment:

### High Risk (Will Cause Deployment Failure):
- ❌ Missing libmagic1 - **CRITICAL** (already failing)
- ❌ Missing libmagic-dev - **LIKELY** (might be needed for python-magic)

### Medium Risk (Might Cause Runtime Issues):
- ✅ Font registration - Handled in Dockerfile
- ✅ Storage permissions - Handled in Dockerfile
- ✅ Python path - Correctly configured

### Low Risk (Already Handled):
- ✅ Matplotlib backend - Set to Agg
- ✅ Timezone handling - tzdata installed
- ✅ PDF generation - fonts-dejavu installed

## Next Steps:
1. Add libmagic1 and libmagic-dev to Dockerfile
2. Deploy and test
3. Monitor logs for any additional missing dependencies