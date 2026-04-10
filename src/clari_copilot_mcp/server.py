"""Clari Copilot MCP Server.

Exposes Clari Copilot call data (transcripts, summaries, metadata)
as MCP tools for querying by Claude Code, SHERPA, or other AI agents.

Supports two modes:
  - Local: credentials in .env, queries the Clari API directly
  - Remote proxy: forwards tool calls to a shared SSE server (VPN required)

API docs: https://api-doc.copilot.clari.com
Base URL: https://rest-api.copilot.clari.com
Auth: X-Api-Key + X-Api-Password headers
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

from .config import Settings

settings = Settings()

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


# ── Local mode detection ───────────────────────────────────────────
# Local mode is enabled when API credentials are configured.

def _local_enabled() -> bool:
    return bool(settings.clari_api_key)


_client = None


def _client_instance():
    global _client
    if _client is None:
        from .client import ClariCopilotClient
        _client = ClariCopilotClient(settings)
    return _client


# ── Remote proxy mode ──────────────────────────────────────────────
# When REMOTE_SSE_URL is set, tool calls are forwarded to a remote MCP
# server via SSE. This lets the server start instantly (tools register)
# even when off VPN — connection is attempted lazily per tool call.

_REMOTE_SSE_URL = os.getenv("REMOTE_SSE_URL")

_VPN_REQUIRED_MSG = (
    "**Cannot reach the Clari Copilot data server.** Connect to Percona VPN and try again.\n\n"
    "The MCP is configured in remote mode — it connects to a shared server "
    "that is only accessible on the Percona internal network.\n\n"
    "_If you need offline access, re-run the installer and choose Local mode "
    "with your own Clari Copilot API credentials._"
)

_NOT_CONFIGURED_MSG = (
    "**Clari Copilot not configured.** Run the installer to set up the data connection:\n"
    "```\n"
    "curl -fsSL https://raw.githubusercontent.com/Percona-Lab/relay-bridge/main/installer.py | python3 -\n"
    "```\n"
    "Choose Remote (default) for VPN access, or Local if you have your own API credentials.\n"
    "See https://github.com/Percona-Lab/relay-bridge for details."
)


def _friendly_error(source: str, e: Exception) -> str:
    """Return a user-friendly error message based on exception type."""
    etype = type(e).__name__
    msg = str(e)
    if "ConnectionError" in etype or "ConnectionTimeout" in etype or "timed out" in msg.lower():
        return (
            f"**{source} connection failed.** Cannot reach the server.\n\n"
            f"**If using the remote server (recommended setup):** Connect to Percona VPN and try again.\n"
            f"**If running locally with your own credentials:** Check that the base URL in your .env file is correct "
            f"and reachable from your network.\n\n"
            f"_Technical detail: {etype}: {msg}_"
        )
    if "Authentication" in etype or "401" in msg or "403" in msg:
        return (
            f"**{source} authentication failed.** Your credentials are incorrect or expired. "
            f"Check the API key and password in your .env file. "
            f"If you don't have credentials, switch to the remote server instead — "
            f"no credentials needed, just VPN. See https://github.com/Percona-Lab/relay-bridge\n\n"
            f"_Technical detail: {etype}: {msg}_"
        )
    return f"**{source} query failed:** {etype}: {msg}"


async def _call_remote(tool_name: str, arguments: dict) -> str:
    """Forward a tool call to the remote MCP server via SSE."""
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    try:
        async with sse_client(url=_REMOTE_SSE_URL) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.content:
                    parts = [
                        block.text for block in result.content
                        if hasattr(block, "text")
                    ]
                    return "\n".join(parts) if parts else "No results."
                return "No results returned."
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in [
            "nodename", "connecterror", "connect error",
            "timed out", "connection refused", "unreachable",
            "name or service not known", "no route to host",
        ]):
            return _VPN_REQUIRED_MSG
        return f"**Remote query failed:** {type(e).__name__}: {e}"


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            args = {"skip": skip, "limit": limit, "sort_time": sort_time}
            if filter_time_gt:
                args["filter_time_gt"] = filter_time_gt
            if filter_time_lt:
                args["filter_time_lt"] = filter_time_lt
            if filter_user:
                args["filter_user"] = filter_user
            if filter_topics:
                args["filter_topics"] = filter_topics
            if filter_type:
                args["filter_type"] = filter_type
            if filter_duration_gt is not None:
                args["filter_duration_gt"] = filter_duration_gt
            if filter_duration_lt is not None:
                args["filter_duration_lt"] = filter_duration_lt
            return await _call_remote("list_calls", args)
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().list_calls(
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
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            args = {"call_id": call_id}
            if include_audio:
                args["include_audio"] = include_audio
            return await _call_remote("get_call_details", args)
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().get_call_details(call_id, include_audio=include_audio)
        return _json(result)
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


@mcp.tool()
async def get_transcript(call_id: str) -> str:
    """Get just the transcript for a call.

    Returns speaker-diarized text with timestamps and annotations
    (topic tracker matches, AI-detected labels).

    Args:
        call_id: The call ID (from list_calls results).
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("get_transcript", {"call_id": call_id})
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().get_call_details(call_id)
        call = result.get("call", result)
        transcript = call.get("transcript", [])
        title = call.get("title", "Unknown")
        return _json({
            "call_id": call_id,
            "title": title,
            "utterance_count": len(transcript),
            "transcript": transcript,
        })
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("get_summary", {"call_id": call_id})
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().get_call_details(call_id)
        call = result.get("call", result)
        return _json({
            "call_id": call_id,
            "title": call.get("title", "Unknown"),
            "summary": call.get("summary", {}),
            "competitor_sentiments": call.get("competitor_sentiments", []),
        })
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("get_recent_summaries", {
                "days": days, "limit": limit, "filter_duration_gt": filter_duration_gt,
            })
        return _NOT_CONFIGURED_MSG
    try:
        to_dt = date.today()
        from_dt = to_dt - timedelta(days=days)

        calls_result = await _client_instance().list_calls(
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
                details = await _client_instance().get_call_details(call_id)
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
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("search_calls", {
                "query": query, "days": days, "limit": limit,
            })
        return _NOT_CONFIGURED_MSG
    try:
        to_dt = date.today()
        from_dt = to_dt - timedelta(days=days)

        result = await _client_instance().list_calls(
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
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


# ------------------------------------------------------------------
# Reference Data
# ------------------------------------------------------------------


@mcp.tool()
async def list_users() -> str:
    """List all users in the Clari Copilot system.

    Returns user id, email, name, role (REP/MANAGER/OBSERVER),
    recording status, and manager_id.
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("list_users", {})
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().list_users()
        return _json(result)
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


@mcp.tool()
async def list_topics() -> str:
    """List all tracked topics in Clari Copilot.

    Topics include keyword trackers and AI-detected custom topics.
    Use topic names with list_calls(filter_topics=...) to find
    calls where specific topics were discussed.
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("list_topics", {})
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().list_topics_v2()
        return _json(result)
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("get_deal", {"deal_id": deal_id})
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().get_deal(deal_id)
        return _json(result)
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


@mcp.tool()
async def get_account(account_id: str) -> str:
    """Get CRM account details from Clari Copilot.

    Args:
        account_id: The source CRM account ID.
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("get_account", {"account_id": account_id})
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().get_account(account_id)
        return _json(result)
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


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
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            args = {"skip": skip, "limit": limit}
            if filter_time_gt:
                args["filter_time_gt"] = filter_time_gt
            if filter_time_lt:
                args["filter_time_lt"] = filter_time_lt
            if filter_rep_id:
                args["filter_rep_id"] = filter_rep_id
            return await _call_remote("list_scorecards", args)
        return _NOT_CONFIGURED_MSG
    try:
        result = await _client_instance().list_scorecards(
            skip=skip,
            limit=limit,
            filter_time_gt=filter_time_gt,
            filter_time_lt=filter_time_lt,
            filter_rep_id=filter_rep_id,
        )
        return _json(result)
    except Exception as e:
        return _friendly_error("Clari Copilot", e)


# ------------------------------------------------------------------
# Call Intelligence Index
# ------------------------------------------------------------------


@mcp.tool()
async def query_call_index(
    product_areas: list[str] | None = None,
    customer_type: str | None = None,
    market_signals: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    text_search: str | None = None,
    limit: int = 50,
) -> str:
    """Search the local call intelligence index by product area, customer type, market signals, date range, or text.

    Returns thin metadata (call_id, title, date, account, tags) for matching calls.
    Use get_summary or get_call_details to fetch full details for specific calls.

    The index must be built first with rebuild_call_index.

    Args:
        product_areas: Filter by product areas (MySQL, PostgreSQL, MongoDB, PMM, Operators, Everest, Valkey, Percona Toolkit, Pro Builds, Support, Consulting, ExpertOps). Any match.
        customer_type: Filter by customer type (Enterprise/ICP, Mid-Market, SMB, Prospect, Unknown). Exact match.
        market_signals: Filter by market signals (Migration, Upgrade, New Deployment, Performance Issue, Cost Optimization, Compliance/Security, Cloud Migration, HA/DR, Competitive Eval, Expansion, Churn Risk). Any match.
        date_from: Only calls on or after this date (YYYY-MM-DD).
        date_to: Only calls on or before this date (YYYY-MM-DD).
        text_search: Search titles, accounts, deal names, users (case-insensitive substring).
        limit: Max results to return (default 50).
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            args = {"limit": limit}
            if product_areas:
                args["product_areas"] = product_areas
            if customer_type:
                args["customer_type"] = customer_type
            if market_signals:
                args["market_signals"] = market_signals
            if date_from:
                args["date_from"] = date_from
            if date_to:
                args["date_to"] = date_to
            if text_search:
                args["text_search"] = text_search
            return await _call_remote("query_call_index", args)
        return _NOT_CONFIGURED_MSG
    try:
        from .index import CallIndex
        index = CallIndex()
        if index.count() == 0:
            return _json({
                "error": "Index is empty. Run rebuild_call_index first to populate it.",
                "hint": "Example: rebuild_call_index(days=90)",
            })
        results = index.query(
            product_areas=product_areas,
            customer_type=customer_type,
            market_signals=market_signals,
            date_from=date_from,
            date_to=date_to,
            text_search=text_search,
            limit=limit,
        )
        return _json({
            "matches": len(results),
            "query": {
                "product_areas": product_areas,
                "customer_type": customer_type,
                "market_signals": market_signals,
                "date_from": date_from,
                "date_to": date_to,
                "text_search": text_search,
            },
            "calls": results,
        })
    except Exception as e:
        return _friendly_error("Call Index", e)


@mcp.tool()
async def call_index_stats() -> str:
    """Show statistics about the local call intelligence index.

    Returns counts by product area, customer type, market signal, and date range.
    Useful for understanding what's in the index before querying.
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("call_index_stats", {})
        return _NOT_CONFIGURED_MSG
    try:
        from .index import CallIndex
        index = CallIndex()
        if index.count() == 0:
            return _json({
                "error": "Index is empty. Run rebuild_call_index first to populate it.",
                "hint": "Example: rebuild_call_index(days=90)",
            })
        return _json(index.stats())
    except Exception as e:
        return _friendly_error("Call Index", e)


@mcp.tool()
async def rebuild_call_index(
    days: int = 90,
    max_calls: int = 5000,
    full_rebuild: bool = False,
) -> str:
    """Build or update the local call intelligence index from the Clari Copilot API.

    Fetches call metadata and AI summaries, then tags each call by product area,
    customer type, and market signals. Incremental by default — only indexes
    new calls not already in the index.

    This is a long-running operation (fetches call details one by one at ~6/sec).
    For 1000 new calls, expect ~3 minutes.

    Args:
        days: How many days back to index (default 90).
        max_calls: Max calls to fetch from the API (default 5000).
        full_rebuild: If true, re-index all calls even if already indexed (default false).
    """
    if not _local_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("rebuild_call_index", {
                "days": days, "max_calls": max_calls, "full_rebuild": full_rebuild,
            })
        return _NOT_CONFIGURED_MSG
    try:
        from .indexer import build_index
        result = await build_index(
            days=days,
            max_calls=max_calls,
            skip_existing=not full_rebuild,
        )
        return _json(result)
    except Exception as e:
        return _friendly_error("Indexer", e)


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------


def main() -> None:
    """Run the MCP server (stdio transport for local, or SSE for hosted).

    Supports CLI args for hosted deployment:
        python -m clari_copilot_mcp.server --transport sse --port 8401 --host 0.0.0.0
    """
    import argparse

    parser = argparse.ArgumentParser(description="Clari Copilot MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"])
    parser.add_argument("--port", type=int, default=8401)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "sse":
        # Set host/port via env vars that uvicorn picks up through FastMCP
        os.environ.setdefault("UVICORN_HOST", args.host)
        os.environ.setdefault("UVICORN_PORT", str(args.port))
        os.environ.setdefault("MCP_HOST", args.host)
        os.environ.setdefault("MCP_PORT", str(args.port))
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
