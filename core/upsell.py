"""
Simple upsell scheduler:
- Schedules logo-free PDF upsell 72h post-generation
- Sends reminder at +5d
- Sends urgency email at +7d (expiry)

Uses a file-backed queue in storage to avoid DB.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

from core.email import send_postmark_email
from core.logging import get_logger

logger = get_logger(__name__)

STORAGE_DIR = Path(os.environ.get("UPSSELL_STORAGE_DIR", Path(__file__).resolve().parents[1] / "storage"))
QUEUE_FILE = STORAGE_DIR / "upsell_queue.jsonl"


@dataclass
class UpsellJob:
    email: str
    certificate_id: str
    industry: str
    spec_type: str
    created_at: str  # ISO
    stage: str  # scheduled72h | reminder5d | urgency7d | done


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_upsell(email: str, certificate_id: str, industry: str, spec_type: str) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    job = UpsellJob(
        email=email,
        certificate_id=certificate_id,
        industry=industry,
        spec_type=spec_type,
        created_at=_now_iso(),
        stage="scheduled72h",
    )
    with QUEUE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(job)) + "\n")
    logger.info(f"Enqueued upsell for {email} cert={certificate_id}")


def _read_jobs() -> List[UpsellJob]:
    if not QUEUE_FILE.exists():
        return []
    jobs: List[UpsellJob] = []
    with QUEUE_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                jobs.append(UpsellJob(**data))
            except Exception:
                continue
    return jobs


def _write_jobs(jobs: List[UpsellJob]) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(asdict(j)) + "\n")
    tmp.replace(QUEUE_FILE)


def _send_stage_email(job: UpsellJob) -> bool:
    base_subject = {
        "scheduled72h": "Remove the ProofKit logo for €7",
        "reminder5d": f"How other {job.industry} teams use ProofKit",
        "urgency7d": "Logo-free upgrade expires tomorrow",
    }[job.stage]

    # Basic HTML bodies referencing marketing copy
    html = f"""
    <p>Hi there,</p>
    <p>Your {job.industry} certificate ({job.spec_type}) is ready for a logo-free upgrade.</p>
    <p>One-time cost: €7 · Instant download</p>
    <p>
      <a href="https://www.proofkit.net/app?upgrade={job.certificate_id}" style="background:#4c51bf;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;">Upgrade for €7</a>
      &nbsp;
      <a href="https://www.proofkit.net/download/{job.certificate_id}/pdf">View Original</a>
    </p>
    <p>If you have questions, just reply to this email.</p>
    <p>— ProofKit Team</p>
    """
    return send_postmark_email(to_email=job.email, subject=base_subject, html_body=html)


def process_queue_once(now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    jobs = _read_jobs()
    changed = False
    for j in jobs:
        created = datetime.fromisoformat(j.created_at)
        if j.stage == "scheduled72h" and now - created >= timedelta(hours=72):
            if _send_stage_email(j):
                j.stage = "reminder5d"
                changed = True
        elif j.stage == "reminder5d" and now - created >= timedelta(days=5):
            if _send_stage_email(j):
                j.stage = "urgency7d"
                changed = True
        elif j.stage == "urgency7d" and now - created >= timedelta(days=7):
            if _send_stage_email(j):
                j.stage = "done"
                changed = True
        else:
            continue
    if changed:
        _write_jobs(jobs)

