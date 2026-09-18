"""
stage2/api_client.py  —  PERSON B

Thin wrapper around the two endpoints the pipeline talks to:
  POST /queries       (data manager)
  POST /escalations   (human gate)

Kept as a separate module so it's trivial to monkeypatch/mock in tests
without touching node logic.
"""

from __future__ import annotations

import os
from typing import Any

import requests

BASE_URL = os.environ.get("ATLAS_API_BASE_URL", "http://localhost:8000")


def post_query(subject_id: str, query_text: str, record_refs: list[str]) -> dict[str, Any]:
    """POST /queries — raises requests.HTTPError on failure."""
    resp = requests.post(
        f"{BASE_URL}/queries",
        json={"subject_id": subject_id, "query_text": query_text, "record_refs": record_refs},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def post_escalation(subject_id: str, reason: str, record_refs: list[str]) -> dict[str, Any]:
    """
    POST /escalations — raises requests.HTTPError on failure.

    Expected response shape (confirm against the actual API spec):
        {"decision": "APPROVED" | "REJECTED" | "CLARIFY", "clarify_question": str | None}
    """
    resp = requests.post(
        f"{BASE_URL}/escalations",
        json={"subject_id": subject_id, "reason": reason, "record_refs": record_refs},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
