# Webinar Demo Scripts
## Comprehensive Presenter Guidelines for Both Sessions

---

## Pre-Demo Setup Checklist

### Technical Requirements
- [ ] ProofKit website loaded and tested
- [ ] Sample CSV files ready (both powder coat and autoclave)
- [ ] Spec JSON templates copied to clipboard
- [ ] Screen recording software active (for YouTube upload)
- [ ] Backup browser window open
- [ ] Zoom webinar features tested (screen share, polls, Q&A)

### Files to Have Ready
1. **powder_coat_cure_successful_180c_10min_pass.csv** (from examples/)
2. **Autoclave cycle CSV** with temperature and pressure data
3. **Qualicoat spec template** (pre-filled JSON)
4. **CFR 11 autoclave spec template** (pre-filled JSON)
5. **Previous certificate examples** for reference

---

## Demo Script 1: Qualicoat Webinar

### Opening Hook (30 seconds)
**Script:** "Good morning everyone. Before we start, I have a quick question - and please use the chat to respond. How many of you have spent more than an hour preparing powder coat documentation for a single audit? I see lots of 'yes' responses... and a few 'try 3 hours' comments. That pain ends today."

### Problem Setup (2 minutes)
**Script:** "Let me show you what most quality managers are dealing with." [Screen share Excel spreadsheet]

"Here's a typical Excel powder coat log. Looks professional, right? But watch what happens when an auditor digs deeper:
- These temperature calculations? Manual formulas that could be wrong
- The PASS/FAIL decision? Based on someone's interpretation 
- The hold time calculation? Easy to manipulate after the fact
- The sensor uncertainty? Often completely ignored

I've personally seen three companies fail Qualicoat audits because of Excel calculation errors. Let's fix this."

### Live Demo - Step by Step (8 minutes)

#### Step 1: Upload CSV (1 minute)
**Script:** "I'm going to use real powder coat data from a 180°C cure cycle. This CSV came straight from a Fluke data logger - no preprocessing, no cleanup."

**Actions:**
1. Navigate to ProofKit homepage
2. Click "Upload CSV" 
3. Select powder_coat_cure_successful_180c_10min_pass.csv
4. Show file upload progress

**Script continues:** "Notice I'm not doing any Excel manipulation here. Raw logger data, exactly as it came from the oven."

#### Step 2: Spec Input (2 minutes)
**Script:** "Now for the critical part - the specification. This is where most Excel users get into trouble."

**Paste this JSON template:**
```json
{
  "target_temperature": 180,
  "temperature_tolerance": 5,
  "min_hold_time_minutes": 10,
  "sensor_uncertainty": 2,
  "hysteresis": 2,
  "ramp_rate_max": 50,
  "spec_name": "Standard Qualicoat Powder Coat Cure",
  "industry": "powder_coating"
}
```

**Script continues:** "See this sensor_uncertainty field? This is the game-changer. ProofKit automatically calculates the conservative threshold at 182°C - that's 180°C target plus 2°C sensor uncertainty. Most Excel users miss this completely."

#### Step 3: Processing (1 minute)
**Script:** "Now watch the magic happen." [Click Generate Certificate]

**During processing:** "ProofKit is now:
- Validating the CSV data quality
- Calculating the conservative threshold with hysteresis
- Finding the longest continuous hold above threshold
- Computing the maximum ramp rate
- Generating tamper-proof hashes
- Creating the compliance certificate"

#### Step 4: Results Review (4 minutes)
**Script:** "And we have a PASS! Let me walk you through what makes this audit-proof."

**Show certificate sections:**

1. **PASS/FAIL Banner:** "Clear visual - no ambiguity for auditors"
2. **Spec Compliance Box:** "Every parameter verified and documented"
3. **Temperature Plot:** "Notice the red threshold line at 182°C, not 180°C. This conservative approach prevents false passes."
4. **Hold Time:** "ProofKit found 12.3 minutes of continuous hold - well above our 10-minute requirement"
5. **QR Code:** "This is the audit secret weapon. Any auditor can scan this and independently verify our results."

