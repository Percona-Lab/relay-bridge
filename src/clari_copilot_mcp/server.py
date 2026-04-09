"""Clari Copilot MCP Server.

Exposes Clari Copilot call data (transcripts, summaries, metadata)
as MCP tools for querying by Claude Code, SHERPA, or other AI agents.
"""

from __future__ import annotations

import json
from datetime import date

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


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@mcp.tool()
async def list_calls(
    from_date: str | None = None,
    to_date: str | None = None,
    tag: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> str:
    """List recent Clari Copilot calls with metadata.

    Args:
        from_date: Start date filter (YYYY-MM-DD). Defaults to no lower bound.
        to_date: End date filter (YYYY-MM-DD). Defaults to no upper bound.
        tag: Filter by call tag (e.g. "External", "Customer").
        user_id: Filter by the recording user/rep ID.
        page: Page number for pagination (default 1).
        per_page: Results per page (default 25, max 100).
    """
    result = await client.list_calls(
        from_date=from_date,
        to_date=to_date,
        tag=tag,
        user_id=user_id,
        page=page,
        per_page=per_page,
    )
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def get_call(call_id: str) -> str:
    """Get detailed metadata for a specific call.

    Args:
        call_id: The unique identifier of the call.
    """
    result = await client.get_call(call_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def get_transcript(call_id: str) -> str:
    """Get the full speaker-diarized transcript of a call.

    Returns timestamped utterances with speaker attribution.
    Use this to read the actual conversation content.

    Args:
        call_id: The unique identifier of the call.
    """
    result = await client.get_transcript(call_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def get_summary(call_id: str) -> str:
    """Get the AI-generated Smart Summary for a call.

    Includes key topics, action items, next steps, competitor mentions,
    and pricing discussions. Use this for a quick overview before
    pulling the full transcript.

    Args:
        call_id: The unique identifier of the call.
    """
    result = await client.get_summary(call_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def get_deal_calls(deal_id: str) -> str:
    """Get all calls associated with a CRM deal/opportunity.

    Use this to review the full conversation history for a specific deal.

    Args:
        deal_id: The CRM deal/opportunity ID.
    """
    result = await client.get_deal_calls(deal_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def list_tags() -> str:
    """List all available call tags.

    Tags can be used to filter calls (e.g. Internal vs External,
    customer-facing, etc.).
    """
    result = await client.list_tags()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def search_calls(
    query: str,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> str:
    """Search calls by keyword across titles and participants.

    This fetches calls and filters client-side by the query string.
    For large result sets, use date filters to narrow the window.

    Args:
        query: Search term to match against call titles and participant names.
        from_date: Start date filter (YYYY-MM-DD).
        to_date: End date filter (YYYY-MM-DD).
        page: Page number (default 1).
        per_page: Results per page (default 25).
    """
    result = await client.list_calls(
        from_date=from_date,
        to_date=to_date,
        page=page,
        per_page=per_page,
    )

    query_lower = query.lower()
    calls = result.get("calls", result.get("data", []))
    matched = []
    for call in calls:
        searchable = json.dumps(call).lower()
        if query_lower in searchable:
            matched.append(call)

    return json.dumps(
        {"query": query, "matches": len(matched), "calls": matched},
        indent=2,
        default=str,
    )


@mcp.tool()
async def get_recent_summaries(
    days: int = 7,
    tag: str | None = None,
    per_page: int = 50,
) -> str:
    """Get AI summaries for all recent calls in a date range.

    Fetches calls from the last N days and retrieves each summary.
    Useful for trend analysis and batch review.

    Args:
        days: Number of days to look back (default 7).
        tag: Optional tag filter (e.g. "External").
        per_page: Max calls to process (default 50).
    """
    from datetime import timedelta

    to_dt = date.today()
    from_dt = to_dt - timedelta(days=days)

    calls_result = await client.list_calls(
        from_date=from_dt,
        to_date=to_dt,
        tag=tag,
        per_page=per_page,
    )

    calls = calls_result.get("calls", calls_result.get("data", []))
    summaries = []

    for call in calls:
        call_id = call.get("id", call.get("call_id", ""))
        if not call_id:
            continue
        try:
            summary = await client.get_summary(call_id)
            summaries.append(
                {
                    "call_id": call_id,
                    "title": call.get("title", call.get("name", "Unknown")),
                    "date": call.get("date", call.get("created_at", "")),
                    "duration": call.get("duration", ""),
                    "participants": call.get("participants", []),
                    "summary": summary,
                }
            )
        except Exception as e:
            summaries.append(
                {
                    "call_id": call_id,
                    "title": call.get("title", call.get("name", "Unknown")),
                    "error": str(e),
                }
            )

    return json.dumps(
        {
            "period": f"{from_dt} to {to_dt}",
            "total_calls": len(calls),
            "summaries_retrieved": len([s for s in summaries if "summary" in s]),
            "results": summaries,
        },
        indent=2,
        default=str,
    )


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------


def main() -> None:
    """Run the MCP server (stdio transport for local, or SSE for hosted)."""
    mcp.run()


if __name__ == "__main__":
    main()
