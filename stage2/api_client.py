"""
stage2/api_client.py

Talks to the two real endpoints the problem doc specifies:
    GET  {hub_url}/documents/protocol       -- read protocol rules
    POST {gateway_url}/queries               -- data manager
    POST {gateway_url}/escalations           -- human gate

hub_url, gateway_url, and team_key come from YOUR event registration/team
dashboard — check there for the actual values. This module does not
hardcode a base URL because ReviewCrew's constructor takes them explicitly:

    class ReviewCrew:
        def __init__(self, hub_url, gateway_url, team_key, atlas: Atlas): ...

TODO: confirm the exact auth header format with the organizers' API docs.
This assumes a Bearer token — adjust `_headers()` if theirs differs
(e.g. a custom header like `X-Team-Key`).
"""

from __future__ import annotations

from typing import Any

import requests

from stage2.schema import EscalationDraft, EscalationResponse, QueryDraft, QueryResponse


class ApiClient:
    def __init__(self, hub_url: str, gateway_url: str, team_key: str, timeout: int = 10) -> None:
        self.hub_url = hub_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.team_key = team_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        # TODO: confirm against the real API — this assumes Bearer auth.
        return {"Authorization": f"Bearer {self.team_key}"}

    # --- Hub: read-only reference documents -------------------------------

    def get_protocol_document(self, version: int | None = None) -> str:
        """GET {hub_url}/documents/protocol — returns the protocol text."""
        params = {"version": version} if version is not None else {}
        resp = requests.get(
            f"{self.hub_url}/documents/protocol",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        # TODO: confirm response shape — assuming plain text or {"text": ...}
        try:
            return resp.json().get("text", resp.text)
        except ValueError:
            return resp.text

    # --- Gateway: queries and escalations -----------------------------------

    def post_query(self, draft: QueryDraft) -> QueryResponse:
        """POST {gateway_url}/queries"""
        resp = requests.post(
            f"{self.gateway_url}/queries",
            json=draft.to_dict(),
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return QueryResponse.from_dict(resp.json())

    def post_escalation(self, draft: EscalationDraft) -> EscalationResponse:
        """
        POST {gateway_url}/escalations

        Response is always one of:
            {"id": "E-0007", "decision": "APPROVED", "reason": "..."}
            {"id": "E-0007", "decision": "REJECTED", "reason": "..."}
            {"id": "E-0007", "decision": "CLARIFY",  "reason": "<the actual question>"}
        """
        resp = requests.post(
            f"{self.gateway_url}/escalations",
            json=draft.to_dict(),
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return EscalationResponse.from_dict(resp.json())

    def resubmit_escalation_with_clarification(
        self, draft: EscalationDraft, clarification_answer: str
    ) -> EscalationResponse:
        """
        Resubmit an escalation after auto-answering a CLARIFY request.

        TODO: confirm the exact resubmission contract with the real API —
        this assumes appending the answer to the summary and POSTing again
        as a fresh escalation body. If the API instead expects a PATCH to
        the original escalation id, adjust this method accordingly.
        """
        updated = EscalationDraft(
            code=draft.code,
            usubjid=draft.usubjid,
            severity=draft.severity,
            summary=f"{draft.summary}\n\nClarification: {clarification_answer}",
            evidence=draft.evidence,
            alternatives=draft.alternatives,
        )
        return self.post_escalation(updated)
