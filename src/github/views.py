from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import aiohttp
import discord

from ..views import MILBotModal, MILBotView

if TYPE_CHECKING:
    from ..bot import MILBot


logger = logging.getLogger(__name__)


class GitHubUsernameModal(MILBotModal):

    username = discord.ui.TextInput(label="Username")

    def __init__(
        self,
        bot: MILBot,
        org_name: Literal["uf-mil", "uf-mil-electrical", "uf-mil-mechanical"],
    ):
        self.bot = bot
        self.org_name = org_name
        super().__init__(title="GitHub Username")

    async def on_submit(self, interaction: discord.Interaction):
        """
        Invite a user to a MIL GitHub organization.

        Args:
            username: The username of the user to invite.
            org_name: The name of the organization to invite the user to.
        """
        username = self.username.value
        # Ensure that the specified username is actually a GitHub user, and get
        # their user object
        try:
            user = await self.bot.github.get_user(username)
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                await interaction.response.send_message(
                    f"Failed to find user with username {username}.",
                    ephemeral=True,
                )
            raise e

        async with self.bot.db_factory() as db:
            oauth_user = await db.get_github_oauth_member(interaction.user.id)
            if not oauth_user:
                return await interaction.response.send_message(
                    f"You have not connected your GitHub account. Please connect your account first in {self.bot.member_services_channel.mention}!",
                    ephemeral=True,
                )
        try:
            # If the org is uf-mil, invite to the "Developers" team
            if self.org_name == "uf-mil":
                team = await self.bot.github.get_team(self.org_name, "developers")
                await self.bot.github.invite_user_to_org(
                    user["id"],
                    self.org_name,
                    team["id"],
                    oauth_user.access_token,
                )
            else:
                await self.bot.github.invite_user_to_org(
                    user["id"],
                    self.org_name,
                    user_access_token=oauth_user.access_token,
                )
            await interaction.response.send_message(
                f"Successfully invited {username} to {self.org_name}.",
                ephemeral=True,
            )
        except aiohttp.ClientResponseError as e:
            if e.status == 403:
                await interaction.response.send_message(
                    "Your GitHub account does not have the necessary permissions to invite users to the organization.",
                    ephemeral=True,
                )
            if e.status == 422:
                await interaction.response.send_message(
                    "Validation failed, the user might already be in the organization.",
                    ephemeral=True,
                )
            return
        except Exception:
            await interaction.response.send_message(
                f"Failed to invite {username} to {self.org_name}.",
                ephemeral=True,
            )
            logger.exception(
                f"Failed to invite username {username} to {self.org_name}.",
            )


class GitHubInviteView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Invite to uf-mil",
        style=discord.ButtonStyle.secondary,
        custom_id="github_invite:software",
    )
    async def invite_to_uf_mil(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ):
        await interaction.response.send_modal(GitHubUsernameModal(self.bot, "uf-mil"))

    @discord.ui.button(
        label="Invite to uf-mil-electrical",
        style=discord.ButtonStyle.secondary,
        custom_id="github_invite:electrical",
    )
    async def invite_to_uf_mil_electrical(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            GitHubUsernameModal(self.bot, "uf-mil-electrical"),
        )

    @discord.ui.button(
        label="Invite to uf-mil-mechanical",
        style=discord.ButtonStyle.secondary,
        custom_id="github_invite:mechanical",
    )
    async def invite_to_uf_mil_mechanical(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            GitHubUsernameModal(self.bot, "uf-mil-mechanical"),
        )
