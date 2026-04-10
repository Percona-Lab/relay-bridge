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

# Names to look for when cleaning up previous installations
LEGACY_MCP_NAMES = [
    "clari-copilot",
    "DISABLED-clari-copilot",
    "relay-bridge",
    "DISABLED-relay-bridge",
]


# ── Helpers ──────────────────────────────────────────────────────────

def _reopen_tty() -> None:
    """Reopen stdin from /dev/tty when running via curl | python.

    When the installer is piped (curl ... | python3 -), stdin is the pipe
    and input()/getpass() hit EOF immediately. Reopening from /dev/tty
    restores interactive prompts. This is the CAIRN doc-search pattern.
    """
    if not sys.stdin.isatty():
        try:
            sys.stdin = open("/dev/tty", "r")
        except OSError:
            pass  # Windows or no TTY — prompts will use defaults


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
        # getpass reads from /dev/tty by default on Unix, so it works
        # even when stdin is a pipe — but we need our fallback wrapper
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


def step_cleanup_previous(install_dir: Path) -> None:
    """Detect and remove previous installations."""
    header("Checking for Previous Installation")

    found_previous = False
    old_dirs: list[Path] = []

    # 1. Check both AI client configs for old MCP entries
    config_files: list[tuple[Path, str]] = [
        (Path.home() / ".claude" / "settings.json", "Claude Code"),
    ]
    if platform.system() == "Darwin":
        config_files.append((
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            "Claude Desktop",
        ))
    elif platform.system() == "Windows":
        config_files.append((
            Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json",
            "Claude Desktop",
        ))

    for cfg_path, cfg_label in config_files:
        if not cfg_path.exists():
            continue
        try:
            config = json.loads(cfg_path.read_text())
            servers = config.get("mcpServers", {})
            for name in LEGACY_MCP_NAMES:
                if name in servers:
                    entry = servers[name]
                    # Extract the old install dir from the command or env
                    cmd = entry.get("command", "")
                    env_path = entry.get("env", {}).get("DOTENV_PATH", "")
                    old_dir = None
                    if env_path:
                        old_dir = Path(env_path).parent
                    elif cmd:
                        # command is like /path/to/.venv/bin/python
                        p = Path(cmd)
                        if ".venv" in p.parts:
                            idx = p.parts.index(".venv")
                            old_dir = Path(*p.parts[:idx])

                    found_previous = True
                    info(f"Found existing MCP entry: {BOLD}{name}{NC} ({cfg_label})")
                    if old_dir and old_dir.exists() and old_dir != install_dir:
                        if old_dir not in old_dirs:
                            print(f"    {DIM}Directory: {old_dir}{NC}")
                            old_dirs.append(old_dir)

        except (json.JSONDecodeError, Exception):
            pass

    # 2. Check common install locations
    for candidate in [
        Path.home() / "relay-bridge",
        Path.home() / "Playground" / "clari-copilot-mcp",
        Path.home() / "clari-copilot-mcp",
    ]:
        if candidate.exists() and candidate != install_dir and candidate not in old_dirs:
            if (candidate / "src" / "clari_copilot_mcp").exists() or (candidate / "spec.yaml").exists():
                found_previous = True
                info(f"Found previous install at: {candidate}")
                old_dirs.append(candidate)

    if not found_previous:
        info("No previous installation found — clean install")
        return

    # 3. Offer to clean up
    print()
    if old_dirs and ask_yn("Remove old installation directories?", default=True):
        for d in old_dirs:
            # Preserve .env if it exists (in case user wants to recover creds)
            old_env = d / ".env"
            if old_env.exists():
                backup = d.parent / f".env.{d.name}.backup"
                shutil.copy2(str(old_env), str(backup))
                info(f"Backed up credentials: {backup}")

            shutil.rmtree(str(d))
            info(f"Removed: {d}")

    # 4. Clean up old MCP entries from all config files (will be re-added later)
    for cfg_path, cfg_label in config_files:
        if not cfg_path.exists():
            continue
        try:
            config = json.loads(cfg_path.read_text())
            servers = config.get("mcpServers", {})
            removed = []
            for name in LEGACY_MCP_NAMES:
                if name in servers:
                    del servers[name]
                    removed.append(name)
            if removed:
                cfg_path.write_text(json.dumps(config, indent=2) + "\n")
                info(f"Removed old MCP entries from {cfg_label}: {', '.join(removed)}")
        except (json.JSONDecodeError, Exception):
            pass


