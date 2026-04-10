"""Lightweight call intelligence index.

Stores thin metadata + tags per call in a single JSON file.
Full summaries are fetched on demand via the existing MCP tools.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Index record ───────────────────────────────────────────────────

@dataclass
class IndexedCall:
    call_id: str
    title: str
    date: str  # ISO 8601 date (YYYY-MM-DD)
    time: str  # ISO 8601 full timestamp
    account_name: str
    deal_name: str
    users: list[str]  # internal user emails
    external_participants: list[str]  # external names
    duration_sec: int
    product_areas: list[str]
    customer_type: str
    market_signals: list[str]
    indexed_at: str = ""  # when this record was created/updated


# ── Index storage ──────────────────────────────────────────────────

def _default_index_path() -> Path:
    """Index file lives next to the .env / project root."""
    env_path = os.getenv("DOTENV_PATH", "")
    if env_path:
        return Path(env_path).parent / "call_index.json"
    return Path(__file__).resolve().parent.parent.parent / "call_index.json"


class CallIndex:
    """In-memory index backed by a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_index_path()
        self._calls: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._calls = {c["call_id"]: c for c in data.get("calls", [])}
            except (json.JSONDecodeError, KeyError):
                self._calls = {}

    def _save(self) -> None:
        data = {
            "version": 1,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "count": len(self._calls),
            "calls": list(self._calls.values()),
        }
        self.path.write_text(json.dumps(data, indent=1, default=str) + "\n")

    def upsert(self, call: IndexedCall) -> None:
        call.indexed_at = datetime.utcnow().isoformat() + "Z"
        self._calls[call.call_id] = asdict(call)

    def upsert_batch(self, calls: list[IndexedCall]) -> int:
        for call in calls:
            self.upsert(call)
        self._save()
        return len(calls)

    def get(self, call_id: str) -> dict | None:
        return self._calls.get(call_id)

    def has(self, call_id: str) -> bool:
        return call_id in self._calls

    def count(self) -> int:
        return len(self._calls)

    def all_call_ids(self) -> set[str]:
        return set(self._calls.keys())

    # ── Query ──────────────────────────────────────────────────────

    def query(
        self,
        product_areas: list[str] | None = None,
        customer_type: str | None = None,
        market_signals: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        text_search: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query the index with filters. Returns matching call records."""
        results = []
        text_lower = text_search.lower() if text_search else None

        for call in self._calls.values():
            # Product area filter (any match)
            if product_areas:
                if not any(p in call.get("product_areas", []) for p in product_areas):
                    continue

            # Customer type filter (exact match)
            if customer_type:
                if call.get("customer_type", "") != customer_type:
                    continue

            # Market signal filter (any match)
            if market_signals:
                if not any(s in call.get("market_signals", []) for s in market_signals):
                    continue

            # Date range filter
            call_date = call.get("date", "")
            if date_from and call_date < date_from:
                continue
            if date_to and call_date > date_to:
                continue

            # Text search (title + account + deal + users + participants)
            if text_lower:
                searchable = " ".join([
                    call.get("title", ""),
                    call.get("account_name", ""),
                    call.get("deal_name", ""),
                    " ".join(call.get("users", [])),
                    " ".join(call.get("external_participants", [])),
                ]).lower()
                if text_lower not in searchable:
                    continue

            results.append(call)
            if len(results) >= limit:
                break

        return results

    # ── Stats ──────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the index."""
        if not self._calls:
            return {"total_calls": 0}

        product_counts: dict[str, int] = {}
        customer_counts: dict[str, int] = {}
        signal_counts: dict[str, int] = {}
        dates: list[str] = []

        for call in self._calls.values():
            for p in call.get("product_areas", []):
                product_counts[p] = product_counts.get(p, 0) + 1
            ct = call.get("customer_type", "Unknown")
            customer_counts[ct] = customer_counts.get(ct, 0) + 1
            for s in call.get("market_signals", []):
                signal_counts[s] = signal_counts.get(s, 0) + 1
            if call.get("date"):
                dates.append(call["date"])

        dates.sort()
        return {
            "total_calls": len(self._calls),
            "date_range": {
                "earliest": dates[0] if dates else None,
                "latest": dates[-1] if dates else None,
            },
            "by_product_area": dict(sorted(product_counts.items(), key=lambda x: -x[1])),
            "by_customer_type": dict(sorted(customer_counts.items(), key=lambda x: -x[1])),
            "by_market_signal": dict(sorted(signal_counts.items(), key=lambda x: -x[1])),
            "untagged_product": sum(1 for c in self._calls.values() if not c.get("product_areas")),
            "untagged_signal": sum(1 for c in self._calls.values() if not c.get("market_signals")),
        }
