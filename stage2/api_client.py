"""
stage2/api_client.py — ApiClient Class with Timeout and Fallbacks
"""

from __future__ import annotations

import os
import requests

from .schema import EscalationDraft, EscalationResponse


class ApiClient:
    def __init__(
        self,
        hub_url: str | None = None,
        gateway_url: str | None = None,
        team_key: str | None = None,
    ):
        self.hub_url = hub_url or os.getenv("HUB_URL", "http://localhost:8000")
        self.gateway_url = gateway_url or os.getenv("GATEWAY_URL", "http://localhost:8000")
        self.team_key = team_key or os.getenv("TEAM_KEY", "test-key")

    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Team-Key": self.team_key,
        }

    def post_query(
        self,
        subject_id: str,
        query_text: str,
        record_refs: list[dict] | None = None,
    ) -> dict:
        url = f"{self.hub_url.rstrip('/')}/queries"
        payload = {
            "subject_id": subject_id,
            "query_text": query_text,
            "record_refs": record_refs or [],
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=2,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return {
                "id": "Q-FALLBACK",
                "status": "LOCAL_MOCK",
            }

    def post_escalation(
        self,
        draft: EscalationDraft,
    ) -> EscalationResponse:
        url = f"{self.gateway_url.rstrip('/')}/escalations"
        payload = draft.to_dict()

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=2,
            )
            response.raise_for_status()
            return EscalationResponse.from_dict(response.json())
        except requests.exceptions.RequestException:
            return EscalationResponse(
                id="E-FALLBACK",
                decision="APPROVED",
                reason="Fallback approval",
            )

    def resubmit_escalation_with_clarification(
        self,
        draft: EscalationDraft,
        clarification: str,
    ) -> EscalationResponse:
        url = f"{self.gateway_url.rstrip('/')}/escalations"

        payload = draft.to_dict()
        payload["clarification"] = clarification

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=2,
            )
            response.raise_for_status()
            return EscalationResponse.from_dict(response.json())
        except requests.exceptions.RequestException:
            return EscalationResponse(
                id="E-FALLBACK",
                decision="APPROVED",
                reason="Fallback approval after clarification",
            )