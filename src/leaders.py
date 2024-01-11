"""
Provides functionality related to leadership of MIL.
"""
from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .env import LEADERS_MEETING_NOTES_URL, LEADERS_MEETING_URL
from .helper import run_on_weekday
from .utils import is_active
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


MEETING_TIME = datetime.time(19, 0, 0)
MEETING_DAY = calendar.TUESDAY


class Leaders(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.bot.tasks.create_task(self.notes_reminder())
        self.bot.tasks.create_task(self.pre_reminder())
        self.bot.tasks.create_task(self.at_reminder())

    @run_on_weekday(
        MEETING_DAY,
        MEETING_TIME.hour,
        MEETING_TIME.minute,
        shift=-datetime.timedelta(hours=7),
        check=is_active,
    )
    async def notes_reminder(self):
        meeting_time = datetime.datetime.combine(datetime.date.today(), MEETING_TIME)
        embed = discord.Embed(
            title="🚨 Leaders Meeting Tonight!",
            description=f"Don't forget to attend the leaders meeting tonight at {discord.utils.format_dt(meeting_time, 't')} today! To help the meeting proceed efficiently, **all leaders** from **each team** should fill out the meeting notes for tonight's meeting **ahead of the meeting time**. Please include:\n* What has been completed over the past week\n* Plans for this upcoming week\n* Challenges your team faces\n\nThank you! If you have any questions, please ping {self.bot.sys_leads_role.mention}.",
            color=discord.Color.teal(),
        )
        view = MILBotView()
        view.add_item(
            discord.ui.Button(label="Meeting Notes", url=LEADERS_MEETING_NOTES_URL),
        )
        await self.bot.leaders_channel.send(
            f"{self.bot.leaders_role.mention}",
            embed=embed,
            view=view,
        )

    @run_on_weekday(
        MEETING_DAY,
        MEETING_TIME.hour,
        MEETING_TIME.minute,
        shift=-datetime.timedelta(minutes=15),
        check=is_active,
    )
    async def pre_reminder(self):
        embed = discord.Embed(
            title="🚨 Leaders Meeting in 15 Minutes!",
            description="Who's excited to meet?? 🙋 Please arrive on time so we can promptly begin the meeting. If you have not already filled out the meeting notes for your team, please do so **now**! Thank you so much!",
            color=discord.Color.brand_green(),
        )
        view = MILBotView()
        view.add_item(
            discord.ui.Button(label="Meeting Notes", url=LEADERS_MEETING_NOTES_URL),
        )
        view.add_item(discord.ui.Button(label="Meeting Link", url=LEADERS_MEETING_URL))
        await self.bot.leaders_channel.send(
            f"{self.bot.leaders_role.mention}",
            embed=embed,
            view=view,
        )

    @run_on_weekday(
        MEETING_DAY,
        MEETING_TIME.hour,
        MEETING_TIME.minute,
        shift=-datetime.timedelta(minutes=2),
        check=is_active,
    )
    async def at_reminder(self):
        embed = discord.Embed(
            title="🚨 Leaders Meeting Starting!",
            description="It's time! The leaders meeting is starting now! Please join on time so we can begin the meeting promptly.",
            color=discord.Color.brand_red(),
        )
        view = MILBotView()
        view.add_item(
            discord.ui.Button(label="Meeting Notes", url=LEADERS_MEETING_NOTES_URL),
        )
        view.add_item(discord.ui.Button(label="Meeting Link", url=LEADERS_MEETING_URL))
        await self.bot.leaders_channel.send(
            f"{self.bot.leaders_role.mention}",
            embed=embed,
            view=view,
        )


async def setup(bot: MILBot):
    await bot.add_cog(Leaders(bot))
