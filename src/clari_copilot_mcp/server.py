"""Clari Copilot MCP Server.

Exposes Clari Copilot call data (transcripts, summaries, metadata)
as MCP tools for querying by Claude Code, SHERPA, or other AI agents.

API docs: https://api-doc.copilot.clari.com
Base URL: https://rest-api.copilot.clari.com
Auth: X-Api-Key + X-Api-Password headers
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

from .client import ClariCopilotClient
from .config import Settings

settings = Settings()
client = ClariCopilotClient(settings)

mcp = FastMCP(
    "Clari Copilot",
    instructions=(
        "Query Clari Copilot for customer call recordings, "
        "transcripts, AI summaries, and deal-linked conversations. "
        "Use this to surface trends, feature requests, pain points, "
        "and action items from customer-facing calls."
    ),
)


def _json(obj: object) -> str:
    return json.dumps(obj, indent=2, default=str)


# ------------------------------------------------------------------
# Call Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_calls(
    skip: int = 0,
    limit: int = 25,
    filter_time_gt: str | None = None,
    filter_time_lt: str | None = None,
    filter_user: str | None = None,
    filter_topics: str | None = None,
    filter_type: str | None = None,
    filter_duration_gt: int | None = None,
    filter_duration_lt: int | None = None,
    sort_time: str = "desc",
) -> str:
    """List Clari Copilot calls with filters and pagination.

    Returns call metadata: id, title, users, participants, status, type,
    time, duration, deal info, account, topics, and metrics.

    Does NOT include transcript or summary — use get_call_details for that.

    Args:
        skip: Number of calls to skip (for pagination). Default 0.
        limit: Max calls to return (1-100). Default 25.
        filter_time_gt: Only calls after this time (ISO 8601, e.g. 2026-04-01T00:00:00Z).
        filter_time_lt: Only calls before this time (ISO 8601).
        filter_user: Filter by user email (as shown in Copilot settings).
        filter_topics: Filter by topic name.
        filter_type: Filter by call type (ZOOM, GOOGLE_MEET, MS_TEAMS, etc.).
        filter_duration_gt: Only calls longer than N seconds.
        filter_duration_lt: Only calls shorter than N seconds.
        sort_time: Sort by call time: "asc" or "desc" (default desc = newest first).
    """
    result = await client.list_calls(
        skip=skip,
        limit=limit,
        filter_time_gt=filter_time_gt,
        filter_time_lt=filter_time_lt,
        filter_user=[filter_user] if filter_user else None,
        filter_topics=[filter_topics] if filter_topics else None,
        filter_type=[filter_type] if filter_type else None,
        filter_duration_gt=filter_duration_gt,
        filter_duration_lt=filter_duration_lt,
        sort_time=sort_time,
    )
    return _json(result)


@mcp.tool()
async def get_call_details(call_id: str, include_audio: bool = False) -> str:
    """Get full details for a single call, including transcript and AI summary.

    Returns everything from list_calls PLUS:
    - transcript: array of speaker-diarized utterances with timestamps
    - summary: full_summary text, topics_discussed, key_action_items
    - competitor_sentiments: competitor mentions with sentiment and reasoning
    - deal_stage_live: current deal stage

    Args:
        call_id: The call ID (from list_calls results).
        include_audio: If true, include a signed audio URL (valid 4 hours).
    """
    result = await client.get_call_details(call_id, include_audio=include_audio)
    return _json(result)


@mcp.tool()
async def get_transcript(call_id: str) -> str:
    """Get just the transcript for a call.

    Returns speaker-diarized text with timestamps and annotations
    (topic tracker matches, AI-detected labels).

    Args:
        call_id: The call ID (from list_calls results).
    """
    result = await client.get_call_details(call_id)
    call = result.get("call", result)
    transcript = call.get("transcript", [])
    title = call.get("title", "Unknown")
    return _json({
        "call_id": call_id,
        "title": title,
        "utterance_count": len(transcript),
        "transcript": transcript,
    })


@mcp.tool()
async def get_summary(call_id: str) -> str:
    """Get the AI-generated Smart Summary for a call.

    Returns:
    - full_summary: narrative summary text
    - topics_discussed: list of topics with timestamps and per-topic summaries
    - key_action_items: action items with speaker and timestamps
    - competitor_sentiments: competitor mentions with sentiment analysis

    Args:
        call_id: The call ID (from list_calls results).
    """
    result = await client.get_call_details(call_id)
    call = result.get("call", result)
    return _json({
        "call_id": call_id,
        "title": call.get("title", "Unknown"),
        "summary": call.get("summary", {}),
        "competitor_sentiments": call.get("competitor_sentiments", []),
    })


@mcp.tool()
async def get_recent_summaries(
    days: int = 7,
    limit: int = 50,
    filter_duration_gt: int = 120,
) -> str:
    """Batch-fetch AI summaries for recent calls.

    Fetches calls from the last N days and retrieves each summary.
    Useful for trend analysis across multiple conversations.

    Args:
        days: Number of days to look back (default 7).
        limit: Max calls to process (default 50).
        filter_duration_gt: Only include calls longer than N seconds (default 120 = 2 min, to skip short/failed calls).
    """
    to_dt = date.today()
    from_dt = to_dt - timedelta(days=days)

    calls_result = await client.list_calls(
        filter_time_gt=f"{from_dt}T00:00:00Z",
        filter_time_lt=f"{to_dt}T23:59:59Z",
        filter_duration_gt=filter_duration_gt,
        limit=min(limit, 100),
        sort_time="desc",
        include_pagination=True,
    )

    calls = calls_result.get("calls", [])
    summaries = []

    for call in calls:
        call_id = call.get("id", "")
        if not call_id:
            continue
        try:
            details = await client.get_call_details(call_id)
            detail_call = details.get("call", details)
            summaries.append({
                "call_id": call_id,
                "title": call.get("title", "Unknown"),
                "time": call.get("time", ""),
                "duration_sec": call.get("metrics", {}).get("call_duration", ""),
                "users": [u.get("userEmail", "") for u in call.get("users", [])],
                "external_participants": [
                    p.get("name", p.get("email", ""))
                    for p in call.get("externalParticipants", [])
                ],
                "deal_name": call.get("deal_name", ""),
                "account_name": call.get("account_name", ""),
                "summary": detail_call.get("summary", {}),
                "competitor_sentiments": detail_call.get("competitor_sentiments", []),
            })
        except Exception as e:
            summaries.append({
                "call_id": call_id,
                "title": call.get("title", "Unknown"),
                "error": str(e),
            })

    return _json({
        "period": f"{from_dt} to {to_dt}",
        "total_calls_found": len(calls),
        "summaries_retrieved": len([s for s in summaries if "summary" in s]),
        "pagination": calls_result.get("pagination", {}),
        "results": summaries,
    })


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


@mcp.tool()
async def search_calls(
    query: str,
    days: int = 30,
    limit: int = 100,
) -> str:
    """Search calls by keyword across titles, participants, accounts, and deals.

    Client-side search over call metadata. For large time ranges, consider
    narrowing with the days parameter.

    Args:
        query: Search term (matched case-insensitively against call metadata).
        days: Number of days to look back (default 30).
        limit: Max calls to scan (default 100).
    """
    to_dt = date.today()
    from_dt = to_dt - timedelta(days=days)

    result = await client.list_calls(
        filter_time_gt=f"{from_dt}T00:00:00Z",
        filter_time_lt=f"{to_dt}T23:59:59Z",
        limit=min(limit, 100),
        sort_time="desc",
        include_pagination=False,
    )

    query_lower = query.lower()
    calls = result.get("calls", [])
    matched = []
    for call in calls:
        searchable = json.dumps(call).lower()
        if query_lower in searchable:
            matched.append(call)

    return _json({
        "query": query,
        "period": f"{from_dt} to {to_dt}",
        "scanned": len(calls),
        "matches": len(matched),
        "calls": matched,
    })


# ------------------------------------------------------------------
# Reference Data
# ------------------------------------------------------------------


@mcp.tool()
async def list_users() -> str:
    """List all users in the Clari Copilot system.

    Returns user id, email, name, role (REP/MANAGER/OBSERVER),
    recording status, and manager_id.
    """
    result = await client.list_users()
    return _json(result)


@mcp.tool()
async def list_topics() -> str:
    """List all tracked topics in Clari Copilot.

    Topics include keyword trackers and AI-detected custom topics.
    Use topic names with list_calls(filter_topics=...) to find
    calls where specific topics were discussed.
    """
    result = await client.list_topics_v2()
    return _json(result)


# ------------------------------------------------------------------
# CRM Objects
# ------------------------------------------------------------------


@mcp.tool()
async def get_deal(deal_id: str) -> str:
    """Get CRM deal details from Clari Copilot.

    Returns deal name, amount, stage, close date, owner,
    stage change history, and custom fields.

    Args:
        deal_id: The source CRM deal/opportunity ID.
    """
    result = await client.get_deal(deal_id)
    return _json(result)


@mcp.tool()
async def get_account(account_id: str) -> str:
    """Get CRM account details from Clari Copilot.

    Args:
        account_id: The source CRM account ID.
    """
    result = await client.get_account(account_id)
    return _json(result)


# ------------------------------------------------------------------
# Scorecards
# ------------------------------------------------------------------


@mcp.tool()
async def list_scorecards(
    skip: int = 0,
    limit: int = 50,
    filter_time_gt: str | None = None,
    filter_time_lt: str | None = None,
    filter_rep_id: str | None = None,
) -> str:
    """List call scorecards.

    Scorecards contain scored evaluations of calls against templates.

    Args:
        skip: Number to skip for pagination. Default 0.
        limit: Max results (1-100). Default 50.
        filter_time_gt: Only scorecards after this time (ISO 8601).
        filter_time_lt: Only scorecards before this time (ISO 8601).
        filter_rep_id: Filter by the user ID being scored.
    """
    result = await client.list_scorecards(
        skip=skip,
        limit=limit,
        filter_time_gt=filter_time_gt,
        filter_time_lt=filter_time_lt,
        filter_rep_id=filter_rep_id,
    )
    return _json(result)


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------


def main() -> None:
    """Run the MCP server (stdio transport for local, or SSE for hosted)."""
    mcp.run()


if __name__ == "__main__":
    main()