def step_collect_credentials() -> dict[str, str]:
    header("Clari Copilot API Credentials")
    print(f"  Find these in your Clari Copilot workspace:")
    print(f"  {DIM}Settings → Integrations → Clari Copilot API{NC}")
    print(f"  {DIM}Use the clipboard icon to copy each value.{NC}\n")

    api_key = ask("API Key").strip()
    if not api_key:
        fail("API Key is required. Get it from Copilot workspace settings.")

    api_secret = ask_secret("API Secret").strip()
    if not api_secret:
        fail("API Secret is required. Get it from Copilot workspace settings.")

    # Show what we captured (masked) so user can spot issues
    print(f"\n  {DIM}Key:    {api_key[:6]}...{api_key[-4:]} ({len(api_key)} chars){NC}")
    print(f"  {DIM}Secret: {'*' * 6}...{api_secret[-4:]} ({len(api_secret)} chars){NC}")

    # Validate credentials
    print(f"\n  {DIM}Validating...{NC}")
    base_url = "https://rest-api.copilot.clari.com"
    try:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            f"{base_url}/calls?limit=1&includePagination=false",
            headers={
                "X-Api-Key": api_key,
                "X-Api-Password": api_secret,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            info(f"Connected — API returned data successfully")

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        print()
        warn(f"HTTP {e.code}: {body or 'Forbidden'}")
        print(f"\n  {DIM}Troubleshooting:{NC}")
        print(f"  {DIM}1. Copy the API Key using the clipboard icon (not by selecting text){NC}")
        print(f"  {DIM}2. Click the eye icon to reveal the API Secret, then copy it{NC}")
        print(f"  {DIM}3. Make sure there are no extra spaces or newlines{NC}\n")
        if not ask_yn("Continue anyway with these credentials?", default=True):
            fail("Aborted. Fix credentials and re-run the installer.")

    except Exception as e:
        warn(f"Could not validate ({e}) — continuing anyway")

    return {
        "CLARI_API_KEY": api_key,
        "CLARI_API_PASSWORD": api_secret,
        "CLARI_BASE_URL": base_url,
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


def _configure_json_file(
    config_path: Path,
    mcp_entry: dict,
    label: str,
    add_permissions: bool = False,
) -> bool:
    """Add the MCP server entry to a JSON config file."""
    if not config_path.parent.exists():
        if not ask_yn(f"{label} config dir not found. Create it?", default=True):
            warn(f"Skipping {label} configuration")
            return False
        config_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            warn(f"Could not parse {config_path} — will merge carefully")
            config = {}

    config.setdefault("mcpServers", {})

    # Remove legacy entries
    for name in LEGACY_MCP_NAMES:
        config["mcpServers"].pop(name, None)

    # Add the active entry
    config["mcpServers"][MCP_SERVER_NAME] = mcp_entry

    # Add permission auto-allow (Claude Code settings.json only)
    if add_permissions:
        config.setdefault("permissions", {})
        config["permissions"].setdefault("allow", [])
        perm = f"mcp__{MCP_SERVER_NAME}__*"
        if perm not in config["permissions"]["allow"]:
            config["permissions"]["allow"].append(perm)

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    info(f"Configured {label}: {config_path}")
    return True


def step_configure_ai_clients(install_dir: Path, python_path: Path) -> bool:
    header("AI Client Configuration")

    mcp_entry = {
        "command": str(python_path),
        "args": ["-m", "clari_copilot_mcp.server"],
        "env": {
            "DOTENV_PATH": str(install_dir / ".env"),
        },
    }

    any_configured = False

    # 1. Claude Code — ~/.claude/settings.json
    code_path = Path.home() / ".claude" / "settings.json"
    if code_path.parent.exists():
        info("Claude Code detected")
        if _configure_json_file(code_path, mcp_entry, "Claude Code", add_permissions=True):
            any_configured = True
    else:
        print(f"  {DIM}Claude Code not detected ({code_path.parent}){NC}")
        if ask_yn("Configure Claude Code anyway?", default=False):
            if _configure_json_file(code_path, mcp_entry, "Claude Code", add_permissions=True):
                any_configured = True

    # 2. Claude Desktop — ~/Library/Application Support/Claude/claude_desktop_config.json
    if platform.system() == "Darwin":
        desktop_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif platform.system() == "Windows":
        desktop_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    else:
        desktop_path = Path.home() / ".config" / "claude" / "claude_desktop_config.json"

    if desktop_path.parent.exists():
        info("Claude Desktop detected")
        if _configure_json_file(desktop_path, mcp_entry, "Claude Desktop"):
            any_configured = True
    else:
        print(f"  {DIM}Claude Desktop not detected ({desktop_path.parent}){NC}")

    if any_configured:
        info(f"MCP server name: {BOLD}{MCP_SERVER_NAME}{NC}")

    return any_configured


def step_verify(python_path: Path) -> None:
    header("Verification")

    result = run([
        str(python_path), "-c",
        (
            "from clari_copilot_mcp.server import mcp; "
            "tools = list(mcp._tool_manager._tools.keys()); "
            "print(f'{len(tools)} tools loaded: ' + ', '.join(tools))"
        ),
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
    _reopen_tty()
    step_welcome()

    # Install location
    install_dir = Path(ask("Install directory", str(DEFAULT_INSTALL_DIR)))
    install_dir = install_dir.expanduser().resolve()

    # Clean up previous installations
    step_cleanup_previous(install_dir)

    # Credentials
    env = step_collect_credentials()

    # Install
    python_path = step_install(install_dir)

    # Write .env
    step_write_env(install_dir, env)

    # Configure AI clients (Claude Code + Claude Desktop)
    step_configure_ai_clients(install_dir, python_path)

    # Verify
    step_verify(python_path)

    # Done
    step_done()


if __name__ == "__main__":
    main()
