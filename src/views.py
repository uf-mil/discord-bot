from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .exceptions import MILBotErrorHandler

if TYPE_CHECKING:
    from .bot import MILBot


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
