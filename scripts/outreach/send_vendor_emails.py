#!/usr/bin/env python3
"""
Send initial vendor partnership outreach emails via Postmark.

Usage:
  POSTMARK_API_TOKEN=... EMAIL_FROM="John <john@proofkit.net>" \
  python3 scripts/outreach/send_vendor_emails.py --dry-run

Options:
  --dry-run            Print emails without sending (default)
  --limit N            Limit number of emails to send
  --only HIGH|MEDIUM   Filter by Partnership_Priority
  --resume COMPANY     Resume after a given company name
"""

import csv
import json
import os
import sys
import time
import argparse
import random
from pathlib import Path
from typing import Dict, Any, Optional

import httpx


def render_template(template_md: str, replacements: Dict[str, str]) -> str:
    body = template_md
    for key, value in replacements.items():
        body = body.replace(f"[{key}]", value)
    return body


def extract_subject_and_body(rendered: str) -> Dict[str, str]:
    lines = [l.rstrip() for l in rendered.splitlines()]
    subject = "ProofKit Partnership Opportunity"
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith("**Subject**:"):
            subject = line.split(":", 1)[1].strip()
            continue
        # Drop template artifacts
        if line.strip().lower().startswith("**email body**"):
            continue
        body_lines.append(line)
    # Strip markdown headings and separators
    filtered = []
    skip_markers = {"# ", "## ", "---"}
    for l in body_lines:
        if any(l.startswith(m) for m in skip_markers):
            continue
        filtered.append(l)
    return {"subject": subject, "body": "\n".join(filtered).strip()}


