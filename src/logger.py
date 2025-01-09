from __future__ import annotations

import difflib
import logging
import typing

import discord
from discord.ext import commands

from .utils import surround

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

    def _log_message_filter(self, message: discord.Message) -> bool:
        return not (
            message.author.bot
            and not isinstance(
                message.channel,
                discord.DMChannel | discord.PartialMessageable,
            )
            and (
                message.channel
                in [
                    self.bot.software_projects_channel,
                    self.bot.member_services_channel,
                    self.bot.message_log_channel,
                ]
                or "-lab-" in message.channel.name
            )
        )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """
        When a message is edited, log the edit.

        Args:
            payload (discord.RawMessageUpdateEvent): The payload containing the message edit.
        """

        # Send a message like the following to #message-log:
        # **Cameron Brown** edited a message in #channel ({jump_link}):
        # **Before**: this was sentence
        # **After**: this was **my** sentence
        # bolded words are additions/deletions$
        message = payload.cached_message
        channel = self.bot.active_guild.get_channel(payload.channel_id)
        if not channel:
            await self.bot.message_log_channel.send(
                f"error! Could not find channel ID of `{payload.channel_id}`.",
            )
            return

        message_now = await channel.fetch_message(payload.message_id)  # type: ignore
        if not message:
            message = message_now

        if not self._log_message_filter(message):
            return

        if (
            not message.embeds
            and message_now.embeds
            and message.content == message_now.content
        ):
            # if the message has an embed now (probably from a link),
            # don't post an update just for the embed
            return

        header = f"✏️ **{message.author.display_name}** edited a message in {channel.mention} ([jump!](<{message.jump_url}>)):"
        # if cached message isn't present, we can't figure out
        # what was there before
        if not payload.cached_message:
            before = f"? (message too old, from {discord.utils.format_dt(message.created_at, 'R')})"
            after = message.content
        else:
            # words/phrases present in original, not in new
            def is_junk(s: str) -> bool:
                return s == " "

            s = difflib.SequenceMatcher(
                is_junk,
                payload.cached_message.content,
                message_now.content,
            )
            before = payload.cached_message.content
            after = message_now.content
            # add bolding around deleted phrases in before
            # add bolding around new/replaced phrases in after
            for tag, i1, i2, j1, j2 in s.get_opcodes():
                if tag == "delete":
                    before = surround(before, i1, i2, "**")
                elif tag == "replace":
                    before = surround(before, i1, i2, "**")
                    after = surround(after, j1, j2, "**")
                elif tag == "insert":
                    after = surround(after, j1, j2, "**")

        quoted_before = before.replace("\n", "\n> ")
        quoted_after = after.replace("\n", "\n> ")
        await self.bot.message_log_channel.send(
            f"{header}\n"
            f"> **Before**: {quoted_before}\n"
            "> ---\n"
            f"> **After**: {quoted_after}",
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Sends a message to #message-log:
        # A message by **Cameron Brown** (sent at {date}) in #channel-name was deleted:
        # > This was the message! (+ 1 attachment)
        if payload.cached_message:
            if not self._log_message_filter(payload.cached_message):
                return

            header = f"🔥 A message by **{payload.cached_message.author.display_name}** (sent {discord.utils.format_dt(payload.cached_message.created_at, 'R')}) in {payload.cached_message.channel.mention} was deleted:"
            quoted_message = payload.cached_message.content.replace("\n", "\n> ")
            header += f"\n> {quoted_message}"
            if payload.cached_message.attachments:
                header += f"\n(+ {len(payload.cached_message.attachments)} attachments)"
            files = [
                await attachment.to_file()
                for attachment in payload.cached_message.attachments
            ]
            await self.bot.message_log_channel.send(header, files=files)
        else:
            # basic filter since we don't have full message
            useless_ids = [
                self.bot.software_projects_channel.id,
                self.bot.member_services_channel.id,
                self.bot.message_log_channel.id,
            ]
            if payload.channel_id in useless_ids:
                return

            created_at = discord.utils.snowflake_time(payload.message_id)
            await self.bot.message_log_channel.send(
                f"🔥 A message sent at {discord.utils.format_dt(created_at, 'F')} was deleted in <#{payload.channel_id}> (too old to retrieve).",
            )


async def setup(bot: MILBot):
    await bot.add_cog(Logger(bot))
