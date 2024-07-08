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
from .github import GitHubInviteView
from .tasks import run_on_weekday
from .utils import is_active
from .verification import StartEmailVerificationView
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


MEETING_TIME = datetime.time(16, 30, 0)
MEETING_DAY = calendar.MONDAY


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

    away_cooldown: dict[discord.Member, list[tuple[discord.Member, datetime.datetime]]]

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.notes_reminder.start(self)
        self.pre_reminder.start(self)
        self.at_reminder.start(self)
        self.robosub_reminder.start(self)
        self.away_cooldown = {}

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

    def _schedule_generator(
        self,
        start_date: datetime.date,
        event_submission: datetime.date,
        design_submission: datetime.date,
        ship_date: datetime.date,
        competition_start: datetime.date,
        competition_end: datetime.date,
    ) -> str:
        today = datetime.date.today()
        symbols = []
        days = (competition_end - start_date).days + 1

        annotations = {}

        for i in range(days):
            current_date = start_date + datetime.timedelta(days=i)
            week_start = current_date - datetime.timedelta(
                days=(current_date.weekday() + 1) % 7,
            )
            week_format = week_start.strftime("%b %d")
            if current_date < today:
                symbol = " "
            elif current_date == today:
                symbol = "X"
            elif current_date.strftime("%U") == today.strftime("%U"):
                symbol = "x"
            elif current_date < ship_date:
                symbol = "."
            elif current_date < competition_start:
                symbol = "s"
            else:
                symbol = "c"

            # Annotations
            if current_date == ship_date:
                annotations[week_format] = "← ship date"
            if current_date == event_submission:
                annotations[week_format] = "← event submission"
            if current_date == design_submission:
                annotations[week_format] = "← design submission"
            if current_date == start_date:
                annotations[week_format] = "← start"
            if current_date == today:
                annotations[week_format] = "← current week"
            if current_date == competition_start:
                annotations[week_format] = "← competition start"
            if current_date == competition_end:
                annotations[week_format] = "← competition end"
            symbols.append(symbol)

        weeks = {}
        for i, symbol in enumerate(symbols):
            current_date = start_date + datetime.timedelta(days=i)
            week_start = current_date - datetime.timedelta(
                days=(current_date.weekday() + 1) % 7,
            )
            week_format = week_start.strftime("%b %d")
            weeks.setdefault(week_format, []).append(symbol)

        final_string = []
        for week, symbols in weeks.items():
            line = f"{week:<6}: {''.join(symbols):<7}"
            if week in annotations:
                line += f" {annotations[week]}"
            final_string.append(line)

        together_schedule = "\n".join(final_string)
        return f"```js\n        SMTWTFS\n{together_schedule}\n```"

    @run_on_weekday(
        [calendar.MONDAY, calendar.FRIDAY],
        9,
        0,
    )
    async def robosub_reminder(self):
        SUMMER_START = datetime.date(2024, 5, 13)
        EVENT_SUBMISSION = datetime.date(2024, 6, 17)
        DESIGN_SUBMISSION = datetime.date(2024, 6, 24)
        ROBOSUB_START = datetime.date(2024, 8, 5)
        ROBOSUB_END = datetime.date(2024, 8, 11)
        SHIPPING_START = ROBOSUB_START - datetime.timedelta(days=10)
        today = datetime.date.today()
        if today < SHIPPING_START:
            days = (SHIPPING_START - today).days
            estimated_testings = days // (7 / 3)  # assuming three testings per week
            await self.bot.leaders_channel.send(
                f"Good morning! There are **{days} days** until sub is shipped! (estimated testings remaining: **{estimated_testings:.0f}**)\n{self._schedule_generator(SUMMER_START, EVENT_SUBMISSION, DESIGN_SUBMISSION, SHIPPING_START, ROBOSUB_START, ROBOSUB_END)}",
            )
        elif today < ROBOSUB_START:
            days = (ROBOSUB_START - today).days
            await self.bot.leaders_channel.send(
                f"Good morning! There are **{days} days** until competition!",
            )

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

    def _away_cooldown_check(
        self,
        away_member: discord.Member,
        pinger: discord.Member,
    ) -> bool:
        """
        Returns True if pinger should be notified, False otherwise.
        """
        if away_member in self.away_cooldown:
            who_was_notified = self.away_cooldown[away_member]
            for member, last_notified in who_was_notified:
                if (
                    member == pinger
                    and datetime.datetime.now().astimezone() - last_notified
                    < datetime.timedelta(days=1)
                ):
                    return False
        return True

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
            description="Your voice matters to us. If you have feedback or concerns about your experience at MIL, please feel comfortable using our anonymous reporting tool. By clicking the button below, you can file a report without revealing your identity, ensuring your privacy and safety."
            + "\n\n"
            + "We treat all submissions with the utmost seriousness and respect. When filing your report, you have the option to select who will receive and review this information. To help us address your concerns most effectively, please provide as much detail as possible in your submission.",
            color=discord.Color.from_rgb(249, 141, 139),
        )
        embed.set_footer(
            text="Our commitment to your privacy is transparent—feel free to review our source code on GitHub.",
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
            description="As leaders, it's important to take breaks and recharge. If you're planning to take a short break, you can mark yourself as away to let others know. When you're ready to return, you can toggle this status off.\n\nDuring your break, members who ping you will be notified that you're away and unable to assist in MIL efforts until you return. This is a great way to ensure you're not disturbed during your break.\n\nYou can use the button below to toggle your away status on and off. Enjoy your break!",
            color=self.bot.away_role.color,
        )
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()

    @commands.command()
    @commands.is_owner()
    async def prepgithub(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Invite Members to GitHub",
            description="Use the following buttons to invite members to the software or electrical GitHub organizations. Please ensure that the member has a GitHub account before inviting them.",
            color=discord.Color.light_gray(),
        )
        view = GitHubInviteView(self.bot)
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()


async def setup(bot: MILBot):
    await bot.add_cog(Leaders(bot))
