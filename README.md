# ProofKit — CSV → Proof Certificate (Powder-Coat Cure v0.1)

Turn an oven/part temperature log (CSV) + a small JSON spec into:
- **proof.pdf** — an inspector-ready certificate (PASS/FAIL, chart, fields, QR with integrity hash)
- **evidence.zip** — a tamper-evident bundle (inputs, normalized.csv, decision.json, plot.png, manifest with SHA-256)

**Why ProofKit?**
Manufacturing shops and quality inspectors need clean, repeatable proof of cure processes. Logger vendors bundle tools for their own devices; ProofKit is **vendor-neutral** and **cryptographically verifiable**, supporting any CSV temperature data source.

## How it works (MVP)
1. Upload CSV (timestamp + temperature columns) and a spec JSON (target temp, hold time, rules).
2. ProofKit:
   - normalizes timezones and units,
   - checks data quality,
   - evaluates cure logic (continuous or cumulative hold),
   - renders a chart and a 1-page certificate,
   - packs everything with hashes into `evidence.zip`.
3. Anyone can open the Verify page (or run the CLI) to re-check the bundle.

## Live endpoints (MVP)
- POST `/api/compile` → `{ id, pass, metrics, urls: { pdf, zip, verify } }`
- GET  `/verify/{id}` → re-runs verification and shows metrics
- GET  `/download/{id}/pdf` / `/download/{id}/zip`

## Spec (powder-coat cure v1)
```json
{
  "version": "powder_coat_cure.v1",
  "job": { "job_id": "PC-2025-0802-17", "oven_id": "OV-3" },
  "spec": {
    "method": "PMT",
    "target_temp_C": 180.0,
    "hold_time_s": 600,
    "hysteresis_C": 2.0,
    "sensor_uncertainty_C": 2.0,
    "sensor_selection": {
      "mode": "min_of_set",
      "sensors": ["temp_C_s1","temp_C_s2","temp_C_s3"],
      "require_at_least": 2
    },
    "logic": { "continuous": true, "max_total_dips_s": 0 },
    "preconditions": { "max_time_to_threshold_s": 3600 }
  },
  "data_requirements": { "max_sample_period_s": 60, "allowed_gaps_s": 120 },
  "reporting": { "timezone": "Europe/Istanbul", "units": "C" }
}
```

## Example CSV (snippet)
```csv
# job_id: PC-2025-0802-17
timestamp,temp_C_s1,temp_C_s2,temp_C_s3,oven_air_C
2025-08-02T10:31:00+03:00,142.3,141.8,142.9,177.2
2025-08-02T10:31:30+03:00,151.0,150.2,151.5,184.0
...
```

## Quick start (local)
```bash
# Python 3.11+ required
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Verify installation
curl http://localhost:8000/health
# Expected: {"status": "ok", "version": "0.1.0"}

# Test with examples
curl -F "csv=@examples/powder_coat_cure_successful_180c_10min_pass.csv" \
     -F "spec=@examples/powder_coat_cure_spec_standard_180c_10min.json" \
     http://localhost:8000/api/compile
```

### CLI Usage
```bash
# Install CLI tools
pip install -e .

# Complete workflow example
proofkit normalize --csv examples/powder_coat_cure_successful_180c_10min_pass.csv --out /tmp/norm.csv --tz "Europe/Istanbul"
proofkit decide --csv /tmp/norm.csv --spec examples/powder_coat_cure_spec_standard_180c_10min.json --out /tmp/decision.json
proofkit render --decision /tmp/decision.json --csv /tmp/norm.csv --out /tmp/proof.pdf --plot /tmp/plot.png
proofkit pack --inputs examples/powder_coat_cure_successful_180c_10min_pass.csv examples/powder_coat_cure_spec_standard_180c_10min.json --normalized /tmp/norm.csv --decision /tmp/decision.json --pdf /tmp/proof.pdf --plot /tmp/plot.png --out /tmp/evidence.zip
proofkit verify --bundle /tmp/evidence.zip
```

## Deployment

### Deploy to Fly.io

