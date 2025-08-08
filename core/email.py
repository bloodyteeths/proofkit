"""
Email sending utilities for transactional and marketing sequences.

Currently supports Postmark via HTTPS API.
"""

from __future__ import annotations

import json
import os
import ssl
from typing import Optional, Tuple
from urllib import request as urlrequest

from core.logging import get_logger

logger = get_logger(__name__)


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 15) -> Tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers=headers, method="POST")
    context = ssl.create_default_context()
    try:
        with urlrequest.urlopen(req, context=context, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.getcode(), body
    except Exception as e:
        return 0, str(e)


def send_postmark_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_email: Optional[str] = None,
) -> bool:
    """Send an email via Postmark API using only stdlib.

    Reads token from POSTMARK_API_TOKEN or POSTMARK_TOKEN.
    Default From is "John <john@proofkit.net>" unless overridden.
    """
    token = os.getenv("POSTMARK_API_TOKEN") or os.getenv("POSTMARK_TOKEN")
    if not token:
        logger.error("POSTMARK_API_TOKEN not configured")
        return False

    from_addr = from_email or os.getenv("EMAIL_FROM", "John <john@proofkit.net>")

    url = "https://api.postmarkapp.com/email"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Postmark-Server-Token": token,
    }
    payload = {
        "From": from_addr,
        "To": to_email,
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body or html_body,
        "MessageStream": os.getenv("POSTMARK_STREAM", "outbound"),
        "TrackOpens": True,
    }

    status, body = _post_json(url, headers, payload)
    if status == 200:
        logger.info(f"Postmark email sent to {to_email}: {subject}")
        return True
    logger.error(f"Postmark email failed ({status}): {body}")
    return False

