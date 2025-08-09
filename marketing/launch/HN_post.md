# Show HN: ProofKit - Generate inspector-ready certificates from any temperature log

Hi HN! I built ProofKit after watching quality teams struggle with manual temperature validation for compliance. Upload a CSV from any data logger, specify your requirements, and get an inspector-ready PDF certificate with cryptographic proof.

**What it does:**
- Validates temperature data against industry standards (powder coating cure, autoclave sterilization, HACCP cooling, cold chain storage, concrete curing)
- Generates tamper-evident PDF certificates with QR codes and SHA-256 verification
- Creates evidence bundles that can be independently verified years later
- Works with any CSV format - handles vendor quirks, timezones, units automatically

**Technical approach:**
- FastAPI + Python for deterministic validation algorithms
- PDF/A-3 with embedded evidence for long-term archival
- RFC 3161 timestamps for legal non-repudiation
- Independent verification - download our Python script and verify any certificate offline

**Try it:**
Upload any temperature CSV at https://proofkit.net - first 2 certificates free.

**Example GIFs:**
- Powder coating validation: /examples/powder_demo.gif
- Autoclave F0 calculation: /examples/autoclave_demo.gif

I'd love feedback on the validation algorithms and ideas for other industries that need temperature compliance documentation.

Code for verification: https://github.com/proofkit/verify
Docs: https://proofkit.net/trust