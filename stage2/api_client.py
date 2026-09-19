
"""
stage2/api_client.py — ApiClient Class with Explicit Mock Mode
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
        mock_api: bool = False,
    ):
        self.hub_url = hub_url or os.getenv("HUB_URL", "http://localhost:8000")
        self.gateway_url = gateway_url or os.getenv(
            "GATEWAY_URL",
            "http://localhost:8000",
        )
        self.team_key = team_key or os.getenv("TEAM_KEY", "test-key")
        self.mock_api = mock_api

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
        if self.mock_api:
            return {
                "id": "Q-LOCAL-MOCK",
                "status": "LOCAL_MOCK",
            }

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

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Hub API unavailable at {url}. "
                "Run with --mock-api only for an explicitly local/mock run."
            ) from exc

    def post_escalation(
        self,
        draft: EscalationDraft,
    ) -> EscalationResponse:

        if self.mock_api:
            return EscalationResponse(
                id="E-LOCAL-MOCK",
                decision="APPROVED",
                reason="LOCAL MOCK MODE: simulated approval; no real human decision.",
            )

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

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Gateway API unavailable at {url}. "
                "Run with --mock-api only for an explicitly local/mock run."
            ) from exc

    def resubmit_escalation_with_clarification(
        self,
        draft: EscalationDraft,
        clarification: str,
    ) -> EscalationResponse:

        if self.mock_api:
            return EscalationResponse(
                id="E-LOCAL-MOCK",
                decision="APPROVED",
                reason=(
                    "LOCAL MOCK MODE: simulated approval after clarification; "
                    "no real human decision."
                ),
            )

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

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Gateway API unavailable at {url}. "
                "Run with --mock-api only for an explicitly local/mock run."
            ) from exc