**Demo the QR code:** "Let me show you what happens when an auditor scans this..." [Navigate to verification URL]

"They get the original data, the processing methodology, and can re-run the calculations themselves. No trust required."

### Transition to Benefits (1 minute)
**Script:** "So what did we just accomplish? In 30 seconds, we went from raw data logger CSV to audit-proof certificate. No formulas to debug, no calculations to verify, no human error possible."

---

## Demo Script 2: CFR 11 Autoclave Webinar

### Opening Hook (30 seconds)
**Script:** "Welcome everyone. Quick poll before we dive in - how many of you would feel 100% confident if FDA showed up tomorrow to inspect your autoclave validation records? I see mostly silence in the chat... exactly. That changes today."

### Urgency Building (2 minutes)
**Script:** "Let me share something that should keep you awake at night." [Show redacted FDA 483 citation]

"This is from a real FDA inspection last year. Quote: 'Temperature mapping data lacks integrity controls and shows evidence of post-processing modification.' Result? $850,000 in remediation costs and a six-month manufacturing hold.

The problem? Excel-based autoclave logs with manual Fo calculations. Sound familiar?"

### Live Demo - CFR 11 Focus (8 minutes)

#### Step 1: The Critical Upload (1 minute)
**Script:** "I'm using actual autoclave cycle data - temperature and pressure from a 121°C sterilization cycle. This data is completely unmodified from the logger."

**Actions:**
1. Navigate to ProofKit
2. Upload autoclave CSV file
3. Show raw data preview

**Script continues:** "Notice both temperature AND pressure data. CFR 11 requires pressure correlation to validate steam quality. Excel users often ignore this."

#### Step 2: FDA Spec Template (2 minutes)
**Script:** "Here's where CFR 11 compliance gets technical:"

**Paste autoclave spec:**
```json
{
  "target_temperature": 121,
  "temperature_tolerance": 2,
  "min_fo_value": 12,
  "pressure_min_kpa": 103.4,
  "hold_time_minutes": 15,
  "z_value": 10,
  "spec_name": "FDA CFR 11 Moist Heat Sterilization",
  "industry": "pharmaceutical"
}
```

**Script continues:** "The Fo value requirement - 12 minutes minimum - represents a 6-log reduction in bioburden. The Z-value of 10°C is FDA standard for moist heat. These aren't suggestions - they're regulatory requirements."

#### Step 3: Real-time Processing (1 minute)
**Script:** "Watch ProofKit calculate the Fo integral in real-time:" [Click Generate]

**During processing:** "ProofKit is computing the time-temperature integral using the FDA-standard formula:
Fo = Σ(10^((T-121)/10) × Δt)

It's also validating pressure correlation throughout the entire cycle. Any pressure drop would trigger an automatic FAIL."

#### Step 4: CFR 11 Certificate Analysis (4 minutes)
**Script:** "Here's your CFR 11 compliant certificate. Let me show you why this passes FDA inspection:"

**Review each element:**

1. **Process Parameters:** "Complete temperature and pressure profiles documented"
2. **Fo Calculation:** "Our result: 18.7 minutes - well above the 12-minute requirement"
3. **Pressure Validation:** "Pressure never dropped below 103.4 kPa - confirming steam saturation"
4. **Digital Signature:** "SHA-256 hash prevents any post-processing modification"
5. **Audit Trail:** "Complete processing methodology documented and reproducible"

**Demo verification:** "Most importantly - the verification capability. When FDA inspectors scan this QR code..." [Navigate to verification URL]

"They can independently verify the Fo calculation using the original data. No trust required, no proprietary software needed. Pure mathematical validation."

### CFR 11 Compliance Emphasis (1 minute)
**Script:** "What we just created satisfies every CFR 11 requirement:
- Electronic records? ✓ Tamper-evident with cryptographic hashes
- Audit trails? ✓ Complete processing methodology documented
- Data integrity? ✓ ALCOA+ principles built-in
- System validation? ✓ Mathematical algorithms are disclosed and standardized"

