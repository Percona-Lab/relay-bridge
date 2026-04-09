#!/usr/bin/env python3
"""Interactive installer for the Clari Copilot MCP server.

Usage:
    curl -fsSL https://raw.githubusercontent.com/Percona-Lab/relay-bridge/main/installer.py | python3 -
    # or
    python3 installer.py
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ── Colours ──────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
NC = "\033[0m"

REPO_URL = "https://github.com/Percona-Lab/relay-bridge.git"
DEFAULT_INSTALL_DIR = Path.home() / "relay-bridge"
MCP_SERVER_NAME = "clari-copilot"


# ── Helpers ──────────────────────────────────────────────────────────

def info(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")
    sys.exit(1)


def header(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{NC}")
    print(f"  {BOLD}{msg}{NC}")
    print(f"{BOLD}{CYAN}{'─' * 60}{NC}\n")


def ask(prompt: str, default: str = "") -> str:
    display_default = f" [{default}]" if default else ""
    try:
        value = input(f"  {prompt}{display_default}: ").strip()
        return value if value else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_yn(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        value = input(f"  {prompt} ({hint}): ").strip().lower()
        if not value:
            return default
        return value in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_secret(prompt: str, default: str = "") -> str:
    display_default = " [****]" if default else ""
    try:
        value = getpass.getpass(f"  {prompt}{display_default}: ").strip()
        return value if value else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def find_uv() -> str | None:
    uv = shutil.which("uv")
    if uv:
        return uv
    # Common install locations
    for p in [Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv"]:
        if p.exists():
            return str(p)
    return None


# ── Steps ────────────────────────────────────────────────────────────

def step_welcome() -> None:
    header("Clari Copilot MCP Server — Installer")
    print(f"  This will set up an MCP server that gives AI agents direct")
    print(f"  access to Clari Copilot call transcripts, summaries, and")
    print(f"  conversation intelligence data.\n")
    print(f"  {DIM}Repo: {REPO_URL}{NC}")
    print(f"  {DIM}API docs: https://api-doc.copilot.clari.com{NC}\n")


def step_collect_credentials() -> dict[str, str]:
    header("Clari Copilot API Credentials")
    print(f"  Find these in your Clari Copilot workspace:")
    print(f"  {DIM}Settings → Integrations → Clari Copilot API{NC}\n")

    api_key = ask_secret("API Key")
    if not api_key:
        fail("API Key is required. Get it from Copilot workspace settings.")

    api_password = ask_secret("API Password")
    if not api_password:
        fail("API Password is required. Get it from Copilot workspace settings.")

    # Validate credentials
    print(f"\n  {DIM}Validating credentials...{NC}")
    try:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            "https://rest-api.copilot.clari.com/users",
            headers={
                "X-Api-Key": api_key,
                "X-Api-Password": api_password,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            user_count = len(data.get("users", []))
            info(f"Credentials valid — {user_count} users found in workspace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            fail(f"Authentication failed (HTTP {e.code}). Check your API key and password.")
        else:
            warn(f"Could not validate (HTTP {e.code}) — continuing anyway")
    except Exception as e:
        warn(f"Could not validate ({e}) — continuing anyway")

    return {
        "CLARI_API_KEY": api_key,
        "CLARI_API_PASSWORD": api_password,
        "CLARI_BASE_URL": "https://rest-api.copilot.clari.com",
    }


def step_install(install_dir: Path) -> Path:
    header("Installing")

    uv = find_uv()

    # Clone or update repo
    if (install_dir / ".git").exists():
        info(f"Repo exists at {install_dir} — pulling latest...")
        run(["git", "-C", str(install_dir), "pull", "--ff-only"])
    else:
        print(f"  Cloning to {install_dir}...")
        result = run(["git", "clone", REPO_URL, str(install_dir)])
        if result.returncode != 0:
            fail(f"git clone failed: {result.stderr}")
        info("Cloned successfully")

    # Create venv and install
    if uv:
        info(f"Using uv: {uv}")
        run([uv, "venv", str(install_dir / ".venv")], cwd=str(install_dir))
        result = run([uv, "pip", "install", "-e", "."], cwd=str(install_dir))
    else:
        info("Using pip (uv not found)")
        run([sys.executable, "-m", "venv", str(install_dir / ".venv")], cwd=str(install_dir))
        pip = str(install_dir / ".venv" / "bin" / "pip")
        if platform.system() == "Windows":
            pip = str(install_dir / ".venv" / "Scripts" / "pip.exe")
        result = run([pip, "install", "-e", "."], cwd=str(install_dir))

    if result.returncode != 0:
        fail(f"Install failed: {result.stderr}")

    info("Dependencies installed")

    # Determine python path
    if platform.system() == "Windows":
        python_path = install_dir / ".venv" / "Scripts" / "python.exe"
    else:
        python_path = install_dir / ".venv" / "bin" / "python"

    return python_path


def step_write_env(install_dir: Path, env: dict[str, str]) -> Path:
    env_path = install_dir / ".env"
    lines = [f"{k}={v}" for k, v in env.items() if v]
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)
    info(f"Credentials saved to {env_path} (mode 600)")
    return env_path


def step_configure_claude_code(install_dir: Path, python_path: Path) -> bool:
    header("Claude Code Configuration")

    settings_path = Path.home() / ".claude" / "settings.json"

    if not settings_path.parent.exists():
        if not ask_yn("Claude Code config dir not found. Create it?", default=True):
            warn("Skipping Claude Code configuration")
            return False
        settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config
    config: dict = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            warn(f"Could not parse {settings_path} — will merge carefully")
            config = {}

    # Build MCP entry
    mcp_entry = {
        "command": str(python_path),
        "args": ["-m", "clari_copilot_mcp.server"],
        "env": {
            "DOTENV_PATH": str(install_dir / ".env"),
        },
    }

    config.setdefault("mcpServers", {})

    # Remove DISABLED version if present
    config["mcpServers"].pop(f"DISABLED-{MCP_SERVER_NAME}", None)
    config["mcpServers"][MCP_SERVER_NAME] = mcp_entry

    # Add permission auto-allow
    config.setdefault("permissions", {})
    config["permissions"].setdefault("allow", [])
    perm = f"mcp__{MCP_SERVER_NAME}__*"
    if perm not in config["permissions"]["allow"]:
        config["permissions"]["allow"].append(perm)

    settings_path.write_text(json.dumps(config, indent=2) + "\n")
    info(f"Configured Claude Code: {settings_path}")
    info(f"MCP server name: {BOLD}{MCP_SERVER_NAME}{NC}")
    return True


def step_verify(python_path: Path) -> None:
    header("Verification")

    result = run([
        str(python_path), "-c",
        "from clari_copilot_mcp.server import mcp; "
        "tools = list(mcp._tool_manager._tools.keys()); "
        "print(f'{len(tools)} tools: {', '.join(tools)}')"
    ])

    if result.returncode == 0:
        info(result.stdout.strip())
    else:
        warn(f"Verification failed: {result.stderr.strip()}")


def step_done() -> None:
    header("Setup Complete")
    print(f"  {GREEN}{BOLD}The Clari Copilot MCP server is ready.{NC}\n")
    print(f"  Restart Claude Code to pick up the new MCP server.")
    print(f"  Then try asking:\n")
    print(f"    {DIM}\"List recent Clari Copilot calls from the past week\"{NC}")
    print(f"    {DIM}\"Get the transcript and summary for call <id>\"{NC}")
    print(f"    {DIM}\"Search calls mentioning PostgreSQL\"{NC}")
    print(f"    {DIM}\"Get summaries for all calls in the last 7 days\"{NC}\n")


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    step_welcome()

    # Install location
    install_dir = Path(ask("Install directory", str(DEFAULT_INSTALL_DIR)))
    install_dir = install_dir.expanduser().resolve()

    # Credentials
    env = step_collect_credentials()

    # Install
    python_path = step_install(install_dir)

    # Write .env
    step_write_env(install_dir, env)

    # Configure Claude Code
    step_configure_claude_code(install_dir, python_path)

    # Verify
    step_verify(python_path)

    # Done
    step_done()


if __name__ == "__main__":
    main()
