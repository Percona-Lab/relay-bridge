# Clari Copilot MCP Server

Gives Claude (and other AI assistants) direct access to Clari Copilot call recordings, transcripts, AI summaries, and conversation intelligence.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Percona-Lab/relay-bridge/main/install-relay-bridge | bash
```

**Windows:**
```powershell
irm https://raw.githubusercontent.com/Percona-Lab/relay-bridge/main/install-relay-bridge.ps1 | iex
```

The installer:
- Asks you to choose **Remote** (recommended, Percona VPN required) or **Local** (your own API credentials)
- Clones the repo and sets up the Python environment
- Auto-configures Claude Desktop, Claude Code, Cursor, and Windsurf

> **VPN note:** Remote mode proxies to the shared Percona server on sherpa. When you're off VPN, the connector stays active and tool calls return a friendly "Connect to VPN" message instead of crashing.

## What it does

Once installed, Claude can:
- List and search calls by account, participant, topic, or date range
- Retrieve full call transcripts (speaker-diarized with timestamps)
- Get AI-generated summaries, key takeaways, and action items
- Find competitor mentions across calls
- Look up deals and accounts linked to calls

## Two modes

| Mode | Use case | Requires |
|---|---|---|
| **Remote** | Percona employees — shared server, always current | Percona VPN when querying |
| **Local** | Your own Clari API credentials, no VPN needed | Clari Copilot API key + secret |

## Re-run installer

To switch modes or update, re-run the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/Percona-Lab/relay-bridge/main/install-relay-bridge | bash
```

## License

Apache 2.0
