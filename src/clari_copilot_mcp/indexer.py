"""Indexer: fetches calls from Clari Copilot API and builds the tag index.

Designed to be called from MCP tools (async) or as a standalone script.
Fetches call metadata via list_calls, then fetches details (summary) for
unindexed calls. Tags each call and upserts into the index.

Rate limit aware: 10 req/sec, 100k/week. Uses asyncio.sleep between
detail fetches to stay well under limits.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from .client import ClariCopilotClient
from .config import Settings
from .index import CallIndex, IndexedCall
from .tagger import tag_call


async def build_index(
    days: int = 90,
    max_calls: int = 5000,
    skip_existing: bool = True,
    fetch_delay: float = 0.15,
    on_progress: callable = None,
) -> dict:
    """Build or update the call intelligence index.

    Args:
        days: How many days back to index (default 90).
        max_calls: Max calls to fetch from the API (default 5000).
        skip_existing: Skip calls already in the index (default True).
        fetch_delay: Seconds between detail fetches (rate limit safety).
        on_progress: Optional callback(indexed, total, call_id) for progress.

    Returns:
        Dict with stats: total_fetched, newly_indexed, skipped, errors.
    """
    settings = Settings()
    client = ClariCopilotClient(settings)
    index = CallIndex()

    to_dt = date.today()
    from_dt = to_dt - timedelta(days=days)

    # Phase 1: Fetch all call metadata via pagination
    all_calls = []
    skip = 0
    page_size = 100

    while len(all_calls) < max_calls:
        result = await client.list_calls(
            filter_time_gt=f"{from_dt}T00:00:00Z",
            filter_time_lt=f"{to_dt}T23:59:59Z",
            filter_duration_gt=120,  # skip <2min calls
            skip=skip,
            limit=page_size,
            sort_time="desc",
            include_pagination=True,
        )
        calls = result.get("calls", [])
        if not calls:
            break
        all_calls.extend(calls)
        skip += page_size

        # Check if we've fetched all available
        pagination = result.get("pagination", {})
        total_available = pagination.get("totalCalls", 0)
        if total_available and skip >= total_available:
            break

        await asyncio.sleep(fetch_delay)

    # Phase 2: For each call, fetch details and tag
    existing_ids = index.all_call_ids()
    newly_indexed = 0
    skipped = 0
    errors = 0
    batch: list[IndexedCall] = []
    batch_size = 50

    for i, call in enumerate(all_calls):
        call_id = call.get("id", "")
        if not call_id:
            continue

        if skip_existing and call_id in existing_ids:
            skipped += 1
            continue

        try:
            # Fetch call details for summary
            details = await client.get_call_details(call_id)
            detail_call = details.get("call", details)

            summary = detail_call.get("summary", {})
            summary_text = summary.get("full_summary", "")
            topics_text = " ".join(
                t.get("name", "") + " " + t.get("summary", "")
                for t in summary.get("topics_discussed", [])
            )
            action_items_text = " ".join(
                a.get("action_item", "")
                for a in summary.get("key_action_items", [])
            )
            competitor_sentiments = detail_call.get("competitor_sentiments", [])

            # Tag the call
            tags = tag_call(
                title=call.get("title", ""),
                deal_name=call.get("deal_name", ""),
                account_name=call.get("account_name", ""),
                summary_text=summary_text,
                topics_text=topics_text,
                action_items_text=action_items_text,
                competitor_sentiments=competitor_sentiments,
            )

            # Extract metadata
            call_time = call.get("time", "")
            call_date = call_time[:10] if call_time else ""
            users = [u.get("userEmail", "") for u in call.get("users", []) if u.get("userEmail")]
            ext_participants = [
                p.get("name", p.get("email", ""))
                for p in call.get("externalParticipants", [])
            ]
            duration = call.get("metrics", {}).get("call_duration", 0)
            if isinstance(duration, str):
                try:
                    duration = int(float(duration))
                except ValueError:
                    duration = 0

            record = IndexedCall(
                call_id=call_id,
                title=call.get("title", ""),
                date=call_date,
                time=call_time,
                account_name=call.get("account_name", ""),
                deal_name=call.get("deal_name", ""),
                users=users,
                external_participants=ext_participants,
                duration_sec=duration,
                product_areas=tags.product_areas,
                customer_type=tags.customer_type,
                market_signals=tags.market_signals,
            )
            batch.append(record)
            newly_indexed += 1

            # Flush batch
            if len(batch) >= batch_size:
                index.upsert_batch(batch)
                batch = []

            if on_progress:
                on_progress(newly_indexed, len(all_calls) - skipped, call_id)

        except Exception:
            errors += 1

        # Rate limit: ~6 req/sec (well under 10/sec limit)
        await asyncio.sleep(fetch_delay)

    # Flush remaining
    if batch:
        index.upsert_batch(batch)

    await client.close()

    return {
        "total_api_calls": len(all_calls),
        "newly_indexed": newly_indexed,
        "skipped_existing": skipped,
        "errors": errors,
        "index_total": index.count(),
        "index_path": str(index.path),
    }
