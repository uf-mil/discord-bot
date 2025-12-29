import datetime
import re
from collections.abc import Iterable

import discord
from discord import app_commands

from .constants import SEMESTERS


def make_and(iterable: Iterable) -> str:
    """
    Joins an iterable with commas and an "and" before the last element.
    """
    iterable = list(iterable)
    if len(iterable) == 0:
        return ""
    if len(iterable) == 1:
        return iterable[0]
    if len(iterable) == 2:
        return f"{iterable[0]} and {iterable[1]}"
    return f"{', '.join(iterable[:-1])}, and {iterable[-1]}"


def surround(s: str, start: int, end: int, surround_with: str) -> str:
    """
    Surrounds a part of a string with some characters.
    """
    if start >= end:
        raise ValueError("start must be less than end")
    return s[:start] + surround_with + s[start:end] + surround_with + s[end:]


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


def has_emoji(s: str) -> bool:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002700-\U000027BF"  # Dingbats
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U00002600-\U000026FF"  # Miscellaneous Symbols
        "\U00002B00-\U00002BFF"  # Miscellaneous Symbols and Arrows
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "]+",
        flags=re.UNICODE,
    )
    return bool(emoji_pattern.fullmatch(s))


def emoji_header(emoji: str, title: str) -> str:
    if not has_emoji(emoji):
        raise ValueError(f"{emoji} is not a valid emoji")
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
    for made_it, part in enumerate(parts):
        if len(result) + len(part) + len("\n_... (99 after)_") > cap:
            result += f"_... ({len(parts) - made_it} after)_"
            break
        result += part + "\n"
    return result.strip()


# derived from: https://stackoverflow.com/a/20007730
def ordinal(n: int):
    suffix = (
        "th"
        if 11 <= (n % 100) <= 13
        else ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]
    )
    return str(n) + suffix
