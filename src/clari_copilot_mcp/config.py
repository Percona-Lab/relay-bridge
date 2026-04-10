import os
from pathlib import Path

from dotenv import load_dotenv

# CAIRN DOTENV_PATH pattern: load .env from the path specified in the
# DOTENV_PATH env var, falling back to cwd/.env or package-relative .env.
_pkg_dir = Path(__file__).resolve().parent.parent.parent
_dotenv_path = os.getenv("DOTENV_PATH", "")

if _dotenv_path and Path(_dotenv_path).is_file():
    load_dotenv(Path(_dotenv_path))
else:
    for _candidate in [Path.cwd() / ".env", _pkg_dir / ".env"]:
        if _candidate.is_file():
            load_dotenv(_candidate)
            break
    else:
        load_dotenv()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the Clari Copilot MCP server.

    Set via environment variables or a .env file:
        CLARI_API_KEY=your-api-key
        CLARI_API_PASSWORD=your-api-password
        CLARI_BASE_URL=https://rest-api.copilot.clari.com
    """

    clari_api_key: str = ""
    clari_api_password: str = ""
    clari_base_url: str = "https://rest-api.copilot.clari.com"

    # Future: Slack integration
    slack_bot_token: str = ""
    slack_channel_id: str = "C0APW0L41QF"