---

## Q&A Handling Scripts

### Common Questions & Responses

#### "How do I validate ProofKit for our quality system?"
**Response:** "Great question. ProofKit provides IQ/OQ/PQ templates specifically for regulated environments. The algorithms are open-source and mathematically verifiable - there's no black box to validate. We also provide FDA inspection support documentation."

#### "What if our data logger uses different formats?"
**Response:** "ProofKit accepts any time-series CSV format. We've tested with Omega, Onset, Lascar, Testo, Fluke, and 20+ other logger brands. If you send me your CSV format after the webinar, I can confirm compatibility within 24 hours."

#### "Can this integrate with our existing LIMS?"
**Response:** "ProofKit generates API-friendly JSON results that can integrate with any LIMS system. We also provide batch processing capabilities for high-volume environments. Happy to discuss your specific integration needs offline."

#### "What about data security and storage?"
**Response:** "ProofKit doesn't permanently store your data. Processing happens in memory, certificates are generated, and data is deleted. For audit purposes, you control the evidence packages locally. We're SOC 2 Type II compliant for the processing infrastructure."

### Demo Troubleshooting

#### If Upload Fails:
**Script:** "Looks like we have a connectivity issue. This is exactly why I have backup screenshots ready..." [Switch to prepared certificate examples]

#### If Processing Takes Too Long:
**Script:** "While this processes, let me show you a certificate we prepared earlier..." [Navigate to example certificate]

#### If Verification Link Fails:
**Script:** "The verification system is getting heavy traffic from webinar attendees. Let me show you the verification process using this example..." [Use pre-loaded verification page]

---

## Closing Scripts

### Qualicoat Webinar Close
**Script:** "To recap what we've accomplished: We took raw logger data and generated an audit-proof Qualicoat certificate in 30 seconds. No Excel formulas, no calculation errors, no auditor questions about data integrity.

Your next steps:
1. Download the sample files from the chat links
2. Try your first 3 certificates free at proofkit.com
3. Schedule a 1:1 call if you process high volumes

Remember - every manual Excel calculation is an audit risk. Questions?"

### CFR 11 Webinar Close
**Script:** "We just demonstrated CFR 11 compliant autoclave validation in 30 seconds. No manual Fo calculations, no audit trail gaps, no inspector concerns about data integrity.

For pharmaceutical and medical device companies, this isn't just about efficiency - it's about regulatory survival. 

Your action items:
1. Test ProofKit with your autoclave data - 3 free certificates
2. Download the CFR 11 compliance checklist
3. Schedule validation support if you're in a regulated environment

FDA inspections don't wait for convenient timing. Questions about implementation?"

---

## Post-Demo Follow-up Actions

### Immediate (Within 5 minutes of webinar end):
1. Send chat message with recording link
2. Email slide deck PDF to all attendees
3. Provide sample CSV download links
4. Share free trial signup URL

### Within 24 Hours:
1. Upload recording to YouTube with SEO-optimized title
2. Send follow-up email with additional resources
3. Create personalized follow-up for enterprise inquiries
4. Update lead scoring based on engagement

### Within 48 Hours:
1. Analyze Q&A themes for content gaps
2. Create FAQ additions based on questions
3. Update demo scripts based on timing issues
4. Schedule follow-up calls for qualified leads

---

## Demo File Requirements

### Required CSV Files:
- `powder_coat_cure_successful_180c_10min_pass.csv`
- `autoclave_cycle_121c_15min_pass.csv` (create if needed)
- `powder_coat_cure_insufficient_hold_time_fail.csv` (for failure demo)

### Required Spec Templates:
- Qualicoat powder coat spec (JSON)
- CFR 11 autoclave spec (JSON)
- Alternative specs for Q&A scenarios

### Backup Materials:
- Pre-generated certificates for demo failures
- Screenshot alternatives for connectivity issues
- Verification page examples for backup demo