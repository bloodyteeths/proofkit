# claude.md — Working Rules

## Principles
after          │
│   complation, each agent has to write summary of what  │
│   they did and note to future claude to roadmap  
- Single-purpose MVP: powder-coat cure proof from CSV + spec. No auth, no DB.
- Deterministic outputs: identical inputs → identical PDFs and hashes.
- Minimal deps: FastAPI, Pydantic v2, pandas, numpy, matplotlib, reportlab, jsonschema, qrcode.

## File Hygiene
- Always write full files (not diffs) when asked to "create" or "replace".
- Use absolute, explicit imports within our package namespace (no from * imports).
- Each module must have type hints, docstrings, and a 5–10 line example in comments.
- Keep functions ≤ 60 lines; split helpers where needed.

## Data Contracts
- Implement and validate `core/spec_schema.json`. Reject unknown fields.
- Never proceed if CSV fails quality checks (sampling, gaps). Return a clear error JSON and human message.
- decision.json must match the Roadmap's schema exactly.

## Algorithms (must match)
- conservative_threshold = target + sensor_uncertainty.
- Hysteresis (default 2°C) on threshold crossings.
- Continuous hold by longest interval above (threshold−hyst); cumulative hold if specified.
- Ramp rate = max derivative (°C/min) using central differences.
- Time-to-threshold measured from first sample.

## Security/Size
- Max CSV 10 MB; max rows 200k; streaming parse (pandas chunks or csv stdlib).
- Restrict file types via magic; sanitize filenames; never trust client path.
- Rate-limit: naive in-memory token bucket per IP.

## Output & Integrity
- Plot with consistent font + size; include target/threshold lines and shaded hold interval.
- PDF must include: PASS/FAIL banner, spec box, results box, chart, QR of root hash.
- evidence.zip: include manifest with per-file SHA-256 and root hash; verify() recomputes and re-runs decision.

## Web UX
- One page with upload form (CSV + pre-filled spec JSON textarea).
- After submit: show PASS/FAIL, metrics table, links to proof.pdf, evidence.zip, and verify page.
- No SPA; Jinja + HTMX partials only.

## Testing
- Write pytest tests for normalize(), decide(), verify() using examples.
- Add golden files for plots and PDFs (hash compare leniently by bytesize + first 512 bytes).
- CI: run tests + flake8 + mypy.

## Commit & PR Style
- Conventional commits (feat:, fix:, chore:, docs:).
- Small PRs mapped to milestones M1–M8.