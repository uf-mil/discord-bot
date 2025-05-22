from __future__ import annotations

import random
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from .bot import MILBot


class FunCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.change_status.is_running():
            self.change_status.start()

    @tasks.loop(hours=1)
    async def change_status(self):
        activities: list[discord.Activity] = [
            discord.Activity(type=discord.ActivityType.watching, name="ROS tutorials"),
            discord.Activity(type=discord.ActivityType.playing, name="with SubjuGator"),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="VRX submissions",
            ),
            discord.Activity(
                type=discord.ActivityType.playing,
                name="with soldering irons",
            ),
            discord.Activity(
                type=discord.ActivityType.playing,
                name="ML Image Labeler",
            ),
            discord.Activity(
                type=discord.ActivityType.playing,
                name="SolidWorks",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="robotics lectures",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="underwater pings",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="feedback from members",
            ),
            discord.Activity(type=discord.ActivityType.watching, name="for new PRs"),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="mechanical Tech Talks",
            ),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="students get internships",
            ),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="the DSIT building open",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="alumni advice",
            ),
        ]
        await self.bot.change_presence(activity=random.choice(activities))


async def setup(bot: MILBot):
    await bot.add_cog(FunCog(bot))
