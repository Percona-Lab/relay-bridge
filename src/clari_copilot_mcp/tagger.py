"""Keyword-based tagger for Clari Copilot calls.

Classifies calls by product area, customer type, and market signals
using title, summary, topics, deal name, and account name. No LLM
needed — fast deterministic matching for index-time tagging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Product area patterns ──────────────────────────────────────────
# Each tuple: (canonical name, list of regex patterns to match)

PRODUCT_PATTERNS: list[tuple[str, list[str]]] = [
    ("MySQL", [
        r"\bmysql\b", r"\bpercona\s*server\b", r"\bps\s*\d", r"\bpxc\b",
        r"\bpercona\s*xtradb\b", r"\bxtrabackup\b", r"\binnodb\b",
        r"\borchestrator\b", r"\bproxysql\b", r"\breplication\b",
        r"\bgroup\s*replication\b", r"\bgalera\b",
    ]),
    ("PostgreSQL", [
        r"\bpostgre", r"\bpg\s*\d", r"\bppg\b", r"\bpercona\s*postgresql\b",
        r"\bpg_stat", r"\bpgbouncer\b", r"\bpatron[i]?\b", r"\bcitus\b",
        r"\bpostgis\b",
    ]),
    ("MongoDB", [
        r"\bmongo", r"\bpsmdb\b", r"\bpercona\s*server\s*for\s*mongo",
        r"\bpbm\b", r"\bpercona\s*backup\s*for\s*mongo", r"\breplicaset\b",
        r"\bsharding\b",
    ]),
    ("PMM", [
        r"\bpmm\b", r"\bpercona\s*monitor", r"\bgrafana\b.*percona",
        r"\bquery\s*analytics\b", r"\bqan\b",
    ]),
    ("Operators", [
        r"\boperator[s]?\b", r"\bkubernetes\b", r"\bk8s\b", r"\bhelm\b",
        r"\bopenshift\b", r"\bpxc\s*operator\b", r"\bpsmdb\s*operator\b",
        r"\bpg\s*operator\b", r"\bperconalab/percona-xtradb-cluster-operator\b",
    ]),
    ("Everest", [
        r"\beverest\b", r"\bopen\s*everest\b", r"\bpercona\s*everest\b",
        r"\bdbaas\b",
    ]),
    ("Valkey", [
        r"\bvalkey\b", r"\bredis\b",
    ]),
    ("Percona Toolkit", [
        r"\bpt-", r"\bpercona\s*toolkit\b", r"\bpt_",
    ]),
    ("Pro Builds", [
        r"\bpro\s*build", r"\bpercona\s*pro\b", r"\benterprise\s*build",
    ]),
    ("Support", [
        r"\bsupport\s*(contract|renewal|agreement|ticket|case)\b",
        r"\bsla\b", r"\b24x7\b", r"\b24/7\b",
    ]),
    ("Consulting", [
        r"\bconsulting\b", r"\bprofessional\s*services\b",
        r"\bscope\s*of\s*work\b", r"\bsow\b", r"\bengagement\b",
        r"\bhealth\s*(check|audit)\b",
    ]),
    ("ExpertOps", [
        r"\bexpertops\b", r"\bmanaged\s*service", r"\bmanaged\s*db",
        r"\bdba\s*as\s*a\s*service\b",
    ]),
]

# ── Market signal patterns ─────────────────────────────────────────

SIGNAL_PATTERNS: list[tuple[str, list[str]]] = [
    ("Migration", [
        r"\bmigrat", r"\bmoving\s*(from|to|off)\b", r"\breplac(e|ing)\b",
        r"\bswitch(ing)?\s*(from|to)\b", r"\btransition\b",
    ]),
    ("Upgrade", [
        r"\bupgrad", r"\bversion\s*\d", r"\bupdate\s*(to|from)\b",
        r"\beol\b", r"\bend.of.life\b", r"\bdeprecated\b",
    ]),
    ("New Deployment", [
        r"\bnew\s*(deploy|install|setup|cluster|environment)\b",
        r"\bgreenfield\b", r"\bpoc\b", r"\bproof\s*of\s*concept\b",
        r"\bevaluat", r"\btrial\b", r"\bpilot\b",
    ]),
    ("Performance Issue", [
        r"\bperformance\b", r"\bslow\s*(query|queries)?\b", r"\blatency\b",
        r"\bthroughput\b", r"\bbottleneck\b", r"\btun(e|ing)\b",
        r"\boptimiz", r"\bcpu\s*(spike|usage|high)\b",
    ]),
    ("Cost Optimization", [
        r"\bcost\b", r"\bpric(e|ing)\b", r"\blicens", r"\bbudget\b",
        r"\bsav(e|ing)\b", r"\broi\b", r"\btco\b",
    ]),
    ("Compliance/Security", [
        r"\bcomplia", r"\bsecur", r"\baudit\b", r"\bencrypt",
        r"\bgdpr\b", r"\bhipaa\b", r"\bsoc\s*2\b", r"\bpci\b",
        r"\bfederal\b", r"\bgovernment\b",
    ]),
    ("Cloud Migration", [
        r"\bcloud\b", r"\baws\b", r"\bazure\b", r"\bgcp\b",
        r"\bgoogle\s*cloud\b", r"\brds\b", r"\baurora\b",
        r"\bon.prem.*cloud\b", r"\bcloud.*on.prem\b",
        r"\beks\b", r"\bgke\b", r"\baks\b",
    ]),
    ("HA/DR", [
        r"\bhigh\s*availab", r"\bha\b", r"\bdisaster\s*recover",
        r"\bdr\b", r"\bfailover\b", r"\bfail\s*over\b",
        r"\breplica", r"\bbackup\b", r"\brto\b", r"\brpo\b",
    ]),
    ("Competitive Eval", [
        r"\bvs\.?\s", r"\bcompet", r"\balternative\b", r"\bcompare\b",
        r"\bcomparison\b", r"\bbenchmark\b",
        r"\boracle\b", r"\bmariadb\b", r"\bcockroach\b", r"\btidb\b",
        r"\bcloudsql\b", r"\balloydb\b", r"\bplanetscale\b",
    ]),
    ("Expansion", [
        r"\bexpand", r"\bscal(e|ing)\b", r"\bgrow", r"\badditional\s*(node|instance|server|cluster)\b",
        r"\bupsell\b", r"\bcross.sell\b", r"\brenewal\b",
    ]),
    ("Churn Risk", [
        r"\bchurn\b", r"\bcancel", r"\bdiscontinue\b", r"\bnot\s*renew",
        r"\bdissatisf", r"\bunhappy\b", r"\bfrustrat",
        r"\bleaving\b", r"\bswitch\s*away\b",
    ]),
]

# ── Customer type inference ────────────────────────────────────────

# Deal name patterns from Clari: "35461\US-TX\CompanyName\Products\Stage"
_ENTERPRISE_SIGNALS = [
    r"\benterprise\b", r"\bicp\b", r"\bstrategic\b",
    r"\b(fortune|f)\s*\d{2,4}\b", r"\bglobal\b",
]
_MIDMARKET_SIGNALS = [r"\bmid.?market\b", r"\bgrowth\b"]
_SMB_SIGNALS = [r"\bsmb\b", r"\bstarter\b", r"\bsmall\b", r"\bstartup\b"]
_PROSPECT_SIGNALS = [
    r"\bnew\s*business\b", r"\bprospect\b", r"\bpoc\b",
    r"\btrial\b", r"\bevaluat",
]


def _match_any(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# ── Public API ─────────────────────────────────────────────────────


@dataclass
class CallTags:
    product_areas: list[str]
    customer_type: str
    market_signals: list[str]


def tag_call(
    title: str = "",
    deal_name: str = "",
    account_name: str = "",
    summary_text: str = "",
    topics_text: str = "",
    action_items_text: str = "",
    competitor_sentiments: list[dict] | None = None,
) -> CallTags:
    """Tag a call based on available metadata and summary text.

    All inputs are optional — the tagger uses whatever is available.
    More text = better classification.
    """
    # Combine all text for matching
    all_text = " ".join(filter(None, [
        title, deal_name, account_name,
        summary_text, topics_text, action_items_text,
    ]))

    # Product areas
    products = []
    for name, patterns in PRODUCT_PATTERNS:
        if _match_any(all_text, patterns):
            products.append(name)

    # Market signals
    signals = []
    for name, patterns in SIGNAL_PATTERNS:
        if _match_any(all_text, patterns):
            signals.append(name)

    # Add Competitive Eval if competitor_sentiments is non-empty
    if competitor_sentiments and "Competitive Eval" not in signals:
        signals.append("Competitive Eval")

    # Customer type — check deal_name first (most reliable), then all_text
    deal_text = f"{deal_name} {account_name}"
    customer_type = "Unknown"
    if _match_any(deal_text, _ENTERPRISE_SIGNALS):
        customer_type = "Enterprise/ICP"
    elif _match_any(deal_text, _MIDMARKET_SIGNALS):
        customer_type = "Mid-Market"
    elif _match_any(deal_text, _SMB_SIGNALS):
        customer_type = "SMB"
    elif _match_any(deal_text, _PROSPECT_SIGNALS):
        customer_type = "Prospect"
    elif _match_any(all_text, _ENTERPRISE_SIGNALS):
        customer_type = "Enterprise/ICP"
    elif _match_any(all_text, _PROSPECT_SIGNALS):
        customer_type = "Prospect"

    return CallTags(
        product_areas=products,
        customer_type=customer_type,
        market_signals=signals,
    )
