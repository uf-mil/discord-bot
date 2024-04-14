from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.utils import MISSING

from .exceptions import MILBotErrorHandler

if TYPE_CHECKING:
    from .bot import MILBot

logger = logging.getLogger(__name__)


class MILBotModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        title: str,
        timeout: float | None = None,
        custom_id: str = MISSING,
    ):
        keys = {}
        if custom_id:
            keys["custom_id"] = custom_id
        if len(title) > 45:
            logger.warning(f"Modal title is too long ({len(title)} > 45): {title}")
        super().__init__(title=title[:45], timeout=timeout, **keys)
        self.handler = MILBotErrorHandler()

    async def on_error(  # type: ignore
        self,
        interaction: discord.Interaction[MILBot],
        error: Exception,
    ) -> None:
        await self.handler.handle_interaction_exception(interaction, error)


class MILBotView(discord.ui.View):
    def __init__(self, *, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.handler = MILBotErrorHandler()

    async def on_error(
        self,
        interaction: discord.Interaction[MILBot],
        error: app_commands.AppCommandError,
        item: discord.ui.Item,
    ) -> None:
        await self.handler.handle_interaction_exception(interaction, error)
