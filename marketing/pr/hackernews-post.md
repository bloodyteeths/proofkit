# Show HN: ProofKit – Open-Source Quality Control Specs + CSV-to-Certificate Automation

**Link:** https://proofkit.io  
**GitHub:** https://github.com/proofkit/specifications  
**Demo:** https://proofkit.io/demo (try with sample CSV)

---

## What is ProofKit?

ProofKit transforms quality control data (CSV) into tamper-proof compliance certificates across six industries. Think "Stripe for quality validation" – upload sensor data, get regulatory-grade PDF/A-3 certificates with blockchain verification.

**Key insight:** Most quality control is still manual Excel hell. A powder-coat manufacturer spends 8 hours creating cure certificates for each batch. HACCP kitchens manually calculate cooling curves. We automate this to 30 seconds with deterministic algorithms.

---

## Technical Architecture

**Deterministic by Design:**
- Identical CSV input → identical PDF output + SHA-256 hash
- Conservative threshold calculations with sensor uncertainty
- Hysteresis control for temperature fluctuation handling
- PDF/A-3 format with embedded evidence + RFC 3161 timestamps

**Stack:**
- FastAPI + Pydantic v2 for robust data validation
- Pandas/NumPy for time-series analysis
- ReportLab for PDF generation with embedded evidence
- JSONSchema validation against industry specifications
- QR codes linking to blockchain verification

**Open Source Specs:**
We've open-sourced our industry specification library:
- `powder_coat_iso2368.json` – Qualicoat compliance
- `haccp_cooling_135_70_41.json` – Food safety validation  
- `autoclave_fo_value.json` – Pharmaceutical sterilization
- `concrete_astm_c31.json` – Construction curing logs
- `vaccine_usp797.json` – Cold chain monitoring

---

## Why This Matters

**Compliance is broken everywhere:**
- Manufacturing: Manual cure certificates fail Qualicoat audits
- Food service: 25% HACCP documentation errors lead to closures
- Healthcare: Autoclave validation costs $50K+ for commercial systems
- Construction: Concrete specification failures cost $75K per re-pour
- Pharma: Vaccine cold chain breaks destroy $50K inventory

**Our solution:** 
Deterministic algorithms + tamper-proof certificates + industry-standard compliance = automated trust.

---

## Live Demo

Upload your CSV at **proofkit.io/demo** (works with any temperature logger):

1. **Powder coating cure:** 180°C for 10 minutes → automatic ISO 2368 validation
2. **HACCP cooling:** 135°F→70°F→41°F timing analysis → health inspector ready
3. **Autoclave cycle:** Fo value calculation with pressure correlation
4. **Concrete curing:** Maturity index with strength estimation
5. **Vaccine storage:** 2-8°C excursion detection with potency impact

**Sample CSVs provided** – see real certificates generated in <30 seconds.

---

## Technical Innovation

**PDF/A-3 with Embedded Evidence:**
Each certificate contains the original CSV, processing algorithms, and verification chain. Inspectors can extract and re-validate using any PDF reader.

**Blockchain Verification:**
SHA-256 hashes stored on-chain with RFC 3161 timestamps. QR codes enable instant authenticity verification via smartphone.

**Streaming CSV Parser:**
Handles 10MB files with 200K+ data points using chunked processing. No memory limits for large industrial datasets.

---

## Business Model

**Freemium SaaS:**
- Free: 3 certificates/month
- Pro: €49/month unlimited with custom branding
- Enterprise: API access + multi-location management

**Current traction:**
- 500+ facilities using the platform
- 100% audit success rate across industries
- 95% average time reduction in documentation

---

## Open Source Philosophy

**Why open-source the specs?**
Quality control shouldn't be proprietary. Industry standards like ISO 2368 and ASTM C31 are public – our implementations should be too.

**Community contributions welcome:**
- New industry specifications
- Algorithm improvements
- Localization for international standards
- Integration with additional sensor formats

---

## Questions We'd Love Feedback On

1. **Industry coverage:** What quality control processes still require manual documentation in your field?

2. **Technical approach:** Is our deterministic validation model useful for other compliance domains?

3. **Open source strategy:** Would you contribute specifications for your industry?

4. **Scaling challenges:** How do we handle regulatory variations across countries/regions?

---

## Try It Now

**Live demo:** proofkit.io/demo  
**Documentation:** docs.proofkit.io  
**Specs repo:** github.com/proofkit/specifications  
**Questions:** team@proofkit.io

Upload a CSV, get a certificate. See if it works for your use case.

---

*Built by a team frustrated with manual QC processes in manufacturing. We're solving this for everyone.*

**Stack:** FastAPI, Pydantic, Pandas, ReportLab, PostgreSQL  
**Hosted:** EU (GDPR compliant)  
**Compliance:** SOC 2 Type I in progress