ProofKit is optimized for deployment on Fly.io with persistent storage and auto-scaling.

#### Prerequisites
```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login to Fly.io
fly auth login
```

#### Initial Deployment
```bash
# Clone and prepare the application
git clone <your-repo-url> proofkit
cd proofkit

# Create the Fly.io app
fly apps create proofkit

# Create persistent storage volume (1GB)
fly volumes create proofkit_storage --region ord --size 1

# Deploy the application
fly deploy

# Check deployment status
fly status
fly logs
```

#### Configuration Management
```bash
# Set production environment variables
fly secrets set RETENTION_DAYS=7
fly secrets set MAX_UPLOAD_MB=25
fly secrets set RATE_LIMIT_PER_MIN=50

# Scale based on usage
fly scale count 2
fly scale memory 1024

# Monitor health
fly status --all
curl https://proofkit.fly.dev/health
```

#### Maintenance Commands
```bash
# View application logs
fly logs --follow

# Access storage volume
fly ssh console
ls -la /app/storage/

# Update deployment
git pull origin main
fly deploy

# Rollback if needed
fly releases list
fly releases rollback v42
```

### Deploy to Render

Render provides simple deployment with automatic builds from Git repositories.

#### Prerequisites
- Render account with GitHub/GitLab connected
- Repository pushed to GitHub/GitLab

#### Deployment Steps

1. **Create Web Service**
   ```bash
   # Visit https://dashboard.render.com/
   # Click "New +" -> "Web Service"
   # Connect your repository
   ```

2. **Configure Service Settings**
   ```yaml
   # Service Configuration (render.yaml is included)
   Name: proofkit
   Environment: Docker
   Region: Oregon (or closest to users)
   Branch: main
   Dockerfile Path: ./Dockerfile
   ```

3. **Environment Variables** (set in Render dashboard)
   ```bash
   RETENTION_DAYS=14
   MAX_UPLOAD_MB=10
   CORS_ORIGINS=*
   RATE_LIMIT_PER_MIN=30
   MPLBACKEND=Agg
   PYTHONUNBUFFERED=1
   TZ=UTC
   ```

4. **Deploy and Verify**
   ```bash
   # Render auto-deploys on git push
   git push origin main
   
   # Check deployment at your Render URL
   curl https://proofkit.onrender.com/health
   ```

#### Render-Specific Features
```bash
# Automatic scaling configuration
# Set in render.yaml:
scaling:
  minInstances: 1
  maxInstances: 3
  targetCPUPercent: 80

# Persistent disk for evidence storage
disk:
  name: proofkit-storage
  mountPath: /app/storage
  sizeGB: 1

# Custom domain setup (optional)
# Add in Render dashboard under "Settings" -> "Custom Domains"
```

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `RETENTION_DAYS` | Days to keep evidence bundles before cleanup | `30` | No |
| `MAX_UPLOAD_MB` | Maximum file upload size in MB | `10` | No |
| `BASE_URL` | Base URL for generated links | Auto-detected | No |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `*` | No |
| `RATE_LIMIT_PER_MIN` | API requests per minute per IP | `10` | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |
| `CLEANUP_INTERVAL_HOURS` | Hours between cleanup cycles | `24` | No |
| `MPLBACKEND` | Matplotlib backend for plotting | `Agg` | No |
| `PYTHONUNBUFFERED` | Disable Python output buffering | `1` | No |
| `TZ` | Timezone for server operations | `UTC` | No |

### Development Setup

#### Requirements
- Python 3.11 or higher
- pip or pipenv for dependency management
- Git for version control

#### Setup Steps
```bash
# Clone repository
git clone <your-repo-url> proofkit
cd proofkit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install CLI tools in development mode
pip install -e .

# Run tests
python -m pytest tests/ -v

# Run with hot reload
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

#### Development Verification
```bash
# Health check
curl http://localhost:8000/health

# Test API endpoint
curl -X POST \
  -F "csv=@examples/powder_coat_cure_successful_180c_10min_pass.csv" \
  -F "spec=@examples/powder_coat_cure_spec_standard_180c_10min.json" \
  http://localhost:8000/api/compile

