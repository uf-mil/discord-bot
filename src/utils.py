import datetime
import re

import discord
from discord import app_commands

from .constants import SEMESTERS


def is_active() -> bool:
    """
    Whether the reports system is active.
    """
    for semester in SEMESTERS:
        if semester[0] <= datetime.date.today() <= semester[1]:
            return True
        if datetime.date.today() <= semester[0]:
            return False
    return False


def emoji_header(emoji: str, title: str) -> str:
    return f"{emoji} __{title}__"


class EmojiEmbed(discord.Embed):
    def add_field(
        self,
        emoji: str,
        name: str,
        value: str,
        *,
        inline: bool = False,
    ) -> None:
        super().add_field(name=emoji_header(emoji, name), value=value, inline=inline)


class DateTransformer(app_commands.Transformer):
    async def transform(
        self,
        interaction: discord.Interaction,
        value: str,
    ) -> datetime.date:
        # Supports the following formats:
        # 2021-09-01
        # 9/1/2021
        # 9/1/21
        # 9-1-2021
        # 9-1-21
        # 9/1
        # 9-1

        value = value.replace(" ", "")

        # Define regex patterns for different date formats
        patterns = {
            r"^(\d{4})-(\d{2})-(\d{2})$": "%Y-%m-%d",  # 2021-09-01
            r"^(\d{1,2})/(\d{1,2})/(\d{4})$": "%m/%d/%Y",  # 9/1/2021
            r"^(\d{1,2})/(\d{1,2})/(\d{2})$": "%m/%d/%y",  # 9/1/21
            r"^(\d{1,2})-(\d{1,2})-(\d{4})$": "%m-%d-%Y",  # 9-1-2021
            r"^(\d{1,2})-(\d{1,2})-(\d{2})$": "%m-%d-%y",  # 9-1-21
            r"^(\d{1,2})/(\d{1,2})$": "%m/%d",  # 9/1
            r"^(\d{1,2})-(\d{1,2})$": "%m-%d",  # 9-1
        }

        for pattern, date_format in patterns.items():
            if re.match(pattern, value):
                # Convert matched value to datetime.date object
                date_value = datetime.datetime.strptime(value, date_format).date()
                return date_value

        # If no pattern matches, you might want to raise an error or handle it gracefully
        raise ValueError("Invalid date format. Please enter a valid date.")


class TimeTransformer(app_commands.Transformer):
    async def transform(
        self,
        interaction: discord.Interaction,
        value: str,
    ) -> datetime.time:
        # Supports the following formats:
        # 09:00
        # 9:00 AM
        # 9:00 am
        # 9AM

        value = value.replace(" ", "").lower()

        # Define regex patterns for different time formats
        patterns = {
            r"^(\d{1,2}):(\d{2})$": "%H:%M",  # 09:00
            r"^(\d{1,2}):(\d{2})(am|pm)$": "%I:%M%p",  # 9:00am
            r"^(\d{1,2})(am|pm)$": "%I%p",  # 9am
        }

        for pattern, time_format in patterns.items():
            if re.match(pattern, value):
                # Convert matched value to datetime.time object
                time_value = datetime.datetime.strptime(value, time_format).time()
                return time_value

        # If no pattern matches, you might want to raise an error or handle it gracefully
        raise ValueError("Invalid time format. Please enter a valid time.")


def capped_str(parts: list[str], cap: int = 1024) -> str:
    """
    Joins the most parts possible with a new line between them. If the resulting
    length is greater than the cap length, then the remaining parts are truncated.

    If the parts are capped, "_... (X after)_" is appended to the end.
    """
    result = ""
    made_it = 0
    for part in parts:
        if len(result) + len(part) + len("\n_... (99 after)_") > cap:
            result += f"_... ({len(parts) - made_it} after)_"
            break
        result += part + "\n"
        made_it += 1
    return result.strip()
