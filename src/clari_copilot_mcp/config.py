from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the Clari Copilot MCP server.

    Set via environment variables or a .env file:
        CLARI_API_KEY=your-api-key
        CLARI_BASE_URL=https://api.copilot.clari.com/v1
        SLACK_BOT_TOKEN=xoxb-...  (optional, for future Slack posting)
        SLACK_CHANNEL_ID=C0APW0L41QF  (optional)
    """

    clari_api_key: str = ""
    clari_base_url: str = "https://api.copilot.clari.com/v1"

    # Future: Slack integration
    slack_bot_token: str = ""
    slack_channel_id: str = "C0APW0L41QF"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
