from __future__ import annotations

import logging
import typing

import discord
from discord.ext import commands

if typing.TYPE_CHECKING:
    from .bot import MILBot

logger = logging.getLogger(__name__)


class Logger(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        When a member leaves the server, log that the member left, along with information
        about their membership when they left.

        Args:
            member (discord.Member): The member who left the server.
        """
        # Post a leaving info message
        embed = discord.Embed(
            title=f"`{member}`",
            color=discord.Color.brand_red(),
        )

        joined_at = (
            f"{discord.utils.format_dt(member.joined_at, style='f')} "
            f"({discord.utils.format_dt(member.joined_at, style='R')})"
        )
        embed.description = (
            f"**{member}** (nicknamed `{member.nick}`) has left the server (or was removed)."
            if member.nick
            else f"**{member}** has left the server (or was removed)."
        )

        embed.add_field(name="Joined At", value=joined_at)
        embed.add_field(
            name="Roles",
            value="\n".join([role.mention for role in member.roles]),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.bot.leave_channel.send(embed=embed)


async def setup(bot: MILBot):
    await bot.add_cog(Logger(bot))
