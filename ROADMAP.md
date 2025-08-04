# Roadmap — ProofKit (v0.1)
Generate an inspector-ready proof PDF + a tamper-evident evidence bundle from:
CSV temperature logs + a small JSON spec (powder-coat cure, wedge #1).

## 0) Scope (MVP)
- Input: CSV with timestamps + one or more temperature columns.
- Spec: JSON defining target temp, hold time, sensors, data quality rules.
- Output:
  a) proof.pdf (PASS/FAIL, chart, fields, QR with hash)
  b) evidence.zip (inputs, normalized.csv, decision.json, plot.png, manifest with SHA-256)
- Web: single-page upload → returns proof.pdf + evidence.zip + share/verify link.
- CLI: normalize/decide/render/pack/verify.

## 1) Architecture (minimal)
- Backend: Python 3.11, FastAPI, Pydantic v2, Uvicorn.
- Core: pandas/numpy (normalize), matplotlib (plot), jsonschema (validate spec),
  qrcode (QR), reportlab OR WeasyPrint (PDF, start with ReportLab to avoid system deps),
  hashlib + zipfile (integrity bundle).
- Frontend: Jinja2 templates + HTMX + Pico.css (no SPA).
- Storage: local disk (./storage) for MVP; path hashing by job_id.
- No DB for v0.1. Add SQLite in v0.2 (jobs table) if needed.
- Deployment: Dockerfile + Fly.io/Render. Single container.

## 2) Milestones & Acceptance
M0 — Repo scaffold (Day 0) ✅ COMPLETED
- [x] FastAPI app skeleton, /health endpoint, Dockerfile, Makefile, pre-commit.
- [x] ./core, ./web, ./storage, ./examples folders.

