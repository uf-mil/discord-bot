from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class GroupButton(discord.ui.Button):
    def __init__(self, label: str, bot: MILBot, emoji: str | None = None):
        self.bot = bot
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label,
            custom_id=f"roles_{label.lower()}",
            emoji=emoji,
        )

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"User {interaction.user} requested {self.label} role")
        assert isinstance(interaction.user, discord.Member)  # buttons in guild only
        role = discord.utils.get(self.bot.active_guild.roles, name=self.label)
        if role is None:
            return await interaction.response.send_message(
                f"Role {self.label} not found. Please contact an admin.",
                ephemeral=True,
            )

        # Make sure user removing role will not cause user to have no roles
        if role in interaction.user.roles and len(interaction.user.roles) == 2:
            return await interaction.response.send_message(
                "Sorry, you cannot remove your last role. Please try adding another role, and then try removing this role.",
                ephemeral=True,
            )

        # If user has New Member role, remove it
        new_member_role = discord.utils.get(
            self.bot.active_guild.roles,
            name="New Member",
        )
        if new_member_role in interaction.user.roles:
            await interaction.user.remove_roles(new_member_role)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"Removed your `{self.label}` role.",
                ephemeral=True,
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"Assigned you the `{self.label}` role.",
                ephemeral=True,
            )


class TeamRolesView(discord.ui.View):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.add_item(GroupButton(label="Mechanical", bot=bot, emoji="🔧"))
        self.add_item(GroupButton(label="Electrical", bot=bot, emoji="🔋"))
        self.add_item(GroupButton(label="Software", bot=bot, emoji="💻"))

    async def on_error(
        self,
        interaction: discord.Interaction,
        exception: Exception,
        item: discord.ui.Item,
    ):
        logger.exception(f"Error with role selection: {exception}")
        await interaction.response.send_message(
            f"Sorry! There was an error with your role selection: `{exception}`",
            ephemeral=True,
        )


class MechanicalRolesView(discord.ui.View):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.add_item(GroupButton(label="Structures and Manufacturing", bot=bot))
        self.add_item(GroupButton(label="Mechanisms and Testing", bot=bot))
        self.add_item(GroupButton(label="Dynamics and Controls", bot=bot))

    async def on_error(
        self,
        interaction: discord.Interaction,
        exception: Exception,
        item: discord.ui.Item,
    ):
        logger.exception(f"Error with role selection: {exception}")
        await interaction.response.send_message(
            f"Sorry! There was an error with your role selection: `{exception}`",
            ephemeral=True,
        )


class GroupCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def teamroles(self, ctx):
        embed = discord.Embed(
            title="Team Selection",
            description="Want to learn more about a specific subteam in MIL? Please use the buttons below to join the appropriate channels. In those channels, you can get connected with team members working on projects in specific domains.",
            color=discord.Color.light_gray(),
        )
        view = TeamRolesView(self.bot)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.is_owner()
    async def mechroles(self, ctx):
        embed = discord.Embed(
            title="Subteam Selection",
            description="Interested in joining a mechanical subteam? Please use the buttons below to select a subteam that best suits your profile. Each button will allow you to see messages for one or more subteams that you may want to participate in.",
            color=discord.Color.orange(),
        )
        view = MechanicalRolesView(self.bot)
        await ctx.send(embed=embed, view=view)


async def setup(bot: MILBot):
    await bot.add_cog(GroupCog(bot))
