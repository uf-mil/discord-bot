import os
from typing import Literal, overload

from dotenv import load_dotenv

load_dotenv()


@overload
def ensure_string(name: str, optional: Literal[False] = False) -> str: ...


@overload
def ensure_string(name: str, optional: Literal[True] = True) -> str | None: ...


@overload
def ensure_string(name: str, optional: bool) -> str | None: ...


def ensure_string(name: str, optional: bool = False) -> str | None:
    value = os.getenv(name)
    if value is None and not optional:
        raise ValueError(f"Environment variable {name} is not set.")
    return value or ""


GSPREAD_PRIVATE_KEY = ensure_string("GSPREAD_PRIVATE_KEY")
GSPREAD_PRIVATE_KEY_ID = ensure_string("GSPREAD_PRIVATE_KEY_ID")
GSPREAD_SERVICE_ACCOUNT_EMAIL = ensure_string("GSPREAD_SERVICE_ACCOUNT_EMAIL")
GSPREAD_TOKEN_URI = ensure_string("GSPREAD_TOKEN_URI")
GSPREAD_SS_NAME = ensure_string("GSPREAD_SS_NAME")
DISCORD_TOKEN = ensure_string("DISCORD_TOKEN")
GUILD_ID = int(ensure_string("GUILD_ID"))
GITHUB_TOKEN = ensure_string("GITHUB_TOKEN")
LEADERS_MEETING_NOTES_URL = ensure_string("MEETING_NOTES_URL")
LEADERS_MEETING_URL = ensure_string("MEETING_URL")
DATABASE_ENGINE_URL = ensure_string("DATABASE_ENGINE_URL")

# Calendars
GENERAL_CALENDAR = ensure_string("GENERAL_CALENDAR", True)
SOFTWARE_MEETINGS_CALENDAR = ensure_string("SOFTWARE_MEETINGS_CALENDAR", True)
SOFTWARE_OH_CALENDAR = ensure_string("SOFTWARE_OH_CALENDAR", True)
ELECTRICAL_MEETINGS_CALENDAR = ensure_string("ELECTRICAL_MEETINGS_CALENDAR", True)
ELECTRICAL_OH_CALENDAR = ensure_string("ELECTRICAL_OH_CALENDAR", True)
MECHANICAL_MEETINGS_CALENDAR = ensure_string("MECHANICAL_MEETINGS_CALENDAR", True)
MECHANICAL_OH_CALENDAR = ensure_string("MECHANICAL_OH_CALENDAR", True)
LEADERS_CALENDAR = ensure_string("LEADERS_CALENDAR", True)

# Email
EMAIL_USERNAME = ensure_string("EMAIL_USERNAME", True)
EMAIL_PASSWORD = ensure_string("EMAIL_PASSWORD", True)

# Wiki
WIKI_USERNAME = ensure_string("WIKI_USERNAME", True)
WIKI_PASSWORD = ensure_string("WIKI_PASSWORD", True)

WEBHOOK_SERVER_PORT = ensure_string("WEBHOOK_SERVER_PORT", True)
GITHUB_OAUTH_CLIENT_ID = ensure_string("GITHUB_OAUTH_CLIENT_ID", True)
GITHUB_OAUTH_CLIENT_SECRET = ensure_string("GITHUB_OAUTH_CLIENT_SECRET", True)
IPC_PORT = ensure_string("IPC_PORT", True)
