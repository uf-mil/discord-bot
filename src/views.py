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


class YesNo(MILBotView):

    message: discord.Message | None
    interaction: discord.Interaction | None

    def __init__(
        self,
        author: discord.Member | discord.User,
        *,
        additional_components: list[discord.ui.Item] | None = None,
        defer_interaction: bool = True,
    ):
        super().__init__()
        self.value = None
        self.author = author
        self.message = None
        self.interaction = None
        self.defer_interaction = defer_interaction
        if additional_components:
            for item in additional_components:
                self.add_item(item)

    @discord.ui.button(
        label="Yes",
        style=discord.ButtonStyle.green,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ):
        self.interaction = interaction
        if interaction.user == self.author:
            self.value = True
            self.interaction = interaction
            if self.defer_interaction:
                await interaction.response.defer()

            # Update buttons
            if self.message:
                self.clear_items()
                self.add_item(
                    discord.ui.Button(
                        label="Confirmed",
                        style=discord.ButtonStyle.danger,
                        disabled=True,
                    ),
                )
                await self.message.edit(view=self)

            self.stop()
        else:
            await interaction.response.send_message(
                "Sorry, you are not the original staff member who called this method.",
                ephemeral=True,
            )

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.interaction = interaction
        if interaction.user == self.author:
            self.value = False
            if self.defer_interaction:
                await interaction.response.defer()

            # Update buttons
            if self.message:
                self.clear_items()
                self.add_item(
                    discord.ui.Button(
                        label="Cancelled",
                        style=discord.ButtonStyle.secondary,
                        disabled=True,
                    ),
                )
                await self.message.edit(view=self)

            self.stop()
        else:
            await interaction.response.send_message(
                "Sorry, you are not the original staff member who called this method.",
                ephemeral=True,
            )

    async def on_timeout(self) -> None:
        if self.message:
            for children in self.children:
                if isinstance(children, discord.ui.Button):
                    children.disabled = True
            await self.message.edit(view=self)
