"""
Provides functionality related to leadership of MIL.
"""
from __future__ import annotations

import asyncio
import calendar
import datetime
import re
import time
from typing import TYPE_CHECKING

import discord
from discord.app_commands import NoPrivateMessage
from discord.ext import commands

from .anonymous import AnonymousReportView
from .env import LEADERS_MEETING_NOTES_URL, LEADERS_MEETING_URL
from .github import GitHubInviteView
from .tasks import run_on_weekday
from .utils import is_active, make_and
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


MEETING_TIME = datetime.time(17, 0, 0)
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
    protected_channel_names: list[str]
    perm_notify_lock: asyncio.Lock

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.notes_reminder.start(self)
        self.pre_reminder.start(self)
        self.at_reminder.start(self)
        self.robotx_reminder.start(self)
        self.away_cooldown = {}
        self.protected_channel_names = [
            r"^.*leads$",
            "^students-only$",
            "^.*-travel$",
            r"^.*-leadership$",
        ]
        self.perm_notify_lock = asyncio.Lock()

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

    @commands.command()
    @commands.has_any_role("Leaders")
    async def assign_egn4912(
        self,
        ctx: commands.Context,
        files: commands.Greedy[discord.Attachment],
    ):
        """
        Assigns EGN4912 roles to all members.
        """
        software_file = discord.utils.get(files, filename="software.txt")
        electrical_file = discord.utils.get(files, filename="electrical.txt")
        mechanical_file = discord.utils.get(files, filename="mechanical.txt")
        if not software_file and not electrical_file and not mechanical_file:
            await ctx.reply(
                "Please attach at least one of the following files: `software.txt`, `electrical.txt`, `mechanical.txt`.",
            )
            return
        else:
            await ctx.reply(
                f"{self.bot.loading_emoji} Assigning EGN4912 roles to all members. This may take a while...",
            )

        team_names = {
            software_file: "Software",
            electrical_file: "Electrical",
            mechanical_file: "Mechanical",
        }
        added_successfully = {
            software_file: 0,
            electrical_file: 0,
            mechanical_file: 0,
        }
        could_not_find = {
            software_file: [],
            electrical_file: [],
            mechanical_file: [],
        }
        for file in [software_file, electrical_file, mechanical_file]:
            if not file:
                continue
            for name in (await file.read()).decode().split("\n"):
                name = name.strip()
                if not name:
                    continue
                was_added = False
                for member in self.bot.active_guild.members:
                    if member.display_name.lower() == name.lower():
                        team_role = discord.utils.get(
                            self.bot.active_guild.roles,
                            name=f"EGN4912 {team_names[file]}",
                        )
                        if not team_role:
                            await ctx.reply(
                                f"Could not find the role for {team_names[file]} team. Please create the role and try again.",
                            )
                            return
                        roles_to_add = {team_role, self.bot.egn4912_role}
                        await member.add_roles(*(roles_to_add - set(member.roles)))
                        added_successfully[file] += 1
                        was_added = True
                if not was_added:
                    could_not_find[file].append(name)
            await ctx.reply(
                f"{team_names[file]} team: {added_successfully[file]} members added successfully. Could not find: {', '.join(could_not_find[file])}",
            )

    @commands.command(aliases=["yellowpages", "yp"])
    @commands.has_any_role("Leaders")
    async def lookup(self, ctx: commands.Context, name: str):
        """
        Finds all users who could be related to by the name
        """
        members: list[discord.Member] = []
        for member in self.bot.active_guild.members:
            if name.lower() in member.display_name.lower():
                members.append(member)
        if not members:
            await ctx.reply("No members found.")
            return
        members = sorted(members, key=lambda x: x.display_name)
        formatted_members = []
        for member in members:
            useful_roles = set(member.roles) - {self.bot.active_guild.default_role}
            roles = ", ".join(role.name for role in useful_roles)
            formatted_members.append(
                f"* {member.display_name} ({member.mention}) - Roles: {roles}",
            )
        new_line_formatted = "\n".join(formatted_members)
        await ctx.reply(
            f"Found members: \n{new_line_formatted}",
        )

    def _schedule_generator(
        self,
        start_date: datetime.date,
        event_submission: datetime.date,
        design_submission: datetime.date,
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
            elif current_date < competition_start:
                symbol = (
                    "." if current_date.weekday() not in [6, 2] else "t"
                )  # testing dates
            else:
                symbol = "c"

            # Annotations
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
    async def robotx_reminder(self):
        FALL_START = datetime.date(2024, 8, 18)
        EVENT_SUBMISSION = datetime.date(2024, 9, 23)
        DESIGN_SUBMISSION = datetime.date(2024, 9, 30)
        ROBOTX_START = datetime.date(2024, 11, 3)
        ROBOTX_END = datetime.date(2024, 11, 10)
        LEAVE_DATE = ROBOTX_START - datetime.timedelta(days=3)
        today = datetime.date.today()
        if today < LEAVE_DATE:
            days = (LEAVE_DATE - today).days
            total_days = (LEAVE_DATE - FALL_START).days
            progress_ratio = (total_days - days) / total_days
            estimated_testings = days // (7 / 2)  # assuming two testings per week
            await self.bot.leaders_channel.send(
                f"Good morning! There are **{days} days** (progress from start: {progress_ratio:.2%}) until we leave for competition! (estimated testings remaining: **{estimated_testings:.0f}**)\n{self._schedule_generator(FALL_START, EVENT_SUBMISSION, DESIGN_SUBMISSION, ROBOTX_START, ROBOTX_END)}",
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

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ):
        # Do the same thing as the function below
        if not isinstance(before, discord.TextChannel) or not isinstance(
            after,
            discord.TextChannel,
        ):
            return
        async with self.perm_notify_lock:
            important = any(
                re.match(name, after.name) for name in self.protected_channel_names
            )
            if important:
                before_members = before.members
                after_members = after.members
                removed_members = set(before_members) - set(after_members)
                added_members = set(after_members) - set(before_members)
                entry = [
                    x
                    async for x in after.guild.audit_logs(
                        limit=1,
                        after=discord.utils.utcnow() - datetime.timedelta(seconds=5),
                    )
                    if x.action
                    in [
                        discord.AuditLogAction.channel_update,
                        discord.AuditLogAction.overwrite_update,
                        discord.AuditLogAction.overwrite_create,
                        discord.AuditLogAction.overwrite_delete,
                    ]
                    and x.target.id == after.id
                ]
                user = "A user" if not entry else entry[0].user.mention
                if removed_members:
                    removed_name_str = ", ".join(
                        f"**{member.display_name}**" for member in removed_members
                    )
                    await after.send(
                        f"{user} updated channel permissions to remove {{{removed_name_str}}} from this channel. Adios! :wave:",
                    )
                if added_members:
                    added_str = ", ".join(
                        f"**{member.display_name}**" for member in added_members
                    )
                    added_mention_str = make_and(
                        [member.mention for member in added_members],
                    )
                    await after.send(
                        f"{user} updated channel permissions to add {{{added_str}}} to this channel. Welcome {added_mention_str}! :wave:",
                    )

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ):
        # Check if the user received a role that allows them to view/not view
        # important channels
        if before.roles == after.roles:
            return
        async with self.perm_notify_lock:
            after = await after.guild.fetch_member(after.id)
            await asyncio.sleep(1)
            entry = [
                x
                async for x in after.guild.audit_logs(
                    limit=1,
                    after=discord.utils.utcnow() - datetime.timedelta(seconds=5),
                )
                if x.action
                in [
                    discord.AuditLogAction.member_role_update,
                ]
                and x.target.id == after.id
            ]
            user = "A user" if not entry else entry[0].user.mention
            important_channels = [
                c
                for c in before.guild.text_channels
                if any(re.match(name, c.name) for name in self.protected_channel_names)
            ]
            for channel in important_channels:
                member_can_view_before = channel.permissions_for(before).read_messages
                member_can_view_after = channel.permissions_for(after).read_messages
                if member_can_view_after and not member_can_view_before:
                    roles_given = set(after.roles) - set(before.roles)
                    roles_given_str = (
                        f"{{{', '.join(f'{role.name}' for role in roles_given)}}}"
                    )
                    await channel.send(
                        f"{user} added **{after.display_name}** to this channel via giving them the {roles_given_str} roles. Welcome {after.mention}! :wave:",
                    )
                elif not member_can_view_after and member_can_view_before:
                    roles_taken = set(before.roles) - set(after.roles)
                    roles_taken_str = (
                        f"{{{', '.join(f'{role.name}' for role in roles_taken)}}}"
                    )
                    await channel.send(
                        f"{user} removed **{after.display_name}** from this channel via removing the {roles_taken_str} roles. Adios! :wave:",
                    )


async def setup(bot: MILBot):
    await bot.add_cog(Leaders(bot))