def send_postmark(to_email: str, subject: str, html_body: str, text_body: str):
    token = os.getenv("POSTMARK_API_TOKEN") or os.getenv("POSTMARK_TOKEN")
    from_email = os.getenv("EMAIL_FROM", "John <john@proofkit.net>")
    reply_to = os.getenv("REPLY_TO", "john@proofkit.net")
    message_stream = os.getenv("POSTMARK_MESSAGE_STREAM", "broadcast")
    if not token:
        print("ERROR: POSTMARK_API_TOKEN not set")
        return False, 0, "missing token"
    url = "https://api.postmarkapp.com/email"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": token,
    }
    data = {
        "From": from_email,
        "To": to_email,
        "ReplyTo": reply_to,
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": message_stream,
        "Headers": [
            {"Name": "List-Unsubscribe", "Value": "<mailto:john@proofkit.net?subject=unsubscribe>"}
        ],
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        print(f"✅ Sent: {to_email}")
        return True, resp.status_code, resp.text
    print(f"❌ {to_email} -> {resp.status_code} {resp.text}")
    return False, resp.status_code, resp.text


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    group.add_argument("--send", dest="dry_run", action="store_false", help="Actually send emails via Postmark")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--only", type=str, choices=["High", "Medium", "Low"], default=None)
    parser.add_argument("--resume", type=str, default=None)
    parser.add_argument("--csv", type=str, default=None, help="Path to CSV of targets (defaults to vendor-list.csv)")
    parser.add_argument("--pace-seconds", type=float, default=12.0, help="Base delay between sends to avoid ISP blocks")
    parser.add_argument("--jitter-seconds", type=float, default=6.0, help="Random jitter added to base delay")
    parser.add_argument("--sent-log", type=str, default=os.getenv("SENT_LOG_PATH", "build/outreach/sent_log.csv"), help="Path to CSV log of sent emails to avoid duplicates")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    csv_path = Path(args.csv) if args.csv else (root / "marketing" / "partnerships" / "vendor-list.csv")
    tmpl_path = root / "marketing" / "outreach" / "vendor-email-templates.md"
    if not csv_path.exists() or not tmpl_path.exists():
        print("ERROR: Required files missing")
        return 1

    template_md = tmpl_path.read_text(encoding="utf-8")
    # Single-sentence value proposition used across all variants
    one_liner = (
        "We're ProofKit — we turn temperature logs (CSV/PDF) into inspector-ready, tamper-evident PDF/A-3 certificates in ~30 seconds."
    )

    # Load sent history for deduplication
    sent_log_path = Path(args.sent_log)
    sent_log_path.parent.mkdir(parents=True, exist_ok=True)
    seen_emails = set()
    seen_companies = set()
    if sent_log_path.exists():
        try:
            with open(sent_log_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    e = (r.get("To") or "").strip().lower()
                    if e:
                        seen_emails.add(e)
                    c = (r.get("Company") or "").strip().lower()
                    if c:
                        seen_companies.add(c)
        except Exception:
            pass
    # Use Template A block, then compress to a short, high-conversion opener
    start = template_md.find("## Template A")
    end = template_md.find("---", start + 1)
    template_a_full = template_md[start:end].strip() if start != -1 and end != -1 else template_md
    # Short, interesting, no phone, tight CTA; we still allow placeholders
    template_a = (
        "**Subject**: Partnering with [VENDOR]: instant, audit-ready certificates for your customers\n\n"
        "**Email Body**:\n\n"
        "Hi [CONTACT_NAME],\n\n"
        "First—kudos on [VENDOR]'s work. We’ve seen customers praise your reliability.\n\n"
        f"{one_liner}\n\n"
        "Your customers get inspector-ready docs without changing their workflow — great for CFR 21, HACCP, ASTM. There’s no downside: no code changes, no impact on your margins.\n\n"
        "Idea: a co-branded [VENDOR] template your team can share. Low lift for you, big value for users.\n\n"
        "Reply YES and I’ll send a [VENDOR]-branded sample today (or build it from a public CSV you share). Prefer a quick chat? Propose a 15‑min slot and I’ll make it work.\n\n"
        "Best,\n[YOUR_NAME] — ProofKit (proofkit.net)\n"
    )

    sent = 0
    resume_reached = args.resume is None
    website_url = os.getenv("WEBSITE_URL", "https://www.proofkit.net")
    calendly_url = os.getenv("CALENDLY_URL", "https://calendly.com/atillatkulu/30min")
    # Subtle scarcity/urgency controls
    try:
        slots_total = int(os.getenv("PARTNER_SLOTS_TOTAL", "5"))
    except ValueError:
        slots_total = 5
    try:
        slots_in_build = int(os.getenv("PARTNER_SLOTS_TAKEN", "2"))
    except ValueError:
        slots_in_build = 2

    # Optional vendor-specific personalization hooks
    vendor_ps: Dict[str, str] = {
        "Monnit": "P.S. I noticed your ALTA sensor platform and partner ecosystem — we can auto-generate PDF/A-3 certificates from Monnit temperature streams to help your customers close audit loops.",
        "E+E Elektronik": "P.S. Your accredited calibration lab and EE series fit well with our CFR 21 Part 11-ready outputs — happy to showcase an integrated report.",
        "Berlinger": "P.S. We work with VFC/UL cold-chain logs similar to Fridge-tag and Q-tag — we can ingest PDFs and generate validated certificate bundles.",
        "Sensitech": "P.S. We work with VFC/UL cold-chain logs similar to Fridge-tag and Q-tag — we can ingest PDFs and generate validated certificate bundles.",
        "TempSen": "P.S. Your Tempod series (incl. –90°C dry ice) aligns with our pharma templates — we can produce site-ready PDF/A-3 certificates.",
        "Gemini": "P.S. Tinytag deployments in pharma/food map neatly to our industry templates — we can provide co-branded certificates for your end-users.",
        "T&D": "P.S. TR7/TR-71/75 data and WebStorage exports drop straight into our certificate pipeline — we can show a full audit-ready bundle.",
        "Elitech": "P.S. Your iCold platform and RC series logs integrate well — we can generate compliant PDF/A-3 reports for audits in seconds.",
    }

    # Deep personalization: compliments, pain, WIIFM, proof, offer (15%), CTA
    vendor_profiles: Dict[str, Dict[str, str]] = {
        "Lascar": {
            "compliment": "Impressive momentum with EasyLog Cloud and the EL-IOT range — love the focus on simple, scalable monitoring.",
            "pain": "Your SMB and healthcare customers often need inspector-ready documentation without adding software complexity.",
            "wiifm": "We co-brand instant PDF/A-3 certificates from their CSVs, so your team drives more hardware retention and upsell without engineering lift.",
            "proof": "We process 3,000+ certificates weekly across CFR 21, HACCP, ASTM — zero learning curve for end users.",
            "offer": "We pay you 15% of certificate fees generated via Lascar‑branded templates; your product pricing and margins stay untouched. We handle integration and support.",
        },
        "Rotronic": {
            "compliment": "Rotronic RMS + DwyerOmega portfolio is best-in-class for GMP environments.",
            "pain": "QA teams still export data and manually build validation packets for audits, which burns time and introduces risk.",
            "wiifm": "We auto-generate tamper-evident PDF/A-3 certificates from exports — co-branded — so customers close audit loops instantly.",
            "proof": "Used across pharma and cleanrooms; JSON + PNG + PDF bundles with SHA-256 verification.",
            "offer": "We pay your team 15% of certificate fees from Rotronic‑branded templates; your existing product margins remain unchanged. We’ll stand up a Rotronic-branded spec template in days.",
        },
        "MadgeTech": {
            "compliment": "Strong life-science footprint and lyophilization depth — your app notes are excellent.",
            "pain": "Labs need fast, compliant documentation from logger runs without bespoke scripting.",
            "wiifm": "Co-branded, one-click certificates from CSV/PDF outputs — fewer tickets, more stickiness for your devices.",
            "proof": "Supports dry-ice and extreme ranges; deterministic processing ensures repeatable results.",
            "offer": "We pay you 15% of certificate fees tied to MadgeTech‑branded templates; your hardware/service pricing is unaffected.",
        },
        "Sensaphone": {
            "compliment": "Your Sentinel lineup nails 24/7 monitoring for cold storage and facilities.",
            "pain": "Ops teams still assemble compliance packets by hand for inspectors and clients.",
            "wiifm": "We transform their exported logs into inspector-ready PDF/A-3 in ~30 seconds, co-branded with Sensaphone.",
            "proof": "Common specs: HACCP 135–70–41, CFR 21, ASTM — with verification JSON and plots.",
            "offer": "We pay you 15% of certificate fees from Sensaphone‑branded flows; rollout without code changes on your side.",
        },
        "CAS DataLoggers": {
            "compliment": "Great distributor breadth — your customers span pharma, industrial, environmental.",
            "pain": "End users ask resellers for audit-grade reports that take hours to compile.",
            "wiifm": "Offer a CAS-branded certification flow — new margin with zero implementation.",
            "proof": "3,000+ weekly certificates; tamper-evident, PDF/A-3 standard.",
            "offer": "Reseller‑friendly payout: we pay 15% of certificate fees on CAS‑branded templates; no change to your margins. We manage support.",
        },
        "Elitech": {
            "compliment": "Elitech’s iCold cloud and wide logger range are strong for food and life science cold chains.",
            "pain": "SMBs and enterprise customers need fast, validated certificates from their runs for audits and tenders.",
            "wiifm": "Co-branded PDF/A-3 output from Elitech exports increases hardware value and reduces churn.",
            "proof": "Supports real-time, WiFi/4G and USB data; we generate JSON+PDF bundles with integrity hashes.",
            "offer": "We pay you 15% of certificate fees via Elitech‑branded templates; your pricing/margins remain as is. Sample this week.",
        },
        "Gemini": {
            "compliment": "Tinytag’s reliability and museum/healthcare presence are well regarded.",
            "pain": "Conservation and healthcare teams need audit-ready docs without extra software.",
            "wiifm": "Co-branded, single-click certification from Tinytag exports — value-add that retains accounts.",
            "proof": "Common frameworks: HACCP, CFR 21; deterministic output ensures consistent audits.",
            "offer": "We pay your team 15% of certificate fees on Tinytag‑branded templates; your product margins are untouched. We maintain the templates.",
        },
        "E+E": {
            "compliment": "Accredited calibration and EE series quality stand out.",
            "pain": "Pharma/HVAC customers still hand-craft validation packets from exports.",
            "wiifm": "Co-branded certificates from EE-series exports; faster audits, happier customers.",
            "proof": "Thousands of weekly certificates across regulated industries.",
            "offer": "We pay 15% of certificate fees for E+E‑branded templates; low‑lift rollout and no impact on your product margins.",
        },
        "Monnit": {
            "compliment": "ALTA ecosystem and partner program are excellent.",
            "pain": "End users struggle turning sensor data into compliant documentation.",
            "wiifm": "Monnit-branded instant certificates from CSV exports — boosts retention and expansion.",
            "proof": "PDF/A-3 + JSON + plots; CFR 21, HACCP, ASTM supported.",
            "offer": "We pay you 15% of certificate fees on Monnit‑branded templates; we handle templates and support. Your pricing stays your own.",
        },
        "Sensitech": {
            "compliment": "Fridge-tag/Q-tag lineage and SmartView coverage are industry benchmarks.",
            "pain": "Global health and pharma teams need standardized, audit-proof reports quickly.",
            "wiifm": "Sensitech-branded certificates from device outputs; faster audits, more device stickiness.",
            "proof": "Used across cold chain; deterministic processing and verification.",
            "offer": "We pay 15% of certificate fees on Sensitech‑branded templates; rapid template delivery and no change to your margins.",
        },
    }
    # Extend with additional vendors requiring clarified 15% payout language
    vendor_profiles.update({
        "Peli BioThermal": {
            "compliment": "Your Crēdo Vault and global refurbishment network are a strong signal of quality and sustainability across pharma logistics.",
            "pain": "Sponsors and 3PLs still ask for inspector‑ready certificate packs for lanes and shipments, which teams often assemble manually.",
            "wiifm": "Peli‑co‑branded, instant PDF/A‑3 certificates from shipment/monitoring exports — added value without adding ops burden.",
            "proof": "Deterministic bundles (PDF/A‑3 + JSON + plots) with integrity hashes; fits GxP and CFR 21 expectations.",
            "offer": "We pay 15% of certificate fees on Peli‑branded templates; your pricing/margins remain untouched. We build and maintain the templates.",
        },
        "Onset": {
            "compliment": "HOBO’s credibility in research and environmental monitoring — including CFR Part 11 options — is best‑in‑class.",
            "pain": "Many customers still export HOBOware data and hand‑craft packets for audits and buyers.",
            "wiifm": "Onset‑branded, one‑click PDF/A‑3 certificates from HOBO exports — fewer tickets, more device stickiness.",
            "proof": "Thousands of compliant bundles weekly across HACCP/CFR 21/ASTM with integrity verification.",
            "offer": "We pay 15% of certificate fees on Onset‑branded templates; zero code changes for your team.",
        },
        "Timestrip": {
            "compliment": "Your simple, visual time/temperature indicators are loved by pharma and food teams for clarity at the edge.",
            "pain": "Buyers still request certificate‑style documentation to accompany indicator outcomes for inspections and tenders.",
            "wiifm": "Timestrip‑branded, instant PDF/A‑3 certificates from companion logger/monitor exports — a clean add‑on to indicators.",
            "proof": "We generate standardized, tamper‑evident outputs (PDF/A‑3 + JSON) aligned to common frameworks.",
            "offer": "We pay 15% of certificate fees on Timestrip‑branded templates; no impact on your margins.",
        },
        "Logmore": {
            "compliment": "Dynamic QR logging and EU cloud are a clever approach — dry‑ice capable with rapid scan‑to‑view is elegant.",
            "pain": "Shippers still need inspector‑ready certificate bundles from runs, and many assemble these by hand today.",
            "wiifm": "Logmore‑branded, instant certificate bundles from exports — improved customer experience without engineering lift.",
            "proof": "Deterministic outputs include PDF/A‑3, plots and machine‑readable JSON; consistent across lanes.",
            "offer": "We pay 15% of certificate fees on Logmore‑branded templates; your pricing stays yours. We handle build and support.",
        },
        "Envirotainer": {
            "compliment": "Your RelEye portfolio and global station network set a high bar for pharma logistics visibility and reliability.",
            "pain": "Sponsors still ask partners for inspector‑ready certificate packs from route validations and shipments, which teams assemble manually.",
            "wiifm": "Envirotainer‑co‑branded, instant PDF/A‑3 certificates from shipment/device exports — value for sponsors and partners without new ops overhead.",
            "proof": "We produce tamper‑evident bundles (PDF/A‑3 + JSON + plots) across CFR 21/GxP with deterministic outputs and hash verification.",
            "offer": "We pay 15% of certificate fees on Envirotainer‑branded templates; no change to your pricing/margins. We build and maintain templates and support sponsors globally.",
        },
        "Cold Chain Technologies": {
            "compliment": "CCT’s sustainable portfolio and Tower acquisition make a compelling end‑to‑end offering across pallets, parcels and covers.",
            "pain": "Shippers and 3PLs still need certificate‑style proof of temperature compliance for audits and tenders, often compiled by hand.",
            "wiifm": "CCT‑branded, one‑click PDF/A‑3 certificates from monitoring and packout data reduce support load and create attach revenue.",
            "proof": "Thousands of weekly certificates across HACCP/CFR 21/ASTM with integrity checks; works with passive/active flows.",
            "offer": "We pay your team 15% of certificate fees on CCT‑branded templates; your margins stay intact. We handle build, rollout and support.",
        },
        "Tower Cold Chain": {
            "compliment": "Your reusable passive containers and sub‑pallet Flexi Fit line are well regarded for low excursion rates and sustainability.",
            "pain": "Sponsors still request validated, inspector‑ready documentation tied to shipments and lanes, which teams assemble manually.",
            "wiifm": "Tower‑branded instant certificates from packout and monitoring data — stronger sponsor value without adding complexity.",
            "proof": "PDF/A‑3 + JSON bundles with SHA‑256 verification; consistent across lanes and seasons.",
            "offer": "We pay 15% of certificate fees on Tower‑branded templates; zero impact on your pricing. We implement and maintain templates globally.",
        },
        "Biocair": {
            "compliment": "Biocair’s CGT focus and 99.9% OTIF with global monitoring is impressive — strong patient‑first execution.",
            "pain": "CGT stakeholders still need standardized certificate packs from monitored runs and validations for audits and QMS records.",
            "wiifm": "Biocair‑branded, single‑click certificate bundles from CGT shipments — better client experience and a new attach without extra effort.",
            "proof": "Deterministic outputs (PDF/A‑3 + telemetry JSON + plots); fits QMS and client audits.",
            "offer": "We pay 15% of certificate fees on Biocair‑branded templates; your service pricing remains unchanged. We handle integration and support.",
        },
        "Cold Chain LLC": {
            "compliment": "Your durable cold chain products and industrial grade build are valued by regulated and industrial users alike.",
            "pain": "End customers still need certificate‑style proof for QA and buyers — often built manually from logger data.",
            "wiifm": "Cold Chain LLC‑branded, instant certificates from logger exports — higher customer satisfaction and support reduction.",
            "proof": "Thousands of compliant bundles weekly across industries with verification payloads.",
            "offer": "We pay 15% of certificate fees on your branded templates; no change to your margins. We manage build and support end to end.",
        },
        "Dickson": {
            "compliment": "DicksonOne and your Mapping Suite are strong — love how you simplify compliance for hospitals and pharma.",
            "pain": "Teams still export and hand‑assemble audit packets from DicksonOne when inspectors or clients ask for ‘certificate‑style’ proof.",
            "wiifm": "Dickson‑branded instant PDF/A‑3 certificates from exports reduce support load and create a new attach for services.",
            "proof": "We generate thousands of compliant bundles weekly (PDF/A‑3 + JSON + plots) across FDA 21 CFR Part 11, GxP, HACCP.",
            "offer": "We pay you 15% of certificate fees tied to Dickson‑branded templates; your device/software pricing stays unchanged. We handle integration and support.",
        },
        "DeltaTrak": {
            "compliment": "FlashTrak and your real‑time loggers are widely trusted in life sciences and food logistics — great ecosystem.",
            "pain": "End customers still need inspector‑ready certificates from FlashTrak data, and many build them manually under time pressure.",
            "wiifm": "DeltaTrak‑branded, single‑click PDF/A‑3 certificates from FlashTrak exports — faster audits, higher device stickiness.",
            "proof": "We support dry ice and multi‑sensor runs; outputs are tamper‑evident with hash verification and structured JSON.",
            "offer": "We pay 15% of certificate fees on DeltaTrak‑branded templates; no impact to your margins. We build and maintain the templates.",
        },
        "Rees Scientific": {
            "compliment": "Your Centron Presidio platform plus ISO/IEC 17025 accreditation and the breadth of EMS services (design, installation, validation, calibration) make you a reference in regulated monitoring.",
            "pain": "Even with a strong EMS, QA teams are still asked for inspector‑ready, standardized certificate packets for CAP/TJC/FDA and client audits — often assembled manually from exports.",
            "wiifm": "Rees‑branded, single‑click PDF/A‑3 certificates from EMS/log exports reduce support burden, speed audits, and create a clean attach for services — with no changes to your pricing or product.",
            "proof": "Thousands of compliant bundles weekly across hospital, pharma, cleanroom and CGT; outputs include PDF/A‑3, plots and machine‑readable JSON with integrity hashes.",
            "offer": "We pay 15% of certificate fees on Rees‑branded templates; your margins remain untouched. We build, validate, and maintain the templates and provide monthly usage + payout reports.",
        },
        "DoKaSch Temperature Solutions": {
            "compliment": "Opticooler RAP/RKN’s reliability and your expanding global footprint (incl. UAE depot near DWC to support Emirates/Etihad lanes) are best‑in‑class for high‑value pharma.",
            "pain": "Sponsors and 3PLs still request validated, inspector‑ready document bundles tied to lane validations and shipments — many teams assemble these manually under time pressure.",
            "wiifm": "DoKaSch‑co‑branded, instant PDF/A‑3 certificate bundles from shipment/monitoring exports — higher sponsor confidence and a value‑add partners can share without new ops overhead.",
            "proof": "Deterministic outputs (PDF/A‑3 + telemetry JSON + plots) with hash verification; consistent across lanes, seasons and networks; aligns with GxP/CFR 21 expectations.",
            "offer": "We pay 15% of certificate fees on DoKaSch‑branded templates; your container pricing and margins remain unchanged. We handle template build, rollout, and support globally.",
        },
        "ELPRO": {
            "compliment": "ELPRO’s LIBERO Cx/Gx and liberoMANAGER 3.0 are best‑in‑class for regulated cold chain — impressive upgrade cadence.",
            "pain": "Quality teams still compile certificate packages outside liberoMANAGER for tenders and audits, which drains time.",
            "wiifm": "ELPRO‑branded, instant certificate bundles from LIBERO exports — a value‑add your partners can share with clients.",
            "proof": "Pharma and biotech users rely on our deterministic processing; outputs include PDF/A‑3, plots and machine‑readable JSON.",
            "offer": "We pay 15% of certificate fees on ELPRO‑branded templates; your pricing/margins remain untouched. We handle integration and support.",
        },
        "Comark": {
            "compliment": "Decades of trust in food and healthcare with Diligence 600 and UKAS/21 CFR aligned workflows.",
            "pain": "Teams still spend hours exporting data and assembling audit packets for regulators and clients.",
            "wiifm": "Comark‑branded, one‑click PDF/A‑3 certificates from exports reduce support load and create new attach revenue.",
            "proof": "Used across HACCP, pharma, and labs; bundles include JSON + plots + SHA‑256 verification.",
            "offer": "We pay you 15% of certificate fees generated via Comark‑branded templates; your margins on instruments/services remain untouched.",
        },
        "Temprecord": {
            "compliment": "ISO/IEC 17025 accreditation and TAD Cloud are impressive — strong credibility for regulated use.",
            "pain": "Customers need inspector‑ready documentation quickly without extra software complexity.",
            "wiifm": "Temprecord‑branded, instant PDF/A‑3 certificates from TRW/TAD exports increase retention and expansion.",
            "proof": "Thousands of certificates weekly across CFR 21/HACCP/ASTM with deterministic outputs.",
            "offer": "We pay 15% of certificate fees on Temprecord‑branded templates; no impact on your hardware or service margins.",
        },
        "LogTag": {
            "compliment": "Global footprint and WHO PQS presence — excellent for pharma and food logistics.",
            "pain": "End users struggle to build audit‑grade reports from exports under time pressure.",
            "wiifm": "LogTag‑branded, single‑click certificates from Analyzer exports — more value with zero engineering.",
            "proof": "PDF/A‑3 + JSON + plots, verified with hashes; consistent outputs for audits.",
            "offer": "We pay your team 15% of certificate fees via LogTag‑branded templates; your product pricing/margins stay unchanged.",
        },
        "Ellenex": {
            "compliment": "Strong industrial IoT portfolio across LoRaWAN/LTE‑M with credible deployments.",
            "pain": "Industrial customers still require signed, tamper‑evident reports for QA and tenders.",
            "wiifm": "Ellenex‑branded certificate generation from exported runs — proof for audits and bids, no extra ops burden.",
            "proof": "Cross‑industry usage with verifiable outputs (PDF/A‑3 + JSON).",
            "offer": "We pay 15% of certificate fees from Ellenex‑branded templates; no change to device or services margins.",
        },
        "Nortech": {
            "compliment": "60+ years in cold shipping — trusted brand in gel packs and packaging.",
            "pain": "Shippers need validation packets for QA and regulatory audits tied to lanes and shipments.",
            "wiifm": "Co‑branded, lane‑specific certificates from logger outputs to improve win rates and reduce support.",
            "proof": "Large weekly certificate volume across HACCP/GxP with integrity checks.",
            "offer": "We pay your team 15% of certificate fees on Nortech‑branded templates; your product margins stay intact.",
        },
        "Creative Packaging": {
            "compliment": "National coverage with cold chain liners/EPS is compelling for meal kits and pharma.",
            "pain": "Customers ask for audit‑ready docs per shipment to satisfy buyers and inspectors.",
            "wiifm": "Creative Packaging‑branded certificates from exported runs — a new revenue stream without added workload.",
            "proof": "Standardized outputs, PDF/A‑3 + verification payloads, consistent for audits.",
            "offer": "We pay 15% of certificate fees on Creative Packaging‑branded templates; no impact on your product margins.",
        },
    })
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            priority = row.get("Partnership_Priority", "").strip()
            if args.only and priority != args.only:
                continue
            company = row.get("Company", "").strip()
            if not resume_reached:
                if company == args.resume:
                    resume_reached = True
                else:
                    continue

            to_email = row.get("Contact_Email", "").strip()
            if to_email.lower() in seen_emails:
                # Skip already contacted addresses
                continue
            if company.strip().lower() in seen_companies:
                # Skip already contacted company (avoid re-contact via other aliases)
                continue
            contact_name = row.get("Contact_Name", "").strip() or "Team"
            website = row.get("Website", "").strip()

            replacements = {
                "CONTACT_NAME": contact_name,
                "VENDOR": company,
                "YOUR_NAME": "John",
                "EMAIL": "john@proofkit.net",
                "PHONE": row.get("Phone", ""),
            }
            # Build personalized email if we have a profile; otherwise fallback to concise template
            profile_key = None
            for key in vendor_profiles.keys():
                if key.lower() in company.lower():
                    profile_key = key
                    break

            if profile_key:
                vp = vendor_profiles[profile_key]
                subject = f"{company}: reserve a pilot slot for co‑branded certificates (we pay 15%)"
                # Clear, concise partnership explainer appended to vendor-specific offer
                terms_clarifier = (
                    "What you get: 15% of certificate fees from your co-branded templates, paid monthly; co-branded templates/page; usage report + payout; optional API/S3 delivery. "
                    "What we handle: build/maintain templates, onboarding, billing, support, compliance. "
                    "No impact on your pricing/margins; end users pay ProofKit per-certificate. Pilot: 1–2 templates live in ~7 days."
                )
                no_downside = (
                    "No downside: zero code changes, zero impact on your margins. Users keep using your devices — they simply get clear, inspector‑ready certificates instead of raw CSVs."
                )
                hold_until = time.strftime("%b %d", time.gmtime(time.time() + 7 * 86400))
                scarcity_line = (
                    f"We’re opening {slots_total} co‑brand slots this quarter; {slots_in_build} already in build. I can hold a slot for {company} until {hold_until}."
                )
                body = (
                    f"Hi {contact_name},\n\n"
                    f"{vp['compliment']}\n\n"
                    f"{one_liner}\n\n"
                    f"What we hear: {vp['pain']}\n\n"
                    f"Why it helps {company}: {vp['wiifm']}\n\n"
                    f"{no_downside}\n\n"
                    f"Proof: {vp['proof']}\n\n"
                    f"Partner terms: {vp['offer']}\n\n{terms_clarifier}\n\n{scarcity_line}\n\n"
                    f"Reply YES and I’ll send a {company}-branded sample today (we can use a public CSV or one you share). Prefer a quick chat? Propose a 15‑min slot and I’ll make it work."
                )
                body = body + f"\n\nOr pick a time: {calendly_url}"
            else:
                rendered = render_template(template_a, replacements)
                parsed = extract_subject_and_body(rendered)
                # Subtly incorporate a pilot slot reference
                subject = f"{company}: reserved pilot slot — instant co‑branded certificates (we pay 15%)"
                # Generic terms clarifier for concise template
                generic_terms = (
                    "Partner terms: We pay 15% of certificate fees generated when your customers use your co-branded templates on ProofKit. "
                    "No change to your pricing/margins; we handle build, onboarding, billing, and support; monthly usage report + payout; pilot in ~7 days."
                )
                hold_until = time.strftime("%b %d", time.gmtime(time.time() + 7 * 86400))
                scarcity_line = (
                    f"We’re opening {slots_total} co‑brand slots this quarter; {slots_in_build} already in build. I can hold a slot for {company} until {hold_until}."
                )
                body = parsed["body"] + f"\n\n{generic_terms}\n\n{scarcity_line}\n\nOr pick a time: {calendly_url}"

            # Insert one-line personalization if available
            ps_line: Optional[str] = None
            for key, val in vendor_ps.items():
                if key.lower() in company.lower():
                    ps_line = val
                    break
            if ps_line:
                body = body + f"\n\n{ps_line}"

            # Build HTML minimal wrapper (no phone number, correct site)
            html_body = f"""
            <div style='font-family: Inter, Arial, sans-serif; line-height: 1.6;'>
              {body.replace('\n', '<br>')}
              <hr>
              <p style='font-size:12px;color:#6b7280'>
                Tamsar, Inc. • <a href='{website_url}'>{website_url}</a><br>
                131 CONTINENTAL DR, STE 305, New Castle, DE 19713<br>
                Don’t want emails from us? Reply with "unsubscribe".
              </p>
            </div>
            """
            text_body = body + f"\n\n---\nTamsar, Inc. • {website_url}\n131 CONTINENTAL DR, STE 305, New Castle, DE 19713\nUnsubscribe: reply with 'unsubscribe'\n"

            if args.dry_run:
                print("\n--- DRY RUN ---")
                print(f"To: {to_email}")
                print(f"Subject: {subject}")
                print(text_body[:400] + ("..." if len(text_body) > 400 else ""))
            else:
                ok, status, resp_text = send_postmark(to_email, subject, html_body, text_body)
                # ISP block/backoff handling
                if (not ok) and ("XGEMAIL_0011" in resp_text or "550 5.7.1" in resp_text or "Command rejected" in resp_text):
                    print("⚠️ ISP block detected; pausing sends to protect deliverability.")
                    # Abort remaining sends in this run
                    break
                # Pacing with jitter
                delay = max(0.0, args.pace_seconds + random.uniform(0, args.jitter_seconds))
                time.sleep(delay)
                if ok:
                    sent += 1
                    # Append to sent log
                    try:
                        write_header = not sent_log_path.exists()
                        with open(sent_log_path, "a", newline="", encoding="utf-8") as f:
                            fieldnames = ["Timestamp", "Company", "To", "Subject"]
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            if write_header:
                                writer.writeheader()
                            writer.writerow({
                                "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "Company": company,
                                "To": to_email,
                                "Subject": subject,
                            })
                        seen_emails.add(to_email.lower())
                    except Exception:
                        pass
                if args.limit and sent >= args.limit:
                    break

    print(f"Done. Sent={sent} (dry_run={args.dry_run})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

