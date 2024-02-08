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
GSPREAD_SS_NAME = ensure_string("GSPREAD_SS_NAME")
DISCORD_TOKEN = ensure_string("DISCORD_TOKEN")
GUILD_ID = int(ensure_string("GUILD_ID"))
GITHUB_TOKEN = ensure_string("GITHUB_TOKEN")
LEADERS_MEETING_NOTES_URL = ensure_string("MEETING_NOTES_URL")
LEADERS_MEETING_URL = ensure_string("MEETING_URL")

# Calendars
GENERAL_CALENDAR = ensure_string("GENERAL_CALENDAR")
SOFTWARE_MEETINGS_CALENDAR = ensure_string("SOFTWARE_MEETINGS_CALENDAR")
SOFTWARE_OH_CALENDAR = ensure_string("SOFTWARE_OH_CALENDAR")
ELECTRICAL_MEETINGS_CALENDAR = ensure_string("ELECTRICAL_MEETINGS_CALENDAR")
ELECTRICAL_OH_CALENDAR = ensure_string("ELECTRICAL_OH_CALENDAR")
MECHANICAL_MEETINGS_CALENDAR = ensure_string("MECHANICAL_MEETINGS_CALENDAR")
MECHANICAL_OH_CALENDAR = ensure_string("MECHANICAL_OH_CALENDAR")