M1 — Spec + Normalizer (Day 1–2) ✅ COMPLETED (except unit tests)
- [x] JSON Schema for spec_v1; pydantic models.
- [x] CSV loader: metadata (# key: value), tz normalize→UTC, °F→°C.
- [x] Resample to fixed step (default 30 s), forbid gaps > allowed_gaps_s.
- [ ] Unit tests: happy path + gaps + dup timestamps.

M2 — Decide (Day 3) ✅ COMPLETED (except tests)
- [x] Algorithm: conservative threshold = target + sensor_uncertainty; hysteresis.
- [x] continuous vs cumulative hold logic; preconditions; data quality checks.
- [x] decision.json shape (pass, reasons[], metrics{}, warnings[]).
- [ ] Tests: pass, short_hold, data_gaps, slow_ramp.

M3 — PDF & Plot (Day 4) ✅ COMPLETED
- [x] plot.png (PMT + target/threshold + shaded hold).
- [x] proof.pdf (ReportLab): PASS/FAIL banner, spec box, results box, chart, hash, QR.
- [x] Deterministic rendering (timezone, fonts).

M4 — Evidence bundle + Verify (Day 5) ✅ COMPLETED
- [x] Zip manifest with SHA-256 per file + root hash.
- [x] verify(): recompute hashes, re-run decision, compare.
- [x] CLI: normalize/decide/render/pack/verify.

M5 — Web UI (Day 6) ✅ COMPLETED
- [x] Upload CSV + paste/edit spec JSON (pre-populated preset).
- [x] Returns proof.pdf + evidence.zip; show small HTML preview.
- [x] 10MB file cap, MIME checks.

M6 — Share & Verify page (Day 7) ✅ COMPLETED
- [x] /verify/:id reads bundle, prints PASS/FAIL + metrics; "download originals".
- [x] Short IDs map to local file path (no DB; id = first 10 chars of root SHA).

M7 — SEO Samples (Day 7) ✅ COMPLETED
- [x] Publish examples (PASS, FAIL, templates) with descriptive filenames.
- [x] /examples page linking to raw files.

M8 — Deploy (Day 8)
- [ ] Fly.io/Render deployment; 2GB RAM, persistent volume ./storage.
- [ ] Smoke tests post-deploy.

M9 — Polish & Guardrails (Day 9–10)
- [ ] Rate-limit (IP), size checks, error pages.
- [ ] Logging + request IDs; simple CORS config.
- [ ] Privacy note: files auto-delete after N days (ENV).

Acceptance: All example datasets produce deterministic outputs; verify() passes; deploy returns a valid PDF within 3 seconds for examples.

## 3) Directory Layout
```
.
├─ app.py                 # FastAPI entry
├─ core/
│  ├─ spec_schema.json
│  ├─ models.py           # Pydantic models
│  ├─ normalize.py        # CSV→normalized
│  ├─ decide.py           # decision.json
│  ├─ render_pdf.py       # proof.pdf
│  ├─ plot.py             # plot.png
│  ├─ pack.py             # evidence.zip + manifest
│  └─ verify.py
├─ web/
│  ├─ templates/          # Jinja (index.html, result.html, verify.html)
│  └─ static/             # pico.css, tiny JS
├─ cli/
│  └─ main.py             # Typer CLI
├─ examples/
│  ├─ ok_run.csv
│  ├─ short_hold.csv
│  ├─ gaps.csv
│  ├─ spec_ok.json
│  └─ outputs/            # golden PDFs/ZIPs
├─ tests/
│  ├─ test_normalize.py
│  ├─ test_decide.py
│  ├─ test_verify.py
│  └─ data/               # copies of examples
├─ storage/               # runtime artifacts
├─ Dockerfile
├─ Makefile
├─ README.md
└─ claude.md
```

## 4) Spec v1 (powder-coat cure)
- Required fields:
  version, job.job_id, spec.method("PMT"|"OVEN_AIR"),
  spec.target_temp_C (>0), spec.hold_time_s (>=1),
  data_requirements.max_sample_period_s, allowed_gaps_s.
- Optional:
  temp_band_C{min,max}, sensor_uncertainty_C (default 2.0),
  sensor_selection {mode:"min_of_set"|"mean_of_set"|"majority_over_threshold", sensors[], require_at_least},
  logic {continuous:bool, max_total_dips_s:int}, preconditions {max_ramp_rate_C_per_min, max_time_to_threshold_s},
  reporting {units:"C"|"F", language, timezone}.

## 5) Algorithm (concise)
- conservative_threshold = target + sensor_uncertainty.
- combined_PMT(t) by selection mode; smoothing optional (window ≤ 2× sample step).
- Continuous: longest interval where PMT ≥ threshold−hysteresis; pass if length ≥ hold_time.
- Cumulative: sum time above threshold allowing total dips ≤ max_total_dips_s.
- Enforce gaps, sampling, ramp rate, time-to-threshold; produce reasons[] and warnings[].

## 6) API (MVP)
POST /api/compile
  multipart/form-data: csv(file), spec(json string)
  → 200: { id, pass, metrics, urls: { pdf, zip, verify } }

GET /verify/{id}
  Renders verify page (re-check bundle, show metrics)

GET /download/{id}/pdf | /zip

## 7) CLI
```bash
proofkit normalize --csv raw.csv --out normalized.csv --tz "Europe/Istanbul"
proofkit decide --csv normalized.csv --spec spec.json --out decision.json
proofkit render --decision decision.json --csv normalized.csv --out proof.pdf --plot plot.png
proofkit pack --inputs raw.csv spec.json --normalized normalized.csv --decision decision.json --pdf proof.pdf --plot plot.png --out evidence.zip
proofkit verify --bundle evidence.zip
```

## 8) Testing matrix
- CSV timezones: local TZ, UTC, unix seconds.
- Units: °F input, °C output.
- Multiple sensors: missing one column, require_at_least enforcement.
- Data gaps: within and exceeding allowed_gaps_s.
- Threshold edge: exactly at boundary with hysteresis.
- Determinism: same inputs → identical hashes.

## 9) v0.2 Targets (after launch)
- Presets: spec presets list (dropdown).
- HACCP cook/chill module (same engine).
- IAQ weekly compliance (CO₂ percentile metric).
- Simple job list (SQLite), magic-link auth, delete-after N days job GC.

## REPOS TO FORK (to stay minimal)
- bigskysoftware/htmx           # tiny progressive enhancement for forms
- picocss/pico                  # classless CSS for clean UI
- Kozea/WeasyPrint              # HTML→PDF (OPTIONAL; start with ReportLab to avoid sys deps)
- reportlab/reportlab           # pure-Python PDF (MVP default)
- pydantic/pydantic             # typed models (v2)
- python-jsonschema/jsonschema  # spec validation
- matplotlib/matplotlib         # charts
- encode/uvicorn                # ASGI server
- tiangolo/typer                # CLI