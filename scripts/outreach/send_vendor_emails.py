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
from typing import Dict, Any

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
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--only", type=str, choices=["High", "Medium", "Low"], default=None)
    parser.add_argument("--resume", type=str, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    csv_path = root / "marketing" / "partnerships" / "vendor-list.csv"
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

            # Build HTML minimal wrapper
            html_body = f"""
            <div style='font-family: Inter, Arial, sans-serif; line-height: 1.6;'>
              {body.replace('\n', '<br>')}
              <hr>
              <p style='font-size:12px;color:#6b7280'>ProofKit • proofkit.net</p>
            </div>
            """
            text_body = body

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

