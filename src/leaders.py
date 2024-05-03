"""
Provides functionality related to leadership of MIL.
"""
from __future__ import annotations

import calendar
import datetime
import time
from typing import TYPE_CHECKING

import discord
from discord.app_commands import NoPrivateMessage
from discord.ext import commands

from .anonymous import AnonymousReportView
from .env import LEADERS_MEETING_NOTES_URL, LEADERS_MEETING_URL
from .tasks import run_on_weekday
from .utils import is_active
from .verification import StartEmailVerificationView
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


MEETING_TIME = datetime.time(19, 0, 0)
MEETING_DAY = calendar.TUESDAY


class AwayView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Toggle Away",
        custom_id="away:toggle",
        style=discord.ButtonStyle.primary,
    )
    async def toggle_away(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise NoPrivateMessage
        if self.bot.away_role in member.roles:
            await member.remove_roles(self.bot.away_role)
            await interaction.response.send_message(
                "You are no longer marked as away. Welcome back!",
                ephemeral=True,
            )
        else:
            await member.add_roles(self.bot.away_role)
            await interaction.response.send_message(
                f"You are now marked as {self.bot.away_role.mention}. Enjoy your break!",
                ephemeral=True,
            )


class Leaders(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.notes_reminder.start(self)
        self.pre_reminder.start(self)
        self.at_reminder.start(self)

    @commands.command()
    @commands.has_any_role("Software Leadership")
    async def runtask(self, ctx: commands.Context, func_name: str):
        for task in self.bot.tasks.recurring_tasks():
            if task._func.__name__ == func_name:
                msg = await ctx.send(
                    f"{self.bot.loading_emoji} Running task `{func_name}`... (started {discord.utils.format_dt(discord.utils.utcnow(), 'R')})",
                )
                start_time = time.monotonic()
                await task.run_immediately()
                end_time = time.monotonic()
                await msg.edit(
                    content=f"✅ Task `{func_name}` ran. Took `{end_time - start_time:.2f}s` to run. Scheduled another instance to run at {task.next_time()}.",
                )
                return
        await ctx.send(f"❌ Task `{func_name}` not found.")

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Check that leaders mentioned are not away - if they are, remind the poster
        # that they are away.
        if message.author.bot:
            return

        mentioned = message.mentions
        for member in mentioned:
            if (
                isinstance(member, discord.Member)
                and self.bot.away_role in member.roles
            ):
                delay_seconds = 15
                delete_at = message.created_at + datetime.timedelta(
                    seconds=delay_seconds,
                )
                await message.reply(
                    f"{member.mention} is currently away from MIL for a temporary break, and may not respond immediately. Please consider reaching out to another leader or wait for their return. (deleting this message {discord.utils.format_dt(delete_at, 'R')})",
                    delete_after=delay_seconds,
                )

    @commands.command()
    @commands.is_owner()
    async def prepverify(self, ctx: commands.Context):
        # Embed to allow current members to verify themselves with their email
        # address. A recent security measure we implemented recently.
        start_date = datetime.datetime(2024, 4, 16, 0, 0, 0)
        end_date = datetime.datetime(2024, 5, 13, 0, 0, 0)
        embed = discord.Embed(
            title="Required Server Verification",
            description=f"* Starting on {discord.utils.format_dt(start_date, 'D')}, all members will need to authenticate themselves with their `ufl.edu` email address in order to maintain access to the server, for security purposes. This authentication process is short, and will only need to be completed once. You must use the `ufl.edu` email belonging to you.\n* {self.bot.alumni_role.mention} are exempt from this process. If you do not have a `ufl.edu` email address, please reach out to {self.bot.leaders_role.mention} or Dr. Schwartz for assistance.\n* All members with unauthenticated email addresses will be **removed from the server** on the first day of Summer 2024 ({discord.utils.format_dt(end_date, 'D')}).",
            color=discord.Color.brand_green(),
        )
        await ctx.send(
            embed=embed,
            view=StartEmailVerificationView(self.bot),
        )

    @commands.command()
    @commands.is_owner()
    async def prepanonymous(self, ctx: commands.Context):
        embed = discord.Embed(
            title="File an Anonymous Report",
            description="""Your voice matters to us. If you have feedback or concerns about your experience at MIL, please feel comfortable using our anonymous reporting tool. By clicking the button below, you can file a report without revealing your identity, ensuring your privacy and safety.

            We treat all submissions with the utmost seriousness and respect. When filing your report, you have the option to select who will receive and review this information. To help us address your concerns most effectively, please provide as much detail as possible in your submission.""",
            color=discord.Color.from_rgb(249, 141, 139),
        )
        view = AnonymousReportView(self.bot)
        await ctx.send(
            embed=embed,
            view=view,
        )
        await ctx.message.delete()

    @commands.command()
    @commands.is_owner()
    async def prepaway(self, ctx: commands.Context):
        view = AwayView(self.bot)
        embed = discord.Embed(
            title="Take a Short Break",
            description="""As leaders, it's important to take breaks and recharge. If you're planning to take a short break, you can mark yourself as away to let others know. When you're ready to return, you can toggle this status off.

            During your break, members who ping you will be notified that you're away and unable to assist in MIL efforts until you return. This is a great way to ensure you're not disturbed during your break.

            You can use the button below to toggle your away status on and off. Enjoy your break!""",
            color=self.bot.away_role.color,
        )
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()


async def setup(bot: MILBot):
    await bot.add_cog(Leaders(bot))
