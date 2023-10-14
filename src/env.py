import os

from dotenv import load_dotenv

load_dotenv()


def ensure_string(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Environment variable {name} is not set.")
    return value


GSPREAD_PRIVATE_KEY = ensure_string("GSPREAD_PRIVATE_KEY")
GSPREAD_PRIVATE_KEY_ID = ensure_string("GSPREAD_PRIVATE_KEY_ID")
GSPREAD_SERVICE_ACCOUNT_EMAIL = ensure_string("GSPREAD_SERVICE_ACCOUNT_EMAIL")
GSPREAD_TOKEN_URI = ensure_string("GSPREAD_TOKEN_URI")
DISCORD_TOKEN = ensure_string("DISCORD_TOKEN")
GUILD_ID = int(ensure_string("GUILD_ID"))
GITHUB_TOKEN = ensure_string("GITHUB_TOKEN")
