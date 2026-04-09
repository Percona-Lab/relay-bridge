"""Clari Copilot API client.

Based on the official OpenAPI spec at https://api-doc.copilot.clari.com
Base URL: https://rest-api.copilot.clari.com
Auth: X-Api-Key + X-Api-Password headers
Rate limit: 10/sec, 100k/week (resets Sunday 0 GMT)
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class ClariCopilotClient:
    """Async HTTP client for the Clari Copilot REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._http = httpx.AsyncClient(
            base_url=self.settings.clari_base_url,
            headers={
                "X-Api-Key": self.settings.clari_api_key,
                "X-Api-Password": self.settings.clari_api_password,
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
        skip: int = 0,
        limit: int = 25,
        filter_user: list[str] | None = None,
        filter_attendees: list[str] | None = None,
        filter_topics: list[str] | None = None,
        filter_status: list[str] | None = None,
        filter_type: list[str] | None = None,
        filter_time_gt: str | None = None,
        filter_time_lt: str | None = None,
        filter_modified_gt: str | None = None,
        filter_modified_lt: str | None = None,
        filter_duration_gt: int | None = None,
        filter_duration_lt: int | None = None,
        sort_time: str | None = None,
        include_private: bool = False,
        include_audio: bool = False,
        include_video: bool = False,
        include_pagination: bool = True,
    ) -> dict[str, Any]:
        """List calls with filters. Max 100 per page, use skip/limit to paginate."""
        params: dict[str, Any] = {
            "skip": skip,
            "limit": limit,
            "includePagination": str(include_pagination).lower(),
        }
        if filter_user:
            params["filterUser"] = filter_user
        if filter_attendees:
            params["filterAttendees"] = filter_attendees
        if filter_topics:
            params["filterTopics"] = filter_topics
        if filter_status:
            params["filterStatus"] = filter_status
        if filter_type:
            params["filterType"] = filter_type
        if filter_time_gt:
            params["filterTimeGt"] = filter_time_gt
        if filter_time_lt:
            params["filterTimeLt"] = filter_time_lt
        if filter_modified_gt:
            params["filterModifiedGt"] = filter_modified_gt
        if filter_modified_lt:
            params["filterModifiedLt"] = filter_modified_lt
        if filter_duration_gt is not None:
            params["filterDurationGt"] = filter_duration_gt
        if filter_duration_lt is not None:
            params["filterDurationLt"] = filter_duration_lt
        if sort_time:
            params["sortTime"] = sort_time
        if include_private:
            params["includePrivate"] = "true"
        if include_audio:
            params["includeAudio"] = True
        if include_video:
            params["includeVideo"] = True

        resp = await self._http.get("/calls", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_call_details(
        self,
        call_id: str,
        *,
        include_audio: bool = False,
        include_video: bool = False,
    ) -> dict[str, Any]:
        """Get full call details including transcript, summary, and competitor sentiments."""
        params: dict[str, Any] = {"id": call_id}
        if include_audio:
            params["includeAudio"] = True
        if include_video:
            params["includeVideo"] = True

        resp = await self._http.get("/call-details", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def list_users(self) -> dict[str, Any]:
        """List all users in the Copilot system."""
        resp = await self._http.get("/users")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------

    async def list_topics(self) -> dict[str, Any]:
        """List all keyword topics."""
        resp = await self._http.get("/topics")
        resp.raise_for_status()
        return resp.json()

    async def list_topics_v2(
        self,
        *,
        filter_modified_gt: str | None = None,
        filter_modified_lt: str | None = None,
    ) -> dict[str, Any]:
        """List detailed topics with optional date filters."""
        params: dict[str, Any] = {}
        if filter_modified_gt:
            params["filterModifiedGt"] = filter_modified_gt
        if filter_modified_lt:
            params["filterModifiedLt"] = filter_modified_lt

        resp = await self._http.get("/v2/topics", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Scorecards
    # ------------------------------------------------------------------

    async def list_scorecards(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        filter_time_gt: str | None = None,
        filter_time_lt: str | None = None,
        filter_rep_id: str | None = None,
        filter_scorer_id: str | None = None,
    ) -> dict[str, Any]:
        """List scorecards with filters."""
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if filter_time_gt:
            params["filterTimeGt"] = filter_time_gt
        if filter_time_lt:
            params["filterTimeLt"] = filter_time_lt
        if filter_rep_id:
            params["filterRepId"] = filter_rep_id
        if filter_scorer_id:
            params["filterScorerId"] = filter_scorer_id

        resp = await self._http.get("/scorecard", params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_scorecard_templates(self) -> dict[str, Any]:
        """List all scorecard templates."""
        resp = await self._http.get("/scorecard-template")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # CRM Objects
    # ------------------------------------------------------------------

    async def get_deal(self, deal_id: str) -> dict[str, Any]:
        """Get a CRM deal by source ID."""
        resp = await self._http.get("/get-deal", params={"id": deal_id})
        resp.raise_for_status()
        return resp.json()

    async def get_account(self, account_id: str) -> dict[str, Any]:
        """Get a CRM account by source ID."""
        resp = await self._http.get("/get-account", params={"id": account_id})
        resp.raise_for_status()
        return resp.json()

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Get a CRM contact by source ID."""
        resp = await self._http.get("/get-contact", params={"id": contact_id})
        resp.raise_for_status()
        return resp.json()
