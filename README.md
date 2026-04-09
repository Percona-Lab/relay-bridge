# Clari Copilot MCP Server

MCP server that provides direct access to Clari Copilot call transcripts, AI summaries, and metadata. Built for SHERPA and other AI infrastructure to surface trends from customer-facing calls.

## Tools

| Tool | Description |
|------|-------------|
| `list_calls` | List recent calls with date/tag/user filters |
| `get_call` | Get detailed metadata for a specific call |
| `get_transcript` | Get full speaker-diarized transcript |
| `get_summary` | Get AI-generated Smart Summary (topics, action items, next steps) |
| `get_deal_calls` | Get all calls linked to a CRM deal |
| `list_tags` | List available call tags for filtering |
| `search_calls` | Search calls by keyword (title, participants) |
| `get_recent_summaries` | Batch-fetch summaries for last N days |

## Setup

### 1. Get API credentials from Clari Copilot

Ask your Clari Copilot admin (Sakshi) to:
1. Go to Clari Copilot admin panel > Settings > Integrations > API
2. Generate an API key
3. Note the API base URL

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your CLARI_API_KEY
```

### 3. Install and run

**Local (Claude Code):**
```bash
cd clari-copilot-mcp
pip install -e .
clari-copilot-mcp
```

**Or add to Claude Code MCP config** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "clari-copilot": {
      "command": "python",
      "args": ["-m", "clari_copilot_mcp.server"],
      "cwd": "/path/to/clari-copilot-mcp",
      "env": {
        "CLARI_API_KEY": "your-key-here"
      }
    }
  }
}
```

**SHERPA-hosted:** Deploy as a service with SSE transport — same codebase, just set `MCP_TRANSPORT=sse` and expose on a port.

## Architecture

```
clari-copilot-mcp/
  src/clari_copilot_mcp/
    config.py      # Pydantic settings (env vars / .env)
    client.py      # Async Clari Copilot API client
    server.py      # MCP server with FastMCP tools
```

## Future: Slack Integration

Phase 2 will add a Slack app that posts full call summaries to #clari-copilot-summaries, replacing the current metadata-only alerts. Requires a Slack bot token with `chat:write` scope.

## Credentials Needed

To activate, provide:
- **CLARI_API_KEY** — from Clari Copilot admin panel (Settings > Integrations > API)
- **CLARI_BASE_URL** — confirm with Clari support (likely `https://api.copilot.clari.com/v1` or legacy `https://api.wingman-web.com/v1`)