# Test CLI commands
proofkit --help
proofkit normalize --help
```

## Design guarantees
- **Deterministic results** for identical inputs.
- **Unit-safe conversions** (°F accepted; outputs in °C).
- **Tamper-evident bundles** (per-file SHA-256 + root hash, QR in PDF).
- **Vendor-neutral CSV**: any logger that exports timestamp + temperature works.

## API Documentation

### Core Endpoints

#### POST `/api/compile`
Generate proof certificate and evidence bundle from CSV and specification.

**Request:**
```bash
curl -X POST \
  -F "csv=@temperature_data.csv" \
  -F "spec=@cure_specification.json" \
  https://proofkit.fly.dev/api/compile
```

**Response:**
```json
{
  "id": "68a61313bd",
  "pass": true,
  "metrics": {
    "hold_time_achieved_s": 612,
    "min_temp_during_hold_C": 178.2,
    "max_temp_during_hold_C": 182.1,
    "time_to_threshold_s": 420,
    "total_cure_time_s": 1032
  },
  "urls": {
    "pdf": "/download/68a61313bd/pdf",
    "zip": "/download/68a61313bd/zip", 
    "verify": "/verify/68a61313bd"
  }
}
```

#### GET `/verify/{id}`
Re-verify evidence bundle and display detailed metrics.

**Request:**
```bash
curl https://proofkit.fly.dev/verify/68a61313bd
```

**Response:** HTML page with verification results or JSON if `Accept: application/json` header provided.

#### GET `/download/{id}/{type}`
Download generated files (pdf, zip).

**Examples:**
```bash
# Download proof certificate
curl -O https://proofkit.fly.dev/download/68a61313bd/pdf

# Download evidence bundle
curl -O https://proofkit.fly.dev/download/68a61313bd/zip
```

#### GET `/health`
Service health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "timestamp": "2025-08-04T12:34:56Z"
}
```

### Rate Limiting
- Default: 10 requests per minute per IP address
- Configurable via `RATE_LIMIT_PER_MIN` environment variable
- Returns HTTP 429 when exceeded

### File Size Limits
- Maximum upload size: 10MB (configurable via `MAX_UPLOAD_MB`)
- Supported CSV formats: UTF-8, ISO-8859-1
- JSON specifications: Must validate against schema

### Error Responses
```json
{
  "error": "Invalid CSV format",
  "details": "Missing required columns: timestamp, temp_C_s1",
  "code": "CSV_VALIDATION_ERROR"
}
```

## Testing & Quality Assurance

### Running Tests
```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests with coverage
python -m pytest tests/ -v --cov=core --cov-report=html

# Run specific test categories
python -m pytest tests/test_normalize.py -v
python -m pytest tests/test_decide.py -v
python -m pytest tests/test_verify.py -v

# Run golden tests (end-to-end validation)
python -m pytest tests/test_golden.py -v
```

### Test Coverage Areas
- **Data normalization**: Unit conversion, timezone handling, data validation
- **Decision logic**: Continuous vs cumulative hold, sensor selection modes
- **PDF generation**: Chart rendering, certificate layout, QR code integrity
- **Bundle packing**: File integrity, manifest generation, SHA-256 verification
- **API endpoints**: Request validation, response formatting, error handling

### Continuous Integration
The project includes automated testing via GitHub Actions:

```yaml
# .github/workflows/test.yml (example)
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.11, 3.12]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run tests
        run: python -m pytest tests/ -v --cov=core
```

### Quality Metrics
- **Type checking**: mypy configuration in `mypy.ini`
- **Code formatting**: Project follows PEP 8 standards
- **Test coverage**: Target >90% coverage for core modules
- **Performance**: Sub-5 second processing for typical datasets (<1000 points)

## Roadmap (next)
- HACCP cook/chill and IAQ weekly compliance modules.
- Preset library for common powders/specs.
- Optional digital signatures (PKI) in proof PDFs.
- SQLite job index, magic-link access, auto-delete after N days.

## License
MIT