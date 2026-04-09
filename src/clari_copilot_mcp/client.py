"""Clari Copilot API client."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from .config import Settings


class ClariCopilotClient:
    """Async HTTP client for the Clari Copilot API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._http = httpx.AsyncClient(
            base_url=self.settings.clari_base_url,
            headers={
                "x-api-key": self.settings.clari_api_key,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    async def list_calls(
        self,
        *,
        from_date: date | str | None = None,
        to_date: date | str | None = None,
        tag: str | None = None,
        user_id: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        """List calls with optional filters."""
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if from_date:
            params["from_date"] = str(from_date)
        if to_date:
            params["to_date"] = str(to_date)
        if tag:
            params["tags"] = tag
        if user_id:
            params["user_id"] = user_id

        resp = await self._http.get("/calls", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_call(self, call_id: str) -> dict[str, Any]:
        """Get metadata for a single call."""
        resp = await self._http.get(f"/calls/{call_id}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Transcripts
    # ------------------------------------------------------------------

    async def get_transcript(self, call_id: str) -> dict[str, Any]:
        """Get the full speaker-diarized transcript for a call."""
        resp = await self._http.get(f"/calls/{call_id}/transcript")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    async def get_summary(self, call_id: str) -> dict[str, Any]:
        """Get the AI-generated Smart Summary for a call."""
        resp = await self._http.get(f"/calls/{call_id}/summary")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    async def list_tags(self) -> dict[str, Any]:
        """List available call tags."""
        resp = await self._http.get("/tags")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Deals / CRM
    # ------------------------------------------------------------------

    async def get_deal_calls(self, deal_id: str) -> dict[str, Any]:
        """Get calls associated with a CRM deal/opportunity."""
        resp = await self._http.get(f"/deals/{deal_id}/calls")
        resp.raise_for_status()
        return resp.json()
