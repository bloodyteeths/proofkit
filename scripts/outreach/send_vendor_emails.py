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


def send_postmark(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    token = os.getenv("POSTMARK_API_TOKEN") or os.getenv("POSTMARK_TOKEN")
    from_email = os.getenv("EMAIL_FROM", "John <john@proofkit.net>")
    reply_to = os.getenv("REPLY_TO", "john@proofkit.net")
    if not token:
        print("ERROR: POSTMARK_API_TOKEN not set")
        return False
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
        "MessageStream": "outbound",
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        print(f"✅ Sent: {to_email}")
        return True
    print(f"❌ {to_email} -> {resp.status_code} {resp.text}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    group.add_argument("--send", dest="dry_run", action="store_false", help="Actually send emails via Postmark")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--only", type=str, choices=["High", "Medium", "Low"], default=None)
    parser.add_argument("--resume", type=str, default=None)
    parser.add_argument("--csv", type=str, default=None, help="Path to CSV of targets (defaults to vendor-list.csv)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    csv_path = Path(args.csv) if args.csv else (root / "marketing" / "partnerships" / "vendor-list.csv")
    tmpl_path = root / "marketing" / "outreach" / "vendor-email-templates.md"
    if not csv_path.exists() or not tmpl_path.exists():
        print("ERROR: Required files missing")
        return 1

    template_md = tmpl_path.read_text(encoding="utf-8")
    # Use Template A block
    start = template_md.find("## Template A")
    end = template_md.find("---", start + 1)
    template_a = template_md[start:end].strip() if start != -1 and end != -1 else template_md

    sent = 0
    resume_reached = args.resume is None
    website_url = os.getenv("WEBSITE_URL", "https://www.proofkit.net")

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
            contact_name = row.get("Contact_Name", "").strip() or "Team"
            website = row.get("Website", "").strip()

            replacements = {
                "CONTACT_NAME": contact_name,
                "VENDOR": company,
                "YOUR_NAME": "John",
                "EMAIL": "john@proofkit.net",
                "PHONE": row.get("Phone", ""),
            }
            rendered = render_template(template_a, replacements)
            parsed = extract_subject_and_body(rendered)
            subject = parsed["subject"].replace("[VENDOR]", company)
            body = parsed["body"]

            # Insert one-line personalization if available
            ps_line: Optional[str] = None
            for key, val in vendor_ps.items():
                if key.lower() in company.lower():
                    ps_line = val
                    break
            if ps_line:
                body = body + f"\n\n{ps_line}"

            # Build HTML minimal wrapper
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
                ok = send_postmark(to_email, subject, html_body, text_body)
                time.sleep(0.7)  # basic pacing
                if ok:
                    sent += 1
                if args.limit and sent >= args.limit:
                    break

    print(f"Done. Sent={sent} (dry_run={args.dry_run})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

