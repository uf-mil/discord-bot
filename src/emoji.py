from __future__ import annotations

import os.path
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import discord

from src.image import convert_svg_to_png

if TYPE_CHECKING:
    from .bot import MILBot


class CustomEmoji(Enum):
    COMMIT = "github_commit.svg"
    STAR = "github_star.svg"
    ISSUE_OPENED = "github_issue_opened.svg"
    ISSUE_CLOSED = "github_issue_closed.svg"
    SKIP = "github_skip.svg"
    PERSON_ADDED = "github_person_added.svg"
    PERSON_REMOVED = "github_person.svg"
    PULL_REQUEST_OPENED = "github_pr_opened.svg"
    PULL_REQUEST_MERGED = "github_pr_merged.svg"
    PULL_REQUEST_CLOSED = "github_pr_closed.svg"
    CODE_BUBBLE = "github_code_bubble.svg"
    COMMENT = "github_comment.svg"
    PENCIL = "github_pencil.svg"
    EARTH = "github_earth.svg"
    REPO = "github_repo.svg"
    TRASH = "github_trash.svg"
    FADED_REPO = "github_faded_repo.svg"
    X = "github_x.svg"
    TAG = "github_tag.svg"
    CALENDAR = "github_calendar.svg"
    PROJECT = "github_project.svg"
    CHECK = "github_check.svg"

    def emoji_name(self) -> str:
        split = os.path.splitext(self.value)
        if len(split) != 2:
            raise ValueError(
                f"{self.name} has a weird filename, cannot create emoji name from filename: {self.value}",
            )
        return split[0]

    def is_svg(self) -> bool:
        return self.value.lower().endswith(".svg")


@dataclass
class EmojiAddition:
    name: str
    image: bytes


class EmojiRegistry:

    emoji_cache_: dict[str, discord.Emoji]

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.emoji_cache_ = {}

    async def upload(self, existing_emojis: list[discord.Emoji]) -> list[EmojiAddition]:
        existing_emoji_names = [e.name for e in existing_emojis]
        need_to_add = []
        for item in CustomEmoji:
            if item.emoji_name() not in existing_emoji_names:
                with open(
                    os.path.join("src", "assets", "emojis", item.value),
                    "rb",
                ) as f:
                    if item.is_svg():
                        # Convert SVG to PNG
                        image = convert_svg_to_png(f.name)
                        if not image:
                            raise ValueError(
                                f"Failed to convert SVG to PNG for emoji {item.name}",
                            )
                    else:
                        image = f.read()
                need_to_add.append(EmojiAddition(name=item.emoji_name(), image=image))
        return need_to_add

    def store_emojis(self, emojis: list[discord.Emoji]) -> None:
        for emoji in emojis:
            self.emoji_cache_[emoji.name] = emoji

    def get_emoji(self, emoji: CustomEmoji) -> discord.Emoji | None:
        return self.emoji_cache_.get(emoji.emoji_name(), None)
