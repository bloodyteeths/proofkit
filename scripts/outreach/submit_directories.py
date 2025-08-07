#!/usr/bin/env python3
"""
Prepare submissions for free/paid directories from marketing/directories/directory-list.csv.

This script outputs a CSV and Markdown with tailored descriptions and UTM links
you can copy into web forms. It can also email editors when an email is provided.

Usage:
  python3 scripts/outreach/submit_directories.py --out build/directory_submissions
  POSTMARK_API_TOKEN=... python3 scripts/outreach/submit_directories.py --email-editors --limit 5
"""

import csv
import os
import argparse
from pathlib import Path
from typing import Dict
import httpx


ABOUT = (
    "ProofKit converts temperature logger CSVs into compliant, tamper-evident "
    "PDF/A-3 certificates in seconds. Supports powder coating (ISO 2368), HACCP "
    "135-70-41, autoclave CFR 21 Part 11, ASTM C31 concrete curing, and cold chain."
)


def build_profile(category: str, industry: str) -> Dict[str, str]:
    title = "ProofKit — Industrial Temperature Validation"
    desc = ABOUT
    features = (
        "• Upload CSV → PASS/FAIL PDF/A-3\n"
        "• Cryptographic integrity (SHA-256, RFC 3161)\n"
        "• Inspector-ready certificates and verification portal\n"
        "• Works with any logger vendor\n"
    )
    url = "https://www.proofkit.net/?utm_source=directory&utm_medium=referral&utm_campaign=" + (
        category.lower().replace(" ", "_")
    )
    return {
        "Title": title,
        "ShortDescription": desc,
        "Features": features,
        "URL": url,
        "Category": category,
        "Industry": industry,
    }


def email_editor(to_email: str, directory_name: str, submit_url: str, profile: Dict[str, str]) -> bool:
    token = os.getenv("POSTMARK_API_TOKEN") or os.getenv("POSTMARK_TOKEN")
    if not token:
        return False
    from_email = os.getenv("EMAIL_FROM", "John <john@proofkit.net>")
    subject = f"Listing submission request: {directory_name}"
    html = f"""
    <p>Hi {directory_name} Team,</p>
    <p>Please find below our listing details. We meet your category requirements and would love to be included.</p>
    <p><strong>Submission URL:</strong> {submit_url}</p>
    <hr>
    <p><strong>{profile['Title']}</strong><br>{profile['ShortDescription']}</p>
    <pre>{profile['Features']}</pre>
    <p><a href="{profile['URL']}">{profile['URL']}</a></p>
    <p>Thanks!<br>John, ProofKit</p>
    """
    data = {
        "From": from_email,
        "To": to_email,
        "Subject": subject,
        "HtmlBody": html,
        "TextBody": html,
        "MessageStream": "outbound",
    }
    with httpx.Client(timeout=20.0) as client:
        r = client.post("https://api.postmarkapp.com/email", headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": token,
        }, json=data)
    return r.status_code == 200


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="build/directory_submissions")
    parser.add_argument("--email-editors", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    csv_path = root / "marketing" / "directories" / "directory-list.csv"
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(csv_path.open()))

    out_csv = out_dir / "submissions.csv"
    out_md = out_dir / "submissions.md"
    with out_csv.open("w", newline="", encoding="utf-8") as cf, out_md.open("w", encoding="utf-8") as mf:
        fieldnames = [
            "Directory Name", "Website", "Submission URL", "Category", "Industry Focus",
            "Submission Cost", "Authority Score", "Estimated Traffic", "Contact Email",
            "Title", "ShortDescription", "Features", "URL"
        ]
        writer = csv.DictWriter(cf, fieldnames=fieldnames)
        writer.writeheader()

        count = 0
        for r in rows:
            profile = build_profile(r.get("Category", ""), r.get("Industry Focus", ""))
            out_row = {
                **{k: r.get(k, "") for k in [
                    "Directory Name", "Website", "Submission URL", "Category", "Industry Focus",
                    "Submission Cost", "Authority Score", "Estimated Traffic", "Contact Email"
                ]},
                **profile,
            }
            writer.writerow(out_row)
            mf.write(f"\n### {r.get('Directory Name')}\n\n")
            mf.write(f"- Submission: {r.get('Submission URL')}\n")
            mf.write(f"- Email: {r.get('Contact Email')}\n")
            mf.write(f"- Title: {profile['Title']}\n")
            mf.write(f"- URL: {profile['URL']}\n\n")
            mf.write(f"{profile['ShortDescription']}\n\n")
            mf.write("```\n" + profile["Features"] + "\n```\n\n")

            if args.email_editors and r.get("Contact Email"):
                ok = email_editor(r["Contact Email"], r["Directory Name"], r.get("Submission URL", ""), profile)
                print(f"Email {r['Directory Name']}: {'OK' if ok else 'FAIL'}")

            count += 1
            if args.limit and count >= args.limit:
                break

    print(f"Prepared {count} submissions → {out_dir}")


if __name__ == "__main__":
    main()

