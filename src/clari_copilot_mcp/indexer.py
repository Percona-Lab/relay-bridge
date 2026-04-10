"""Indexer: fetches calls from Clari Copilot API and builds the tag index.

Designed to be called from MCP tools (async), the installer, or standalone:

    # Standalone with live progress:
    python -m clari_copilot_mcp.indexer --days 90

    # From MCP tool (async, no terminal output):
    result = await build_index(days=90)

Rate limit aware: 10 req/sec, 100k/week. Uses asyncio.sleep between
detail fetches to stay well under limits.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import date, timedelta
from typing import Callable

from .client import ClariCopilotClient
from .config import Settings
from .index import CallIndex, IndexedCall
from .tagger import tag_call


def _terminal_progress(indexed: int, total: int, call_id: str, title: str, errors: int, skipped: int) -> None:
    """Print a carriage-return progress line to stderr."""
    pct = (indexed / total * 100) if total else 0
    short_title = (title[:40] + "...") if len(title) > 43 else title
    sys.stderr.write(
        f"\r  [{indexed}/{total}] {pct:5.1f}%  "
        f"err={errors} skip={skipped}  "
        f"{short_title:<45}"
    )
    sys.stderr.flush()


async def build_index(
    days: int = 90,
    max_calls: int = 5000,
    skip_existing: bool = True,
    fetch_delay: float = 0.15,
    on_progress: Callable | None = None,
) -> dict:
    """Build or update the call intelligence index.

    Args:
        days: How many days back to index (default 90).
        max_calls: Max calls to fetch from the API (default 5000).
        skip_existing: Skip calls already in the index (default True).
        fetch_delay: Seconds between detail fetches (rate limit safety).
        on_progress: Optional callback(indexed, total, call_id, title, errors, skipped).

    Returns:
        Dict with stats: total_fetched, newly_indexed, skipped, errors.
    """
    settings = Settings()
    client = ClariCopilotClient(settings)
    index = CallIndex()

    to_dt = date.today()
    from_dt = to_dt - timedelta(days=days)
    t0 = time.monotonic()

    # Phase 1: Fetch all call metadata via pagination
    all_calls = []
    skip = 0
    page_size = 100

    if on_progress:
        sys.stderr.write(f"  Fetching call list ({from_dt} to {to_dt})...\n")

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

        if on_progress:
            pagination = result.get("pagination", {})
            total_avail = pagination.get("totalCalls", "?")
            sys.stderr.write(f"\r  Fetched {len(all_calls)} call headers (of {total_avail})...")
            sys.stderr.flush()

        # Check if we've fetched all available
        pagination = result.get("pagination", {})
        total_available = pagination.get("totalCalls", 0)
        if total_available and skip >= total_available:
            break

        await asyncio.sleep(fetch_delay)

    if on_progress:
        sys.stderr.write(f"\n  {len(all_calls)} calls found. Fetching details and tagging...\n")

    # Phase 2: For each call, fetch details and tag
    existing_ids = index.all_call_ids()
    to_index = []
    skipped_count = 0
    for call in all_calls:
        call_id = call.get("id", "")
        if not call_id:
            continue
        if skip_existing and call_id in existing_ids:
            skipped_count += 1
            continue
        to_index.append(call)

    if on_progress:
        sys.stderr.write(f"  {len(to_index)} new calls to index, {skipped_count} already indexed.\n")
        if not to_index:
            sys.stderr.write("  Nothing to do.\n")

    newly_indexed = 0
    errors = 0
    batch: list[IndexedCall] = []
    batch_size = 50

    for i, call in enumerate(to_index):
        call_id = call.get("id", "")
        title = call.get("title", "")

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
                title=title,
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
                title=title,
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

        except Exception as e:
            errors += 1
            if on_progress:
                sys.stderr.write(f"\n  ! Error on {call_id}: {e}\n")

        if on_progress:
            _terminal_progress(newly_indexed, len(to_index), call_id, title, errors, skipped_count)

        # Rate limit: ~6 req/sec (well under 10/sec limit)
        await asyncio.sleep(fetch_delay)

    # Flush remaining
    if batch:
        index.upsert_batch(batch)

    await client.close()

    elapsed = time.monotonic() - t0
    stats = {
        "total_api_calls": len(all_calls),
        "newly_indexed": newly_indexed,
        "skipped_existing": skipped_count,
        "errors": errors,
        "index_total": index.count(),
        "index_path": str(index.path),
        "elapsed_sec": round(elapsed, 1),
    }

    if on_progress:
        sys.stderr.write(f"\n\n  Done in {elapsed:.0f}s. "
                         f"Indexed {newly_indexed} new calls, "
                         f"{skipped_count} skipped, {errors} errors. "
                         f"Total in index: {index.count()}\n"
                         f"  Index: {index.path}\n\n")

    return stats


# ── CLI entry point ────────────────────────────────────────────────

def main() -> None:
    """Run the indexer from the command line with live progress."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build/update the Clari Copilot call intelligence index",
    )
    parser.add_argument("--days", type=int, default=90,
                        help="Days back to index (default: 90)")
    parser.add_argument("--max-calls", type=int, default=5000,
                        help="Max calls to fetch (default: 5000)")
    parser.add_argument("--full", action="store_true",
                        help="Full rebuild (re-index existing calls)")
    args = parser.parse_args()

    print(f"\n  Clari Copilot Index Builder")
    print(f"  Days: {args.days}  Max: {args.max_calls}  Mode: {'full rebuild' if args.full else 'incremental'}\n")

    result = asyncio.run(build_index(
        days=args.days,
        max_calls=args.max_calls,
        skip_existing=not args.full,
        on_progress=_terminal_progress,
    ))


if __name__ == "__main__":
    main()
