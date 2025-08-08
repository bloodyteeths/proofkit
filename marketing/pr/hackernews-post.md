# Show HN: ProofKit — CSV→Compliance certificates (PDF/A‑3, RFC 3161)

Link: https://www.proofkit.net  
Examples (sample data): https://www.proofkit.net/examples  
Get started (free): https://www.proofkit.net/auth/get-started

---

## What is it?

ProofKit turns temperature CSV logs into tamper‑evident compliance certificates (PDF/A‑3) for 6 industries (powder coating, HACCP, autoclave, concrete, vaccine storage, sterile processing). Upload a CSV → get a deterministic pass/fail decision, chart, and a verifiable PDF package.

---

## Why it matters

- Teams still build audit PDFs manually in Excel; it’s slow and error‑prone.
- Auditors want objective, reproducible evidence tied to a lot/batch.
- Deterministic algorithms + RFC 3161 timestamps reduce disputes and rework.

---

## How it works (technical)

- Deterministic pipeline: identical CSV → identical PDF + SHA‑256 hash
- Conservative thresholds w/ sensor uncertainty; hysteresis for crossings
- PDF/A‑3 with embedded raw data and parameters; QR links to verification
- FastAPI + Pydantic v2; Pandas/NumPy; ReportLab for PDFs

---

## Live demo

Explore sample data/outputs: https://www.proofkit.net/examples  
Generate your own: https://www.proofkit.net/auth/get-started

Use cases:
1) Powder coating cure: 180 °C for 10 min → ISO/Qualicoat validation  
2) HACCP cooling: 135→70→41 °F timing → inspector‑ready record  
3) Autoclave: FO value calc with temperature/pressure  
4) Concrete (ASTM C31): initial cure temperature window  
5) Vaccine storage: 2–8 °C excursions + actions logged

---

## Specs samples

Browse JSON spec samples (validation rules): https://www.proofkit.net/spec-examples/

---

## Feedback welcome

1) What other compliance processes still require manual PDFs in your field?  
2) Any edge cases we should test in the CSV parser/validation?  
3) Would an API or CLI help you automate bulk runs?

---

## Try it

Examples: https://www.proofkit.net/examples  
Docs: https://www.proofkit.net/docs  
Questions: support@proofkit.net

Upload a CSV, get a certificate (<30 s in most cases). No credit card required.